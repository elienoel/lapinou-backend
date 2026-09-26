import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from .models import Comment, Post, PostMedia

TEST_MEDIA_ROOT = tempfile.mkdtemp()


def png_file(name='photo.png', size=(20, 20)):
    buf = io.BytesIO()
    Image.new('RGB', size, (10, 120, 40)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def video_file(name='clip.mp4', size=2048):
    return SimpleUploadedFile(name, b'\x00' * size, content_type='video/mp4')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class PostMediaTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='eleveur', password='x')
        self.other = User.objects.create_user(username='autre', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _post(self, data):
        return self.client.post('/api/community/posts/', data, format='multipart')

    def test_post_with_images_and_video(self):
        res = self._post({
            'content': 'Ma nouvelle portée 🐰',
            'media': [png_file('a.png'), png_file('b.png'), video_file()],
        })
        self.assertEqual(res.status_code, 201, res.content)
        media = res.data['data']['media']
        self.assertEqual([m['media_type'] for m in media], ['image', 'image', 'video'])
        self.assertTrue(all(m['url'].startswith('http') for m in media))
        self.assertEqual(res.data['data']['title'], '')
        self.assertEqual(PostMedia.objects.count(), 3)

    def test_text_only_and_media_only_posts(self):
        self.assertEqual(self._post({'content': 'Bonjour'}).status_code, 201)
        self.assertEqual(self._post({'media': [png_file()]}).status_code, 201)

    def test_empty_post_rejected(self):
        res = self._post({'content': '   '})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Post.objects.count(), 0)

    def test_invalid_files_rejected_and_nothing_saved(self):
        fake_image = SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')
        res = self._post({'content': 'x', 'media': [png_file(), fake_image]})
        self.assertEqual(res.status_code, 400)
        exe = SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream')
        self.assertEqual(self._post({'content': 'x', 'media': [exe]}).status_code, 400)
        self.assertEqual(Post.objects.count(), 0)
        self.assertEqual(PostMedia.objects.count(), 0)

    def test_too_many_files_rejected(self):
        res = self._post({'content': 'x', 'media': [png_file(f'{i}.png') for i in range(11)]})
        self.assertEqual(res.status_code, 400)

    def test_only_author_can_edit_or_delete(self):
        post = Post.objects.create(author=self.other, content='pas à toi')
        self.assertEqual(
            self.client.patch(f'/api/community/posts/{post.id}/', {'content': 'piraté'}, format='json').status_code, 403
        )
        self.assertEqual(self.client.delete(f'/api/community/posts/{post.id}/').status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.content, 'pas à toi')

    def test_author_can_delete_post_and_files(self):
        res = self._post({'content': 'à supprimer', 'media': [png_file()]})
        post_id = res.data['data']['id']
        media = PostMedia.objects.get(post_id=post_id)
        path = media.file.path
        self.assertEqual(self.client.delete(f'/api/community/posts/{post_id}/').status_code, 200)
        self.assertFalse(Post.objects.filter(pk=post_id).exists())
        import os
        self.assertFalse(os.path.exists(path))

    def test_legacy_image_is_exposed_as_media(self):
        post = Post.objects.create(author=self.user, title='Ancien', content='vieux post')
        post.image.save('old.png', png_file(), save=True)
        res = self.client.get(f'/api/community/posts/{post.id}/')
        self.assertEqual(res.status_code, 200)
        media = res.data['data']['media']
        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]['media_type'], 'image')

    def test_like_and_comment_still_work_on_other_users_post(self):
        post = Post.objects.create(author=self.other, content='hello')
        self.assertEqual(self.client.post(f'/api/community/posts/{post.id}/like/').status_code, 200)
        res = self.client.post(f'/api/community/posts/{post.id}/comments/', {'content': 'super'}, format='json')
        self.assertEqual(res.status_code, 201)


