import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from .models import User

TEST_MEDIA_ROOT = tempfile.mkdtemp()


def png(name='me.png', size=(30, 30)):
    buf = io.BytesIO()
    Image.new('RGB', size, (200, 60, 60)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ProfileTests(APITestCase):
    url = '/api/auth/users/me/'

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username='user_225', phone_number='+2250102030405', first_name='Awa', farm_name='Clapier'
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_get_profile(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['data']['first_name'], 'Awa')
        self.assertNotIn('password', res.data['data'])

    def test_update_text_fields(self):
        res = self.client.patch(self.url, {
            'first_name': 'Aïcha', 'last_name': 'Koné', 'farm_name': 'Ferme du Lac',
            'location': 'Bouaké', 'bio': 'Éleveuse de fauves', 'email': 'a@b.ci',
        }, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.location, self.user.email), ('Aïcha', 'Bouaké', 'a@b.ci'))

    def test_currency_defaults_to_euro_and_can_be_changed(self):
        self.assertEqual(self.client.get(self.url).data['data']['currency'], 'EUR')
        res = self.client.patch(self.url, {'currency': 'XOF'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['currency'], 'XOF')
        self.user.refresh_from_db()
        self.assertEqual(self.user.currency, 'XOF')
        # les autres champs du profil ne sont pas touchés
        self.assertEqual(self.user.first_name, 'Awa')

    def test_unknown_currency_is_rejected(self):
        res = self.client.patch(self.url, {'currency': 'ZZZ'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.currency, 'EUR')

    def test_phone_and_username_cannot_be_changed(self):
        self.client.patch(self.url, {'phone_number': '+22599999999', 'username': 'hacker'}, format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, '+2250102030405')
        self.assertEqual(self.user.username, 'user_225')

    def test_invalid_email_rejected(self):
        self.assertEqual(self.client.patch(self.url, {'email': 'pas-un-email'}, format='json').status_code, 400)

    def test_upload_replace_and_remove_avatar(self):
        res = self.client.patch(self.url, {'avatar': png('a.png')}, format='multipart')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.data['data']['avatar'].startswith('http'))
        self.user.refresh_from_db()
        first_path = self.user.avatar.path

        res = self.client.patch(self.url, {'avatar': png('b.png')}, format='multipart')
        self.assertEqual(res.status_code, 200)
        import os
        self.assertFalse(os.path.exists(first_path), "l'ancienne photo doit être supprimée")

        self.user.refresh_from_db()
        second_path = self.user.avatar.path
        res = self.client.patch(self.url, {'remove_avatar': 'true'}, format='multipart')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.data['data']['avatar'])
        self.assertFalse(os.path.exists(second_path))

    def test_invalid_or_oversized_avatar_rejected(self):
        fake = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
        self.assertEqual(self.client.patch(self.url, {'avatar': fake}, format='multipart').status_code, 400)

        big = SimpleUploadedFile('big.png', png().read() + b'\0' * (5 * 1024 * 1024), content_type='image/png')
        self.assertEqual(self.client.patch(self.url, {'avatar': big}, format='multipart').status_code, 400)

    def test_profile_requires_auth(self):
        self.assertIn(APIClient().get(self.url).status_code, (401, 403))

    def test_delete_account_requires_confirmation_and_removes_files(self):
        self.client.patch(self.url, {'avatar': png()}, format='multipart')
        self.user.refresh_from_db()
        path = self.user.avatar.path

        from chat.models import Conversation, Message
        other = User.objects.create_user(username='autre')
        conv, _ = Conversation.between(self.user, other)
        chat_msg = Message.objects.create(conversation=conv, sender=self.user, image=png('chat.png'))
        chat_path = chat_msg.image.path
        voice = Message.objects.create(
            conversation=conv, sender=self.user,
            audio=SimpleUploadedFile('v.m4a', b'\x00\x00\x00\x20ftypM4A ' + b'\x00' * 64),
        )
        voice_path = voice.audio.path

        self.assertEqual(self.client.delete(self.url).status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

        res = self.client.delete(self.url, {'confirm': True}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        import os
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(chat_path))
        self.assertFalse(os.path.exists(voice_path))
        self.assertEqual(Message.objects.count(), 0)
