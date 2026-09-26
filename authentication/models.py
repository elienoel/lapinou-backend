from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


# Devises proposées dans les paramètres (affichage des montants ; aucune conversion n'est faite)
CURRENCY_CHOICES = [
    ('EUR', 'Euro'),
    ('XOF', 'Franc CFA (BCEAO)'),
    ('XAF', 'Franc CFA (BEAC)'),
    ('USD', 'Dollar américain'),
    ('GBP', 'Livre sterling'),
    ('CHF', 'Franc suisse'),
    ('CAD', 'Dollar canadien'),
    ('MAD', 'Dirham marocain'),
    ('TND', 'Dinar tunisien'),
    ('DZD', 'Dinar algérien'),
    ('NGN', 'Naira nigérian'),
    ('GHS', 'Cedi ghanéen'),
    ('GNF', 'Franc guinéen'),
    ('CDF', 'Franc congolais'),
]
DEFAULT_CURRENCY = 'EUR'


class User(AbstractUser):
    """
    Modèle utilisateur personnalisé pour la plateforme d'élevage et communauté.
    """
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    farm_name = models.CharField(max_length=150, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.phone_number or self.username or str(self.id)


class OTPVerification(models.Model):
    """
    Stockage des codes OTP pour l'authentification par numéro de téléphone.
    """
    phone_number = models.CharField(max_length=20, db_index=True)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at

    def __str__(self):
        return f"OTP for {self.phone_number}: {self.otp_code}"






class NotificationType(models.TextChoices):
    INFO = "info", "Information"
    WARNING = "warning", "Avertissement"
    SUCCESS = "success", "Succès"
    ERROR = "error", "Erreur"
    APPROVAL = "approval", "Approbation"
    COMMENT = "comment", "Commentaire"
    SYSTEM = "system", "Système"


class Notification(models.Model):
    """
    Notification générique pour tout l'ERP
    """
    sender = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_notifications"
    )
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )

    # Pour lier à n'importe quel objet (ex: Crm_Lease, PurchaseRequest, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    notif_type = models.CharField(
        max_length=50, choices=NotificationType.choices, default=NotificationType.INFO
    )

    # lecture + dates
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # gestion d'expiration / archivage si besoin
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def mark_as_read(self):
        """Marque la notification comme lue."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    def __str__(self):
        return f"{self.title} → {self.recipient.username}"

