from django.contrib import admin

from .models import Medication, Pharmacy, PharmacyMedication


class PharmacyMedicationInlineForPharmacy(admin.TabularInline):
    """Médicaments vendus par cette pharmacie, avec leur prix (inline sur PharmacyAdmin)."""

    model = PharmacyMedication
    extra = 1
    autocomplete_fields = ['medication']


class PharmacyMedicationInlineForMedication(admin.TabularInline):
    """Pharmacies qui vendent ce médicament, avec leur prix (inline sur MedicationAdmin)."""

    model = PharmacyMedication
    extra = 1
    autocomplete_fields = ['pharmacy']


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category', 'pharmacy_count', 'has_image')
    list_filter = ('category',)
    search_fields = ('name', 'description')
    inlines = [PharmacyMedicationInlineForMedication]

    @admin.display(description='Pharmacies')
    def pharmacy_count(self, obj):
        return obj.pharmacy_prices.count()

    @admin.display(description='Image', boolean=True)
    def has_image(self, obj):
        return bool(obj.image)


@admin.register(Pharmacy)
class PharmacyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'address', 'phone', 'latitude', 'longitude', 'medication_count')
    search_fields = ('name', 'address')
    inlines = [PharmacyMedicationInlineForPharmacy]

    @admin.display(description='Médicaments')
    def medication_count(self, obj):
        return obj.medication_prices.count()
