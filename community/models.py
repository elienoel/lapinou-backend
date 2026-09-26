from django.conf import settings
from django.db import models


# Réactions autorisées (type WhatsApp) : une seule par utilisateur et par élément
REACTION_EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🙏']
DEFAULT_REACTION = '❤️'


class Post(models.Model):
    """
    Publication / Partage communautaire entre éleveurs de lapins.
    """
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posts'
    )
    title = models.CharField(max_length=200, blank=True, default='')
    content = models.TextField(blank=True, default='')
    # Ancien champ conservé pour les publications existantes ; les nouveaux médias passent par PostMedia
    image = models.ImageField(upload_to='community_posts/', blank=True, null=True)
    tags = models.CharField(max_length=200, blank=True, null=True, help_text="Tags séparés par virgule, ex: alimentation,santé")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title or (self.content[:50] if self.content else f"Publication #{self.pk}")


class PostMedia(models.Model):
    """
    Photo ou vidéo attachée à une publication (plusieurs par publication, comme sur Facebook).
    """
    class MediaType(models.TextChoices):
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Vidéo'

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='media'
    )
    file = models.FileField(upload_to='community_posts/media/')
    media_type = models.CharField(max_length=10, choices=MediaType.choices)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return f"{self.get_media_type_display()} #{self.position} de la publication {self.post_id}"


class Comment(models.Model):
    """
    Commentaire sur une publication.
    """
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    # Réponse à un autre commentaire (un seul niveau d'imbrication, comme Facebook)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Commentaire de {self.author.username} sur la publication {self.post_id}"


class PostLike(models.Model):
    """
    Likes / Mentions 'J'aime' sur une publication.
    """
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='post_likes'
    )
    emoji = models.CharField(max_length=16, default=DEFAULT_REACTION)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} aime la publication {self.post_id}"


class CommentReaction(models.Model):
    """
    Réaction emoji d'un utilisateur à un commentaire.
    """
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comment_reactions'
    )
    emoji = models.CharField(max_length=16, default=DEFAULT_REACTION)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} {self.emoji} commentaire {self.comment_id}"


class MarketplaceListing(models.Model):
    """
    Petites annonces entre éleveurs : vente/recherche de reproducteurs, matériel, alimentation, etc.
    """
    class ListingType(models.TextChoices):
        SELL = 'sell', 'Vente reproducteur/lapin'
        BUY = 'buy', 'Recherche / Achat'
        EQUIPMENT = 'equipment', 'Matériel / Cages'
        FEED = 'feed', 'Alimentation / Fourrage'
        SERVICE = 'service', 'Service de saillie'

    class ListingStatus(models.TextChoices):
        AVAILABLE = 'available', 'Disponible'
        RESERVED = 'reserved', 'Réservé'
        CLOSED = 'closed', 'Clôturé / Vendu'

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='listings'
    )
    title = models.CharField(max_length=200)
    listing_type = models.CharField(max_length=20, choices=ListingType.choices)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    photo = models.ImageField(upload_to='marketplace/', blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=ListingStatus.choices,
        default=ListingStatus.AVAILABLE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_listing_type_display()}] {self.title}"
