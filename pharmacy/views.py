from django.db.models import Min, Max
from rest_framework import permissions
from drf_spectacular.utils import extend_schema

from core.utils import CustomViewSet
from .models import Medication, Pharmacy
from .serializers import (
    MedicationListSerializer,
    MedicationDetailSerializer,
    PharmacySerializer,
    PharmacyDetailSerializer,
)


@extend_schema(tags=['Pharmacie'])
class MedicationViewSet(CustomViewSet):
    """
    Catalogue des médicaments (lecture publique). price_min/price_max sont annotés
    en base (Min/Max sur PharmacyMedication) pour éviter de recalculer la bande de
    prix en Python ; None si aucune pharmacie ne vend encore le médicament.
    """

    queryset = Medication.objects.annotate(
        price_min=Min('pharmacy_prices__price'),
        price_max=Max('pharmacy_prices__price'),
    )
    serializer_class = MedicationDetailSerializer  # retrieve()
    list_serializer_class = MedicationListSerializer  # list()
    user_field_lookup = None  # Ressource partagée, comme Breed
    filterset_fields = {'category': ['exact']}
    search_fields = ['name', 'description']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


@extend_schema(tags=['Pharmacie'])
class PharmacyViewSet(CustomViewSet):
    """Répertoire des pharmacies (lecture publique)."""

    queryset = Pharmacy.objects.all()
    serializer_class = PharmacyDetailSerializer  # retrieve()
    list_serializer_class = PharmacySerializer  # list()
    user_field_lookup = None
    search_fields = ['name', 'address']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