class SharedResourceVisibilityTests(APITestCase):
    def test_feed_shows_posts_of_all_authors_to_logged_in_user(self):
        User = get_user_model()
        me = User.objects.create_user(username='moi', password='x')
        other = User.objects.create_user(username='autre', password='x')
        Post.objects.create(author=me, content='le mien')
        Post.objects.create(author=other, content="celui d'un autre")
        client = APIClient()
        client.force_authenticate(me)
        res = client.get('/api/community/posts/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['data']), 2)

    def test_marketplace_listing_only_editable_by_seller(self):
        from .models import MarketplaceListing
        User = get_user_model()
        me = User.objects.create_user(username='moi', password='x')
        seller = User.objects.create_user(username='vendeur', password='x')
        listing = MarketplaceListing.objects.create(
            seller=seller, title='Cages', listing_type='equipment', description='d'
        )
        client = APIClient()
        client.force_authenticate(me)
        self.assertEqual(client.get(f'/api/community/marketplace/{listing.id}/').status_code, 200)
        self.assertEqual(client.patch(f'/api/community/marketplace/{listing.id}/', {'title': 'x'}, format='json').status_code, 403)
        self.assertEqual(client.delete(f'/api/community/marketplace/{listing.id}/').status_code, 403)
        client.force_authenticate(seller)
        self.assertEqual(client.patch(f'/api/community/marketplace/{listing.id}/', {'title': 'Cages neuves'}, format='json').status_code, 200)


class ReactionsAndRepliesTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.me = User.objects.create_user(username='moi', password='x')
        self.other = User.objects.create_user(username='autre', password='x')
        self.post = Post.objects.create(author=self.other, content='Ma portée')
        self.client = APIClient()
        self.client.force_authenticate(self.me)
        self.like_url = f'/api/community/posts/{self.post.id}/like/'

    def test_post_reaction_set_change_remove(self):
        res = self.client.post(self.like_url, {'emoji': '😂'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['my_reaction'], '😂')
        self.assertTrue(res.data['data']['is_liked'])
        self.assertEqual(res.data['data']['reactions'], [{'emoji': '😂', 'count': 1}])

        # autre emoji = remplacement (pas de doublon)
        res = self.client.post(self.like_url, {'emoji': '🙏'}, format='json')
        self.assertEqual(res.data['data']['my_reaction'], '🙏')
        self.assertEqual(res.data['data']['likes_count'], 1)

        # même emoji = retrait
        res = self.client.post(self.like_url, {'emoji': '🙏'}, format='json')
        self.assertIsNone(res.data['data']['my_reaction'])
        self.assertFalse(res.data['data']['is_liked'])
        self.assertEqual(res.data['data']['likes_count'], 0)

    def test_default_reaction_and_invalid_emoji(self):
        res = self.client.post(self.like_url)
        self.assertEqual(res.data['data']['my_reaction'], '❤️')
        self.assertEqual(self.client.post(self.like_url, {'emoji': '💩'}, format='json').status_code, 400)

    def test_post_serializes_reaction_summary_for_viewer(self):
        User = get_user_model()
        third = User.objects.create_user(username='troisieme', password='x')
        self.client.post(self.like_url, {'emoji': '❤️'}, format='json')
        other_client = APIClient()
        other_client.force_authenticate(third)
        other_client.post(self.like_url, {'emoji': '❤️'}, format='json')
        other_client.post(f'/api/community/posts/{self.post.id}/like/', {'emoji': '👍'}, format='json')  # remplace

        data = self.client.get(f'/api/community/posts/{self.post.id}/').data['data']
        self.assertEqual(data['likes_count'], 2)
        self.assertEqual(data['my_reaction'], '❤️')
        self.assertCountEqual(
            data['reactions'], [{'emoji': '❤️', 'count': 1}, {'emoji': '👍', 'count': 1}]
        )

    def _comment(self, text, parent=None):
        body = {'content': text}
        if parent:
            body['parent'] = parent
        return self.client.post(f'/api/community/posts/{self.post.id}/comments/', body, format='json')

    def test_reply_to_comment_and_flatten_nested_replies(self):
        root = self._comment('Super !').data['data']
        self.assertIsNone(root['parent'])
        reply = self._comment('Merci', parent=root['id'])
        self.assertEqual(reply.status_code, 201, reply.content)
        self.assertEqual(reply.data['data']['parent'], root['id'])

        # répondre à une réponse rattache au commentaire racine
        nested = self._comment('Et moi ?', parent=reply.data['data']['id'])
        self.assertEqual(nested.data['data']['parent'], root['id'])

        listing = self.client.get(f'/api/community/posts/{self.post.id}/comments/').data['data']
        self.assertEqual(len(listing), 3)
        self.assertEqual(self.client.get(f'/api/community/posts/{self.post.id}/').data['data']['comments_count'], 3)

    def test_reply_parent_must_belong_to_same_post(self):
        other_post = Post.objects.create(author=self.other, content='autre')
        foreign = Comment.objects.create(post=other_post, author=self.other, content='ailleurs')
        self.assertEqual(self._comment('hors sujet', parent=foreign.id).status_code, 400)

    def test_comment_reactions(self):
        comment = Comment.objects.create(post=self.post, author=self.other, content='Bravo')
        url = f'/api/community/comments/{comment.id}/react/'
        res = self.client.post(url, {'emoji': '👍'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data['data']['my_reaction'], '👍')
        self.assertEqual(res.data['data']['likes_count'], 1)

        listing = self.client.get(f'/api/community/posts/{self.post.id}/comments/').data['data']
        self.assertEqual(listing[0]['my_reaction'], '👍')
        self.assertEqual(listing[0]['reactions'], [{'emoji': '👍', 'count': 1}])

        res = self.client.post(url, {'emoji': '👍'}, format='json')  # retrait
        self.assertIsNone(res.data['data']['my_reaction'])
        self.assertEqual(self.client.post(url, {'emoji': 'x'}, format='json').status_code, 400)

    def test_only_author_can_edit_or_delete_comment(self):
        comment = Comment.objects.create(post=self.post, author=self.other, content='à moi')
        url = f'/api/community/comments/{comment.id}/'
        self.assertEqual(self.client.patch(url, {'content': 'piraté'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
