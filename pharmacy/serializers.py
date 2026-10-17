from rest_framework import serializers

from .models import Medication, Pharmacy, PharmacyMedication


class PharmacySerializer(serializers.ModelSerializer):
    """
    Forme légère d'une pharmacie, sans prix : utilisée pour la liste/carte, et pour
    la liste des pharmacies qui vendent un médicament donné (pas de prix affiché là,
    seulement la fourchette min/max du médicament).
    """

    class Meta:
        model = Pharmacy
        fields = ['id', 'name', 'address', 'phone', 'latitude', 'longitude']


class MedicationListSerializer(serializers.ModelSerializer):
    """Grille catalogue : nom, catégorie et image."""

    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Medication
        fields = ['id', 'name', 'category', 'category_display', 'image']


class MedicationDetailSerializer(serializers.ModelSerializer):
    """
    Détail d'un médicament : bande de prix min/max (annotée sur le queryset de la vue)
    et pharmacies qui le vendent, sans prix unitaire par pharmacie.
    """

    category_display = serializers.CharField(source='get_category_display', read_only=True)
    price_min = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True, allow_null=True)
    price_max = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True, allow_null=True)
    pharmacies = serializers.SerializerMethodField()

    class Meta:
        model = Medication
        fields = [
            'id', 'name', 'category', 'category_display', 'description', 'image',
            'price_min', 'price_max', 'pharmacies',
        ]

    def get_pharmacies(self, obj):
        pharmacies_qs = Pharmacy.objects.filter(medication_prices__medication=obj).distinct()
        return PharmacySerializer(pharmacies_qs, many=True, context=self.context).data


class PharmacyMedicationPriceSerializer(serializers.ModelSerializer):
    """Ligne « médicament + prix exact » pour la fiche d'une pharmacie."""

    medication_id = serializers.IntegerField(source='medication.id', read_only=True)
    medication_name = serializers.CharField(source='medication.name', read_only=True)
    medication_category = serializers.CharField(source='medication.category', read_only=True)
    medication_image = serializers.ImageField(source='medication.image', read_only=True, allow_null=True)

    class Meta:
        model = PharmacyMedication
        fields = ['medication_id', 'medication_name', 'medication_category', 'medication_image', 'price']


class PharmacyDetailSerializer(serializers.ModelSerializer):
    """Fiche pharmacie : adresse/téléphone + médicaments vendus avec prix exact."""

    medications = PharmacyMedicationPriceSerializer(source='medication_prices', many=True, read_only=True)

    class Meta:
        model = Pharmacy
        fields = ['id', 'name', 'address', 'phone', 'latitude', 'longitude', 'medications']
