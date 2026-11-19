from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import build_success_response
from .models import Carousel, CarouselSlide
from .serializers import CarouselSerializer


@extend_schema(tags=['Annonces'], responses=CarouselSerializer(many=True))
class ActiveCarouselsView(APIView):
    """
    Carrousels actifs de la page d'accueil, dans l'ordre, avec leurs images
    actives dans l'ordre. Les carrousels sans aucune image active sont omis.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        carousels = (
            Carousel.objects.filter(is_active=True, slides__is_active=True)
            .distinct()
            .prefetch_related(
                Prefetch(
                    'slides',
                    queryset=CarouselSlide.objects.filter(is_active=True).order_by('position', 'id'),
                    to_attr='active_slides',
                )
            )
            .order_by('position', 'id')
        )
        data = CarouselSerializer(carousels, many=True, context={'request': request}).data
        return Response(build_success_response(data))
