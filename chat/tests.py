import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from .models import Conversation, Message

TEST_MEDIA_ROOT = tempfile.mkdtemp()


def png(name='p.png'):
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), (10, 90, 200)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def m4a(name='note.m4a', size=2048):
    # En-tête MP4/M4A minimal : taille + 'ftyp' + marque
    return SimpleUploadedFile(name, b'\x00\x00\x00\x20ftypM4A ' + b'\x00' * size, content_type='audio/mp4')


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ChatTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.awa = User.objects.create_user(username='awa', farm_name='Clapier du Lac', location='Bouaké')
        self.kofi = User.objects.create_user(username='kofi', first_name='Kofi', last_name='Mensah')
        self.zoe = User.objects.create_user(username='zoe')
        self.a = client_for(self.awa)
        self.k = client_for(self.kofi)

    def _open(self, client, other):
        return client.post('/api/chat/conversations/', {'user': other.id}, format='json')

    def _send(self, client, conv_id, text='Bonjour', **extra):
        return client.post(f'/api/chat/conversations/{conv_id}/messages/', {'content': text, **extra}, format='multipart')

    def _msgs(self, client, conv_id, query=''):
        return client.get(f'/api/chat/conversations/{conv_id}/messages/{query}')

    # --- conversations -------------------------------------------------

    def test_one_conversation_per_pair_in_both_directions(self):
        first = self._open(self.a, self.kofi)
        self.assertEqual(first.status_code, 201)
        again = self._open(self.k, self.awa)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(first.data['data']['id'], again.data['data']['id'])
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(first.data['data']['other_user']['name'], 'Kofi Mensah')

    def test_cannot_open_conversation_with_self_or_unknown_user(self):
        self.assertEqual(self._open(self.a, self.awa).status_code, 400)
        res = self.a.post('/api/chat/conversations/', {'user': 99999}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_send_receive_and_read_receipts(self):
        conv = self._open(self.a, self.kofi).data['data']['id']
        sent = self._send(self.a, conv, 'Salut Kofi !')
        self.assertEqual(sent.status_code, 201, sent.content)
        msg_id = sent.data['data']['id']
        self.assertFalse(sent.data['data']['is_read'])

        # Kofi voit 1 non-lu dans sa liste et dans le compteur global
        listing = self.k.get('/api/chat/conversations/').data['data']
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]['unread_count'], 1)
        self.assertEqual(listing[0]['last_message']['content'], 'Salut Kofi !')
        self.assertEqual(self.k.get('/api/chat/conversations/unread-count/').data['data']['unread'], 1)
        # Awa n'a rien à lire pour son propre message
        self.assertEqual(self.a.get('/api/chat/conversations/unread-count/').data['data']['unread'], 0)

        # Awa ne sait pas encore que c'est lu
        self.assertIsNone(self._msgs(self.a, conv).data['data']['my_read_up_to'])

        # Kofi ouvre la discussion : lu
        read = self._msgs(self.k, conv)
        self.assertEqual([m['content'] for m in read.data['data']['messages']], ['Salut Kofi !'])
        self.assertEqual(self.k.get('/api/chat/conversations/unread-count/').data['data']['unread'], 0)

        # Awa reçoit l'accusé de lecture
        self.assertEqual(self._msgs(self.a, conv).data['data']['my_read_up_to'], msg_id)

    def test_conversation_without_messages_is_hidden_from_list(self):
        self._open(self.a, self.kofi)
        self.assertEqual(self.a.get('/api/chat/conversations/').data['data'], [])

    def test_list_orders_by_latest_activity(self):
        c1 = self._open(self.a, self.kofi).data['data']['id']
        c2 = self._open(self.a, self.zoe).data['data']['id']
        self._send(self.a, c1, 'premier')
        self._send(self.a, c2, 'second')
        self.assertEqual([c['id'] for c in self.a.get('/api/chat/conversations/').data['data']], [c2, c1])
        self._send(self.k, c1, 'relance')
        self.assertEqual([c['id'] for c in self.a.get('/api/chat/conversations/').data['data']], [c1, c2])

    # --- messages ------------------------------------------------------

    def test_incremental_fetch_and_history_paging(self):
        conv = self._open(self.a, self.kofi).data['data']['id']
        ids = [self._send(self.a, conv, f'm{i}').data['data']['id'] for i in range(5)]

        latest = self._msgs(self.k, conv, '?limit=2').data['data']
        self.assertEqual([m['content'] for m in latest['messages']], ['m3', 'm4'])
        self.assertTrue(latest['has_more'])

        older = self._msgs(self.k, conv, f"?limit=2&before_id={latest['messages'][0]['id']}").data['data']
        self.assertEqual([m['content'] for m in older['messages']], ['m1', 'm2'])
        self.assertTrue(older['has_more'])

        newer = self._msgs(self.k, conv, f'?after_id={ids[2]}').data['data']
        self.assertEqual([m['content'] for m in newer['messages']], ['m3', 'm4'])

        self.assertEqual(self._msgs(self.k, conv, f'?after_id={ids[4]}').data['data']['messages'], [])

    def test_send_image_and_reject_empty_or_invalid(self):
        conv = self._open(self.a, self.kofi).data['data']['id']
        res = self.a.post(f'/api/chat/conversations/{conv}/messages/', {'image': png()}, format='multipart')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(res.data['data']['image'].startswith('http'))

        self.assertEqual(self._send(self.a, conv, '   ').status_code, 400)
        fake = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
        self.assertEqual(self.a.post(f'/api/chat/conversations/{conv}/messages/', {'image': fake}, format='multipart').status_code, 400)
        self.assertEqual(self._send(self.a, conv, 'a' * 4001).status_code, 400)
        self.assertEqual(Message.objects.count(), 1)

    def test_outsider_cannot_read_or_write(self):
        conv = self._open(self.a, self.kofi).data['data']['id']
        self._send(self.a, conv, 'privé')
        z = client_for(self.zoe)
        self.assertEqual(z.get(f'/api/chat/conversations/{conv}/messages/').status_code, 404)
        self.assertEqual(self._send(z, conv, 'intrus').status_code, 404)
        self.assertEqual(Message.objects.count(), 1)

    def test_requires_authentication(self):
        self.assertIn(APIClient().get('/api/chat/conversations/').status_code, (401, 403))

    # --- recherche d'éleveurs ------------------------------------------

    def test_user_search_excludes_self_and_hides_private_data(self):
        res = self.a.get('/api/chat/conversations/users/')
        names = [u['name'] for u in res.data['data']]
        self.assertNotIn('Clapier du Lac', names)
        self.assertCountEqual(names, ['Kofi Mensah', 'zoe'])
        self.assertNotIn('phone_number', res.data['data'][0])

        found = self.k.get('/api/chat/conversations/users/?search=lac').data['data']
        self.assertEqual([u['id'] for u in found], [self.awa.id])
        self.assertEqual(self.k.get('/api/chat/conversations/users/?search=introuvable').data['data'], [])


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class VoiceNoteTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.awa = User.objects.create_user(username='awa')
        self.kofi = User.objects.create_user(username='kofi')
        self.a, self.k = client_for(self.awa), client_for(self.kofi)
        self.conv = self.a.post('/api/chat/conversations/', {'user': self.kofi.id}, format='json').data['data']['id']
        self.url = f'/api/chat/conversations/{self.conv}/messages/'

    def test_send_and_receive_voice_note(self):
        res = self.a.post(self.url, {'audio': m4a(), 'audio_duration_ms': 4200}, format='multipart')
        self.assertEqual(res.status_code, 201, res.content)
        data = res.data['data']
        self.assertTrue(data['audio'].startswith('http'))
        self.assertEqual(data['audio_duration_ms'], 4200)
        self.assertEqual(data['content'], '')

        preview = self.k.get('/api/chat/conversations/').data['data'][0]
        self.assertTrue(preview['last_message']['has_audio'])
        self.assertEqual(preview['last_message']['audio_duration_ms'], 4200)
        self.assertEqual(preview['unread_count'], 1)

        received = self.k.get(self.url).data['data']['messages'][0]
        self.assertEqual(received['audio_duration_ms'], 4200)
        self.assertTrue(received['audio'].endswith('.m4a'))

    def test_rejects_fake_audio_bad_extension_and_oversized_duration(self):
        fake = SimpleUploadedFile('note.m4a', b'ceci n est pas de l audio', content_type='audio/mp4')
        self.assertEqual(self.a.post(self.url, {'audio': fake}, format='multipart').status_code, 400)

        exe = SimpleUploadedFile('note.exe', b'\x00\x00\x00\x20ftypM4A ', content_type='application/octet-stream')
        self.assertEqual(self.a.post(self.url, {'audio': exe}, format='multipart').status_code, 400)

        too_long = self.a.post(self.url, {'audio': m4a(), 'audio_duration_ms': 11 * 60 * 1000}, format='multipart')
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(Message.objects.count(), 0)

    def test_audio_and_image_cannot_be_combined(self):
        res = self.a.post(self.url, {'audio': m4a(), 'image': png()}, format='multipart')
        self.assertEqual(res.status_code, 400)

    def test_voice_note_with_no_text_counts_as_valid_message(self):
        self.assertEqual(self.a.post(self.url, {'audio': m4a()}, format='multipart').status_code, 201)
        # duration is optional and dropped when there is no audio
        res = self.a.post(self.url, {'content': 'salut', 'audio_duration_ms': 5000}, format='multipart')
        self.assertEqual(res.status_code, 201)
        self.assertIsNone(res.data['data']['audio_duration_ms'])
