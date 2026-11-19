from django.core.exceptions import ValidationError
from django.db import models


class Carousel(models.Model):
    """
    Carrousel d'annonces affiché sur la page d'accueil de l'app mobile.
    Plusieurs carrousels peuvent s'afficher l'un sous l'autre, dans l'ordre de
    `position` (le plus petit en premier). Géré uniquement via l'admin Django.
    """

    name = models.CharField('nom', max_length=100, help_text="Nom interne, non affiché dans l'app.")
    position = models.PositiveIntegerField('ordre', default=0, help_text='Le plus petit s’affiche en premier.')
    is_active = models.BooleanField('actif', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'id']
        verbose_name = 'carrousel'

    def __str__(self):
        return self.name


class CarouselSlide(models.Model):
    """
    Image d'annonce (format 16:9) d'un carrousel. Un appui ouvre soit un écran de
    l'application, soit un site web, soit rien.
    """

    class LinkType(models.TextChoices):
        NONE = 'none', 'Aucun lien'
        INTERNAL = 'internal', "Écran de l'application"
        EXTERNAL = 'external', 'Site web'

    class Screen(models.TextChoices):
        PHARMACY = 'pharmacy', 'Pharmacie'
        MARKETPLACE = 'marketplace', 'Petites annonces'
        RABBITS = 'rabbits', 'Mes lapins'
        REPRODUCTION = 'reproduction', 'Reproduction'
        CARE = 'care', 'Soins & entretien'
        COMMUNITY = 'community', 'Communauté'
        CHAT = 'chat', 'Messagerie'
        ACTIVITY = 'activity', 'Activité'
        FINANCES = 'finances', 'Finances'

    carousel = models.ForeignKey(Carousel, on_delete=models.CASCADE, related_name='slides')
    image = models.ImageField('image (16:9)', upload_to='promotions/')
    title = models.CharField(
        'titre', max_length=150, blank=True,
        help_text="Texte alternatif (accessibilité), non affiché sur l'image.",
    )
    link_type = models.CharField('lien', max_length=10, choices=LinkType.choices, default=LinkType.NONE)
    target_screen = models.CharField('écran', max_length=20, choices=Screen.choices, blank=True)
    external_url = models.URLField('adresse du site', blank=True)
    position = models.PositiveIntegerField('ordre', default=0, help_text='Le plus petit s’affiche en premier.')
    is_active = models.BooleanField('active', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'id']
        verbose_name = 'image du carrousel'
        verbose_name_plural = 'images du carrousel'

    def __str__(self):
        return self.title or f'Image #{self.pk}'

    def clean(self):
        if self.link_type == self.LinkType.INTERNAL and not self.target_screen:
            raise ValidationError({'target_screen': "Choisissez l'écran à ouvrir."})
        if self.link_type == self.LinkType.EXTERNAL and not self.external_url:
            raise ValidationError({'external_url': "Indiquez l'adresse du site."})
