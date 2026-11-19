from django.contrib import admin
from django.utils.html import format_html

from .models import Carousel, CarouselSlide


class CarouselSlideInline(admin.TabularInline):
    model = CarouselSlide
    extra = 1
    fields = ('preview', 'image', 'title', 'link_type', 'target_screen', 'external_url', 'position', 'is_active')
    readonly_fields = ('preview',)

    @admin.display(description='Aperçu')
    def preview(self, obj):
        if obj.pk and obj.image:
            return format_html('<img src="{}" style="width:160px;aspect-ratio:16/9;object-fit:cover;border-radius:6px">', obj.image.url)
        return '—'


@admin.register(Carousel)
class CarouselAdmin(admin.ModelAdmin):
    list_display = ('name', 'position', 'is_active', 'slide_count')
    list_editable = ('position', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    inlines = [CarouselSlideInline]

    @admin.display(description='Images actives')
    def slide_count(self, obj):
        return obj.slides.filter(is_active=True).count()


@admin.register(CarouselSlide)
class CarouselSlideAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'carousel', 'link_type', 'position', 'is_active')
    list_editable = ('position', 'is_active')
    list_filter = ('carousel', 'is_active', 'link_type')
    search_fields = ('title', 'external_url')
