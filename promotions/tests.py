import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Carousel, CarouselSlide

MEDIA = tempfile.mkdtemp()
# Plus petit GIF valide : suffit pour un ImageField
GIF = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'


@override_settings(MEDIA_ROOT=MEDIA)
class CarouselApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def slide(self, carousel, title, position, **kw):
        return CarouselSlide.objects.create(
            carousel=carousel, title=title, position=position,
            image=SimpleUploadedFile(f'{title}.gif', GIF, content_type='image/gif'), **kw,
        )

    def test_only_active_items_in_order_without_login(self):
        second = Carousel.objects.create(name='B', position=2)
        first = Carousel.objects.create(name='A', position=1)
        hidden = Carousel.objects.create(name='Off', position=0, is_active=False)
        empty = Carousel.objects.create(name='Vide', position=0)

        self.slide(first, 'a2', 2)
        self.slide(first, 'a1', 1, link_type='internal', target_screen='pharmacy')
        self.slide(first, 'a-off', 0, is_active=False)
        self.slide(second, 'b1', 1, link_type='external', external_url='https://example.com')
        self.slide(hidden, 'h1', 1)
        self.slide(empty, 'e-off', 1, is_active=False)

        res = APIClient().get('/api/promotions/carousels/')
        self.assertEqual(res.status_code, 200)
        data = res.json()['data']
        self.assertEqual([c['name'] for c in data], ['A', 'B'])
        self.assertEqual([s['title'] for s in data[0]['slides']], ['a1', 'a2'])
        self.assertEqual(data[0]['slides'][0]['target_screen'], 'pharmacy')
        self.assertTrue(data[0]['slides'][0]['image'].startswith('http://testserver/media/promotions/'))
        self.assertEqual(data[1]['slides'][0]['external_url'], 'https://example.com')

    def test_link_requires_its_target(self):
        carousel = Carousel.objects.create(name='A')
        with self.assertRaises(ValidationError):
            CarouselSlide(carousel=carousel, image='x.gif', link_type='internal').full_clean()
        with self.assertRaises(ValidationError):
            CarouselSlide(carousel=carousel, image='x.gif', link_type='external').full_clean()
