from django.contrib import admin, messages

from . import plans
from .models import Subscription, SubscriptionPayment


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'current_period_end', 'is_active')
    list_filter = ('plan',)
    search_fields = ('user__username', 'user__phone_number', 'user__farm_name')
    actions = ['extend_30_days']

    @admin.display(boolean=True, description='Active')
    def is_active(self, obj):
        return obj.is_active

    @admin.action(description='Prolonger de 30 jours (formule actuelle)')
    def extend_30_days(self, request, queryset):
        done = 0
        for sub in queryset:
            if sub.plan == plans.FREE:
                continue
            sub.credit(sub.plan)
            done += 1
        self.message_user(request, f'{done} abonnement(s) prolongé(s).', messages.SUCCESS)


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'user', 'plan', 'amount', 'status', 'created_at', 'paid_at')
    list_filter = ('status', 'plan')
    search_fields = ('reference', 'user__username', 'user__phone_number')
    readonly_fields = ('user', 'plan', 'amount', 'reference', 'checkout_url', 'status', 'raw',
                       'paid_at', 'created_at', 'updated_at')
