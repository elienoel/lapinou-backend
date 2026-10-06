from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Notification, OTPVerification, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'phone_number', 'farm_name', 'currency', 'is_staff', 'is_active', 'created_at')
    list_filter = ('currency', 'is_staff', 'is_active', 'is_superuser')
    search_fields = ('username', 'phone_number', 'email', 'farm_name')
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Profil éleveur', {'fields': ('phone_number', 'avatar', 'farm_name', 'location', 'bio', 'currency')}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('Profil éleveur', {'fields': ('phone_number', 'farm_name', 'currency')}),
    )


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'otp_code', 'is_used', 'attempts', 'created_at', 'expires_at')
    list_filter = ('is_used',)
    search_fields = ('phone_number',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'sender', 'notif_type', 'is_read', 'created_at')
    list_filter = ('notif_type', 'is_read')
    search_fields = ('title', 'message', 'recipient__username', 'sender__username')
    autocomplete_fields = ('sender', 'recipient')
