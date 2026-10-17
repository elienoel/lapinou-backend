from django.db import models


class Medication(models.Model):
    """
    Médicament/traitement pour lapins du catalogue partagé (ex. Ivermectine, VHD2...).
    Référentiel global, édité uniquement via l'admin Django (comme Breed).
    """

    class Category(models.TextChoices):
        VACCINE = 'vaccine', 'Vaccin'
        ANTIBIOTIC = 'antibiotic', 'Antibiotique'
        ANTIPARASITIC = 'antiparasitic', 'Anti-parasitaire'
        VITAMIN = 'vitamin', 'Vitamine'
        DIGESTIVE = 'digestive', 'Digestif'
        OTHER = 'other', 'Autre'

    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='medications/', blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Pharmacy(models.Model):
    """
    Pharmacie vétérinaire du répertoire partagé. Pas de GeoDjango dans ce projet :
    latitude/longitude sont de simples FloatField, le filtrage "à proximité" se fait
    côté mobile (Haversine via geolocator).
    """

    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True, null=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'pharmacies'

    def __str__(self):
        return self.name


class PharmacyMedication(models.Model):
    """Prix pratiqué par une pharmacie pour un médicament donné."""

    pharmacy = models.ForeignKey(Pharmacy, on_delete=models.CASCADE, related_name='medication_prices')
    medication = models.ForeignKey(Medication, on_delete=models.CASCADE, related_name='pharmacy_prices')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('pharmacy', 'medication')
        ordering = ['pharmacy__name']

    def __str__(self):
        return f"{self.medication.name} @ {self.pharmacy.name} = {self.price}"
