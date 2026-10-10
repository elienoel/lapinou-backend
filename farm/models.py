from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from datetime import timedelta

from django.db import models
from django.utils import timezone


class SyncableModel(models.Model):
    """
    Champs communs aux modèles Farm synchronisables depuis le mode hors-ligne mobile.

    - client_uuid : identifiant généré côté client à la création, utilisé pour rendre
      les créations idempotentes (un retry réseau après coupure ne crée pas de doublon).
    - is_deleted/deleted_at : suppression douce, pour que le mobile puisse détecter
      lors d'une synchronisation qu'un enregistrement a été supprimé côté serveur.
    """
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class Breed(models.Model):
    """
    Race de lapin (Fauve de Bourgogne, Néo-Zélandais, Géant des Flandres, Papillon, etc.)
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    average_gestation_days = models.PositiveIntegerField(default=31)
    image = models.ImageField(upload_to='breeds/', blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Cage(SyncableModel):
    """
    Cage d'élevage : une grille de loges (lignes x colonnes).
    Les loges sont numérotées ligne par ligne, de haut en bas puis de gauche à droite
    (1 = loge en haut à gauche).
    """
    MAX_ROWS = 12
    MAX_COLUMNS = 6

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cages'
    )
    name = models.CharField(max_length=50, help_text="Nom ou code de la cage (ex. A1)")
    location = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Emplacement (bâtiment, rangée...)"
    )
    rows_count = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_ROWS)],
        help_text="Nombre de lignes (étages) de loges"
    )
    columns_count = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_COLUMNS)],
        help_text="Nombre de colonnes de loges"
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('owner', 'name')

    @property
    def compartments_count(self):
        return self.rows_count * self.columns_count

    def position_of(self, number):
        """Retourne (ligne, colonne) 1-indexées d'une loge."""
        return (number - 1) // self.columns_count + 1, (number - 1) % self.columns_count + 1

    def __str__(self):
        return f"Cage {self.name} ({self.rows_count}x{self.columns_count} loges)"


class Rabbit(SyncableModel):
    """
    Représentation d'un lapin reproducteur ou d'élevage.
    Inclut l'arbre généalogique via sire (père) et dam (mère).
    """
    class Gender(models.TextChoices):
        MALE = 'M', 'Mâle'
        FEMALE = 'F', 'Femelle'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Reproducteur actif'
        PREGNANT = 'pregnant', 'En gestation'
        LACTATING = 'lactating', 'En allaitement'
        RESTING = 'resting', 'En repos'
        RETIRED = 'retired', 'Retiré / Réformé'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rabbits'
    )
    name = models.CharField(max_length=100)
    tag_number = models.CharField(max_length=50, help_text="Numéro de bague ou d'identification")
    gender = models.CharField(max_length=1, choices=Gender.choices)
    breed = models.ForeignKey(
        Breed,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rabbits'
    )
    birth_date = models.DateField()
    color = models.CharField(max_length=50, blank=True, null=True)
    cage_number = models.CharField(max_length=50, blank=True, null=True)
    cage = models.ForeignKey(
        Cage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rabbits'
    )
    compartment_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Numéro de la loge occupée dans la cage (1 = haut)"
    )
    
    # Arbre généalogique (parents)
    sire = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sire_offspring',
        limit_choices_to={'gender': Gender.MALE},
        help_text="Père (mâle)"
    )
    dam = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dam_offspring',
        limit_choices_to={'gender': Gender.FEMALE},
        help_text="Mère (femelle)"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    photo = models.ImageField(upload_to='rabbits/', null=True, blank=True)
    avatar_color_index = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('owner', 'tag_number')

    @property
    def nursing_kits(self):
        """Lapereaux encore au nid avec cette lapine (ils la suivent quand on la déplace)."""
        return sum(litter.kits_remaining for litter in self.litters_as_mother.filter(is_deleted=False))

    def __str__(self):
        return f"{self.name} ({self.tag_number})"


