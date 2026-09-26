from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Conversation(models.Model):
    """
    Discussion privée entre deux éleveurs. Il n'existe qu'une conversation par paire :
    `user_a` est toujours l'utilisateur avec le plus petit identifiant.
    """
    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_a'
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_b'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Date du dernier message : sert à trier la liste des discussions
    updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['user_a', 'user_b'], name='unique_conversation_pair'),
            models.CheckConstraint(condition=Q(user_a__lt=F('user_b')), name='conversation_users_ordered'),
        ]

    @classmethod
    def between(cls, user1, user2):
        """Renvoie (conversation, créée) entre deux utilisateurs distincts."""
        a, b = sorted([user1, user2], key=lambda u: u.pk)
        return cls.objects.get_or_create(user_a=a, user_b=b)

    def includes(self, user):
        return user.pk in (self.user_a_id, self.user_b_id)

    def other_user(self, user):
        return self.user_b if user.pk == self.user_a_id else self.user_a

    def __str__(self):
        return f"Conversation {self.user_a_id} ↔ {self.user_b_id}"


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    content = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='chat/', blank=True, null=True)
    # Note vocale : fichier audio et durée (en millisecondes) annoncée par l'application
    audio = models.FileField(upload_to='chat/audio/', blank=True, null=True)
    audio_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['conversation', 'id'])]

    def __str__(self):
        return f"Message {self.pk} de {self.sender_id}"
