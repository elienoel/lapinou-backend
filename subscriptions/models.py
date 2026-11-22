from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from . import plans


class Subscription(models.Model):
    """Palier payé par l'éleveur et date de fin de la période en cours."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription'
    )
    plan = models.CharField(max_length=20, choices=plans.CHOICES, default=plans.FREE)
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Abonnement'

    def __str__(self):
        return f'{self.user} — {self.get_plan_display()}'

    @property
    def is_active(self):
        return (
            self.plan != plans.FREE
            and self.current_period_end is not None
            and self.current_period_end > timezone.now()
        )

    @property
    def active_plan(self):
        """Palier en vigueur : le gratuit une fois la période payée terminée."""
        return plans.PLANS[self.plan] if self.is_active else plans.PLANS[plans.FREE]

    @property
    def days_left(self):
        if not self.is_active:
            return 0
        return max((self.current_period_end - timezone.now()).days, 0)

    def credit(self, plan_code, days=plans.PERIOD_DAYS):
        """
        Ajoute une période payée : le même palier encore actif est prolongé,
        un autre palier démarre tout de suite.
        """
        now = timezone.now()
        start = self.current_period_end if self.is_active and self.plan == plan_code else now
        self.plan = plan_code
        self.current_period_end = start + timedelta(days=days)
        self.save(update_fields=['plan', 'current_period_end', 'updated_at'])


class SubscriptionPayment(models.Model):
    """Paiement d'une période d'abonnement via GeniusPay."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        COMPLETED = 'completed', 'Payé'
        FAILED = 'failed', 'Échoué'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription_payments'
    )
    plan = models.CharField(max_length=20, choices=plans.PAID_CHOICES)
    amount = models.PositiveIntegerField()
    reference = models.CharField(max_length=64, unique=True, null=True, blank=True)
    checkout_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Dernière réponse GeniusPay, pour le support
    raw = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Paiement d'abonnement"
        verbose_name_plural = "Paiements d'abonnement"

    def __str__(self):
        return f'{self.reference or self.pk} — {self.amount} F — {self.get_status_display()}'