class RabbitImage(models.Model):
    """
    Photos additionnelles ou galerie d'un lapin, avec possibilité d'indiquer la photo principale.
    """
    rabbit = models.ForeignKey(
        Rabbit,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='rabbits/gallery/')
    caption = models.CharField(max_length=200, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', '-created_at']

    def __str__(self):
        return f"Photo de {self.rabbit.name} ({'Principale' if self.is_primary else 'Galerie'})"


class Mating(SyncableModel):
    """
    Accouplement / Saillie entre un mâle et une femelle.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente palpation'
        CONFIRMED = 'confirmed', 'Gestante confirmée'
        KINDLED = 'kindled', 'Mise bas réalisée'
        FAILED = 'failed', 'Infructueux'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='matings'
    )
    male = models.ForeignKey(
        Rabbit,
        on_delete=models.CASCADE,
        related_name='matings_as_sire',
        limit_choices_to={'gender': Rabbit.Gender.MALE}
    )
    female = models.ForeignKey(
        Rabbit,
        on_delete=models.CASCADE,
        related_name='matings_as_dam',
        limit_choices_to={'gender': Rabbit.Gender.FEMALE}
    )
    mating_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    palpation_date = models.DateField(null=True, blank=True, help_text="Date palpation prévue (~J+12)")
    palpation_done_at = models.DateField(null=True, blank=True, help_text="Date à laquelle la palpation a été effectuée")
    nest_box_date = models.DateField(null=True, blank=True, help_text="Pose boîte à nid (~J+28)")
    expected_kindling_date = models.DateField(null=True, blank=True, help_text="Date prévue mise bas (~J+31)")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Une mise bas ne peut pas être enregistrée moins de 21 jours après la saillie
    MIN_GESTATION_DAYS = 21

    class Meta:
        ordering = ['-mating_date']

    @property
    def earliest_kindling_date(self):
        return self.mating_date + timedelta(days=self.MIN_GESTATION_DAYS)

    def __str__(self):
        return f"Accouplement {self.male.name} x {self.female.name} le {self.mating_date}"


class Litter(SyncableModel):
    """
    Mise bas / Portée de lapereaux.
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='litters'
    )
    mating = models.OneToOneField(
        Mating,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='litter'
    )
    mother = models.ForeignKey(
        Rabbit,
        on_delete=models.CASCADE,
        related_name='litters_as_mother',
        limit_choices_to={'gender': Rabbit.Gender.FEMALE}
    )
    father = models.ForeignKey(
        Rabbit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='litters_as_father',
        limit_choices_to={'gender': Rabbit.Gender.MALE}
    )
    birth_date = models.DateField()
    born_alive = models.PositiveIntegerField(default=0)
    still_born = models.PositiveIntegerField(default=0)
    # Total cumulé de lapereaux sevrés (le sevrage peut se faire en plusieurs fois)
    weaned_count = models.PositiveIntegerField(null=True, blank=True)
    # Lapereaux nés vivants morts au nid avant le sevrage
    died_count = models.PositiveIntegerField(default=0)
    # Date PRÉVUE du sevrage (~J+45) et date du dernier sevrage RÉEL
    weaning_date = models.DateField(null=True, blank=True, help_text="Date sevrage prévue (~J+45)")
    weaned_at = models.DateField(null=True, blank=True, help_text="Date du dernier sevrage effectué")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    DEFAULT_WEANING_DAYS = 45

    class Status:
        NURSING = 'nursing'          # au nid, sevrage pas encore dû
        WEANING_DUE = 'weaning_due'  # la date prévue est passée, sevrage à confirmer
        WEANED = 'weaned'            # plus aucun lapereau à sevrer

    class Meta:
        ordering = ['-birth_date']

    @property
    def total_born(self):
        return self.born_alive + self.still_born

    @property
    def kits_remaining(self):
        """Lapereaux encore au nid : nés vivants, ni sevrés ni morts."""
        return max(self.born_alive - (self.weaned_count or 0) - self.died_count, 0)

    @property
    def age_days(self):
        return (timezone.localdate() - self.birth_date).days

    @property
    def planned_weaning_date(self):
        return self.weaning_date or self.birth_date + timedelta(days=self.DEFAULT_WEANING_DAYS)

    @property
    def days_until_weaning(self):
        """Jours avant la date prévue de sevrage (négatif = en retard)."""
        return (self.planned_weaning_date - timezone.localdate()).days

    @property
    def weaning_status(self):
        if self.kits_remaining == 0:
            return self.Status.WEANED
        return self.Status.WEANING_DUE if self.days_until_weaning <= 0 else self.Status.NURSING

    def __str__(self):
        return f"Portée de {self.mother.name} du {self.birth_date} ({self.born_alive} vivants)"


