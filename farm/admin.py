from django.contrib import admin

from .models import (
    Breed,
    Cage,
    CareEvent,
    CareRecord,
    CareTreatment,
    FinanceTransaction,
    Litter,
    Mating,
    Rabbit,
    RabbitImage,
)


@admin.register(Breed)
class BreedAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'average_gestation_days', 'description', 'rabbit_count')
    list_filter = ('average_gestation_days',)
    search_fields = ('name', 'description')

    @admin.display(description='Lapins')
    def rabbit_count(self, obj):
        return obj.rabbits.count()


@admin.register(Cage)
class CageAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'location', 'rows_count', 'columns_count', 'compartments_count')
    list_filter = ('owner',)
    search_fields = ('name', 'location')


class RabbitImageInline(admin.TabularInline):
    model = RabbitImage
    extra = 0


@admin.register(Rabbit)
class RabbitAdmin(admin.ModelAdmin):
    list_display = ('name', 'tag_number', 'gender', 'breed', 'status', 'owner', 'birth_date')
    list_filter = ('gender', 'status', 'breed')
    search_fields = ('name', 'tag_number', 'owner__username')
    autocomplete_fields = ('owner', 'breed', 'cage', 'sire', 'dam')
    inlines = [RabbitImageInline]


@admin.register(RabbitImage)
class RabbitImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'rabbit', 'is_primary', 'caption', 'created_at')
    list_filter = ('is_primary',)
    search_fields = ('rabbit__name', 'caption')


@admin.register(Mating)
class MatingAdmin(admin.ModelAdmin):
    list_display = ('id', 'male', 'female', 'mating_date', 'status', 'owner')
    list_filter = ('status',)
    search_fields = ('male__name', 'female__name', 'owner__username')
    autocomplete_fields = ('male', 'female')


@admin.register(Litter)
class LitterAdmin(admin.ModelAdmin):
    list_display = ('id', 'mother', 'father', 'birth_date', 'born_alive', 'owner')
    list_filter = ('birth_date',)
    search_fields = ('mother__name', 'father__name', 'owner__username')
    autocomplete_fields = ('mother', 'father', 'mating')


@admin.register(CareTreatment)
class CareTreatmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'category', 'renewal_days', 'created_at')
    list_filter = ('category', 'owner')
    search_fields = ('name',)


@admin.register(CareRecord)
class CareRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'treatment', 'owner', 'date', 'next_due_date', 'purpose')
    list_filter = ('treatment', 'owner')
    search_fields = ('purpose', 'treatment__name')
    filter_horizontal = ('rabbits',)


@admin.register(CareEvent)
class CareEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'rabbit', 'care_type', 'date', 'is_completed', 'owner')
    list_filter = ('care_type', 'is_completed')
    search_fields = ('title', 'rabbit__name', 'owner__username')


@admin.register(FinanceTransaction)
class FinanceTransactionAdmin(admin.ModelAdmin):
    list_display = ('title', 'transaction_type', 'amount', 'date', 'category', 'owner')
    list_filter = ('transaction_type', 'category')
    search_fields = ('title', 'category', 'owner__username')
