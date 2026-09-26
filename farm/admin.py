from django.contrib import admin

from .models import Cage, CareRecord, CareTreatment


@admin.register(Cage)
class CageAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'location', 'compartments_count')
    search_fields = ('name', 'location')
    list_filter = ('owner',)


@admin.register(CareTreatment)
class CareTreatmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'category', 'renewal_days')
    list_filter = ('category', 'owner')
    search_fields = ('name',)


@admin.register(CareRecord)
class CareRecordAdmin(admin.ModelAdmin):
    list_display = ('treatment', 'owner', 'date', 'next_due_date')
    list_filter = ('treatment', 'owner')
    filter_horizontal = ('rabbits',)