class CareTreatment(SyncableModel):
    """
    Type de soin défini par l'éleveur (ex. « Vaccin VHD2 », « Vitamine ADE », « Ivermectine »)
    avec sa durée avant renouvellement. Sans durée, le soin est ponctuel (aucun rappel).
    """
    class Category(models.TextChoices):
        VACCINE = 'vaccine', 'Vaccin'
        VITAMIN = 'vitamin', 'Vitamine'
        DEWORMING = 'deworming', 'Déparasitant'
        ANTIPARASITIC = 'antiparasitic', 'Anti-parasitaire externe'
        COCCIDIOSIS = 'coccidiosis', 'Anti-coccidien'
        ANTIBIOTIC = 'antibiotic', 'Antibiotique'
        OTHER = 'other', 'Autre'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='care_treatments'
    )
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    renewal_days = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1)],
        help_text="Durée en jours avant de renouveler le soin (vide = soin ponctuel)"
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('owner', 'name')

    def __str__(self):
        return self.name


class CareRecord(SyncableModel):
    """
    Soin effectué : quel traitement, quand, pourquoi et sur quels lapins.
    La prochaine échéance est calculée à partir de la date et de la durée de renouvellement.
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='care_records'
    )
    # Un type de soin utilisé dans l'historique ne peut pas être supprimé (voir CareTreatmentViewSet)
    treatment = models.ForeignKey(
        CareTreatment,
        on_delete=models.PROTECT,
        related_name='records'
    )
    rabbits = models.ManyToManyField(Rabbit, related_name='care_records')
    date = models.DateField(help_text="Date à laquelle le soin a été effectué")
    purpose = models.CharField(max_length=200, blank=True, default='', help_text="Motif du soin")
    next_due_date = models.DateField(null=True, blank=True, help_text="Prochaine échéance de renouvellement")
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Une échéance dans moins de SOON_DAYS jours est signalée « bientôt »
    SOON_DAYS = 7

    class Meta:
        ordering = ['-date', '-id']

    @staticmethod
    def compute_next_due_date(treatment, date):
        return date + timedelta(days=treatment.renewal_days) if treatment.renewal_days else None

    @property
    def days_until_due(self):
        """Jours avant l'échéance (négatif = en retard), None si aucun renouvellement prévu."""
        if self.next_due_date is None:
            return None
        return (self.next_due_date - timezone.localdate()).days

    def __str__(self):
        return f"{self.treatment.name} le {self.date}"


class CareEvent(SyncableModel):
    """
    Soin et suivi vétérinaire (vaccin, vermifuge, anti-parasite, etc.).
    """
    class CareType(models.TextChoices):
        VACCINE = 'vaccine', 'Vaccination'
        DEWORMING = 'deworming', 'Vermifuge'
        ANTIPARASITIC = 'antiparasitic', 'Anti-parasitaire'
        COCCIDIOSIS = 'coccidiosis', 'Coccidiose'
        CHECKUP = 'checkup', 'Contrôle général'
        OTHER = 'other', 'Autre soin'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='care_events'
    )
    rabbit = models.ForeignKey(
        Rabbit,
        on_delete=models.CASCADE,
        related_name='care_events'
    )
    care_type = models.CharField(max_length=30, choices=CareType.choices)
    title = models.CharField(max_length=150)
    date = models.DateField()
    reminder_date = models.DateField(null=True, blank=True, help_text="Rappel prochain soin")
    is_completed = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.title} - {self.rabbit.name} ({self.date})"


class FinanceTransaction(SyncableModel):
    """
    Suivi financier : Dépenses (aliment, paille, matériel, veto) et Ventes/Entrées d'argent.
    """
    class TransactionType(models.TextChoices):
        INCOME = 'income', 'Entrée / Vente'
        EXPENSE = 'expense', 'Dépense'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='finance_transactions'
    )
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    title = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    category = models.CharField(max_length=100)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        sign = "+" if self.transaction_type == self.TransactionType.INCOME else "-"
        return f"{sign}{self.amount} - {self.title} ({self.date})"
