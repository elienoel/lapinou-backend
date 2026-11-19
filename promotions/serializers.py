from rest_framework import serializers

from .models import Carousel, CarouselSlide


class CarouselSlideSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarouselSlide
        fields = ['id', 'image', 'title', 'link_type', 'target_screen', 'external_url']


class CarouselSerializer(serializers.ModelSerializer):
    slides = serializers.SerializerMethodField()

    class Meta:
        model = Carousel
        fields = ['id', 'name', 'slides']

    def get_slides(self, obj) -> list:
        # `active_slides` est préchargé par la vue (actives, triées par ordre)
        return CarouselSlideSerializer(obj.active_slides, many=True, context=self.context).data
