from django.utils import timezone
from rest_framework import serializers
from .models import (
    Breed, Cage, Rabbit, RabbitImage, Mating, Litter,
    CareTreatment, CareRecord, CareEvent, FinanceTransaction,
)
from drf_spectacular.utils import extend_schema_field

from core.utils import UserActionMixinSerializer


class BreedSerializer(serializers.ModelSerializer):
    """
    Sérialiseur pour les races de lapins.
    """
    class Meta:
        model = Breed
        fields = ['id', 'name', 'description', 'average_gestation_days']


class RabbitImageSerializer(serializers.ModelSerializer):
    """
    Sérialiseur pour les photos additionnelles d'un lapin.
    """
    class Meta:
        model = RabbitImage
        fields = ['id', 'rabbit', 'image', 'caption', 'is_primary', 'created_at']
        read_only_fields = ['id', 'created_at']


class RabbitSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les lapins avec détails des parents et de la race.
    Sérialiseur pour les lapins avec détails des parents, race et galerie d'images.
    """
    breed_name = serializers.CharField(source='breed.name', read_only=True)
    sire_name = serializers.CharField(source='sire.name', read_only=True)
    sire_tag = serializers.CharField(source='sire.tag_number', read_only=True)
    dam_name = serializers.CharField(source='dam.name', read_only=True)
    dam_tag = serializers.CharField(source='dam.tag_number', read_only=True)
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    images = RabbitImageSerializer(many=True, read_only=True)
    cage_name = serializers.CharField(source='cage.name', read_only=True)
    nursing_kits = serializers.IntegerField(read_only=True)

    class Meta:
        model = Rabbit
        fields = [
            'id', 'owner', 'name', 'tag_number', 'gender', 'gender_display',
            'breed', 'breed_name', 'birth_date', 'color', 'cage_number',
            'cage', 'cage_name', 'compartment_number', 'nursing_kits',
            'sire', 'sire_name', 'sire_tag',
            'dam', 'dam_name', 'dam_tag',
            'status', 'status_display', 'weight_kg', 'photo',
            'images',
            'avatar_color_index', 'notes', 'client_uuid', 'is_deleted', 'created_at', 'updated_at',
            'created_by_user'
        ]
        read_only_fields = ['id', 'owner', 'images', 'nursing_kits', 'is_deleted', 'created_at', 'updated_at', 'created_by_user']

    def validate(self, attrs):
        instance = self.instance

        # La bague est unique par éleveur (le propriétaire est en lecture seule : DRF ne le vérifie pas)
        tag = attrs.get('tag_number')
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if tag and user is not None and getattr(user, 'is_authenticated', False):
            same_tag = Rabbit.objects.filter(owner=user, tag_number=tag)
            if instance is not None:
                same_tag = same_tag.exclude(pk=instance.pk)
            if same_tag.exists():
                raise serializers.ValidationError(
                    {'tag_number': f"La bague {tag} est déjà utilisée dans votre élevage."}
                )

        # Un lapin occupe une loge précise d'une cage de son propre élevage ;
        # une loge peut accueillir plusieurs lapins.
        cage = attrs['cage'] if 'cage' in attrs else getattr(instance, 'cage', None)
        compartment = (
            attrs['compartment_number'] if 'compartment_number' in attrs
            else getattr(instance, 'compartment_number', None)
        )
        if cage is None:
            if compartment is not None:
                raise serializers.ValidationError(
                    {'compartment_number': "Sélectionnez d'abord une cage."}
                )
            return attrs

        if user is not None and cage.owner_id != user.id:
            raise serializers.ValidationError({'cage': "Cette cage n'appartient pas à votre élevage."})
        if compartment is None:
            raise serializers.ValidationError({'compartment_number': "Indiquez la loge de la cage."})
        if compartment < 1 or compartment > cage.compartments_count:
            raise serializers.ValidationError({
                'compartment_number': f"La cage {cage.name} possède {cage.compartments_count} loge(s)."
            })
        attrs['cage_number'] = f"{cage.name}-{compartment}"
        return attrs


class CageSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur d'une cage avec l'état de chacune de ses loges (occupant éventuel).
    """
    compartments = serializers.SerializerMethodField()
    compartments_count = serializers.IntegerField(read_only=True)
    occupied_count = serializers.SerializerMethodField()
    rabbits_count = serializers.SerializerMethodField()
    kits_count = serializers.SerializerMethodField()

    class Meta:
        model = Cage
        fields = [
            'id', 'owner', 'name', 'location', 'rows_count', 'columns_count',
            'compartments_count',
            'occupied_count', 'rabbits_count', 'kits_count', 'compartments', 'notes',
            'client_uuid', 'is_deleted', 'created_at', 'updated_at', 'created_by_user'
        ]
        read_only_fields = ['id', 'owner', 'is_deleted', 'created_at', 'updated_at', 'created_by_user']

    def _occupants(self, cage):
        """Lapins de la cage regroupés par numéro de loge (plusieurs par loge possible)."""
        grouped = {}
        for r in cage.rabbits.filter(is_deleted=False):
            if r.compartment_number:
                grouped.setdefault(r.compartment_number, []).append(r)
        return grouped

    def _rabbit_summary(self, rabbit):
        request = self.context.get('request')
        return {
            'id': rabbit.id,
            'name': rabbit.name,
            'tag_number': rabbit.tag_number,
            # lapereaux au nid avec cette lapine : ils suivent la mère quand elle change de loge
            'nursing_kits': rabbit.nursing_kits,
            'gender': rabbit.gender,
            'status': rabbit.status,
            'photo': (
                request.build_absolute_uri(rabbit.photo.url)
                if rabbit.photo and request else (rabbit.photo.url if rabbit.photo else None)
            ),
        }

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_compartments(self, cage):
        occupants = self._occupants(cage)
        result = []
        for number in range(1, cage.compartments_count + 1):
            rabbits = [self._rabbit_summary(r) for r in occupants.get(number, [])]
            row, column = cage.position_of(number)
            result.append({
                'number': number,
                'row': row,
                'column': column,
                # `rabbits` : tous les lapins de la loge ; `rabbit` : le premier (compatibilité)
                'rabbits': rabbits,
                'rabbit': rabbits[0] if rabbits else None,
            })
        return result

    @extend_schema_field(serializers.IntegerField())
    def get_occupied_count(self, cage):
        """Nombre de loges occupées (une loge à plusieurs lapins ne compte qu'une fois)."""
        return len(self._occupants(cage))

    @extend_schema_field(serializers.IntegerField())
    def get_rabbits_count(self, cage):
        return sum(len(v) for v in self._occupants(cage).values())

    @extend_schema_field(serializers.IntegerField())
    def get_kits_count(self, cage):
        """Lapereaux non sevrés présents dans la cage (avec leur mère)."""
        return sum(r.nursing_kits for rabbits in self._occupants(cage).values() for r in rabbits)

    def validate(self, attrs):
        if self.instance is None:
            return attrs
        occupied = [r.compartment_number for r in self.instance.rabbits.filter(is_deleted=False) if r.compartment_number]
        if not occupied:
            return attrs
        rows = attrs.get('rows_count', self.instance.rows_count)
        columns = attrs.get('columns_count', self.instance.columns_count)
        if columns != self.instance.columns_count:
            raise serializers.ValidationError({
                'columns_count': "Libérez les loges occupées avant de changer le nombre de colonnes."
            })
        highest = max(occupied)
        if highest > rows * columns:
            raise serializers.ValidationError({
                'rows_count': f"La loge {highest} est occupée : libérez-la avant de réduire le nombre de lignes."
            })
        return attrs

    def validate_name(self, value):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        qs = Cage.objects.filter(owner=user, name__iexact=value.strip()) if user else Cage.objects.none()
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Une cage porte déjà ce nom.")
        return value.strip()


class MatingSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les accouplements / saillies avec noms des reproducteurs.
    """
    male_name = serializers.CharField(source='male.name', read_only=True)
    male_tag = serializers.CharField(source='male.tag_number', read_only=True)
    female_name = serializers.CharField(source='female.name', read_only=True)
    female_tag = serializers.CharField(source='female.tag_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Mating
        fields = [
            'id', 'owner', 'male', 'male_name', 'male_tag',
            'female', 'female_name', 'female_tag',
            'mating_date', 'status', 'status_display',
            'palpation_date', 'palpation_done_at', 'nest_box_date', 'expected_kindling_date',
            'notes', 'client_uuid', 'is_deleted', 'created_at', 'updated_at', 'created_by_user'
        ]
        # La palpation se confirme par l'action `palpation`, l'échec par l'action `cancel`
        read_only_fields = ['id', 'owner', 'palpation_done_at', 'is_deleted', 'created_at', 'updated_at', 'created_by_user']

    def validate(self, attrs):
        male = attrs.get('male', getattr(self.instance, 'male', None))
        female = attrs.get('female', getattr(self.instance, 'female', None))
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        for rabbit in (male, female):
            if rabbit is not None and user is not None and rabbit.owner_id != user.id:
                raise serializers.ValidationError("Ce lapin n'appartient pas à votre élevage.")
        return attrs


class LitterSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les portées / mises bas, avec le suivi des lapereaux
    (restants au nid, âge, sevrage prévu et effectué) et l'emplacement de la mère.
    """
    mother_name = serializers.CharField(source='mother.name', read_only=True)
    mother_tag = serializers.CharField(source='mother.tag_number', read_only=True)
    father_name = serializers.CharField(source='father.name', read_only=True)
    father_tag = serializers.CharField(source='father.tag_number', read_only=True)
    total_born = serializers.IntegerField(read_only=True)
    kits_remaining = serializers.IntegerField(read_only=True)
    age_days = serializers.IntegerField(read_only=True)
    days_until_weaning = serializers.IntegerField(read_only=True)
    weaning_status = serializers.CharField(read_only=True)
    mother_cage = serializers.SerializerMethodField()
    mother_compartment = serializers.IntegerField(source='mother.compartment_number', read_only=True)

    class Meta:
        model = Litter
        fields = [
            'id', 'owner', 'mating', 'mother', 'mother_name', 'mother_tag',
            'father', 'father_name', 'father_tag',
            'mother_cage', 'mother_compartment',
            'birth_date', 'born_alive', 'still_born', 'died_count', 'total_born',
            'weaned_count', 'weaned_at', 'weaning_date',
            'kits_remaining', 'age_days', 'days_until_weaning', 'weaning_status',
            'notes', 'client_uuid', 'is_deleted', 'created_at', 'updated_at', 'created_by_user'
        ]
        # Le sevrage (`weaned_count`, `weaned_at`) ne se modifie que par l'action `wean`
        read_only_fields = [
            'id', 'owner', 'total_born', 'weaned_count', 'weaned_at',
            'kits_remaining', 'age_days', 'days_until_weaning', 'weaning_status',
            'is_deleted', 'created_at', 'updated_at', 'created_by_user'
        ]
        # La mère et le père sont déduits de l'accouplement sélectionné
        extra_kwargs = {'mother': {'required': False}, 'father': {'required': False}}

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_mother_cage(self, obj):
        return obj.mother.cage.name if obj.mother.cage_id else None

    def validate_mating(self, mating):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if mating is not None and user is not None and mating.owner_id != user.id:
            raise serializers.ValidationError("Cet accouplement n'appartient pas à votre élevage.")
        return mating

    def validate(self, attrs):
        mating = attrs.get('mating')
        if mating is not None:
            attrs['mother'] = mating.female
            attrs['father'] = mating.male
        elif self.instance is None and not attrs.get('mother'):
            raise serializers.ValidationError(
                {'mating': "Sélectionnez l'accouplement concerné par cette mise bas."}
            )

        # La date de mise bas peut être saisie après coup, mais pas dans le futur ni avant la saillie
        birth_date = attrs.get('birth_date')
        if birth_date is not None:
            if birth_date > timezone.localdate():
                raise serializers.ValidationError({'birth_date': "La date de mise bas ne peut pas être dans le futur."})
            linked = attrs.get('mating', getattr(self.instance, 'mating', None))
            if linked is not None and birth_date < linked.earliest_kindling_date:
                raise serializers.ValidationError({
                    'birth_date': (
                        f"Saillie du {linked.mating_date:%d/%m/%Y} : la mise bas ne peut pas avoir lieu "
                        f"avant le {linked.earliest_kindling_date:%d/%m/%Y} ({linked.MIN_GESTATION_DAYS} jours minimum)."
                    )
                })

        # Les effectifs corrigés doivent rester cohérents avec les sevrés et morts déjà enregistrés
        born_alive = attrs.get('born_alive', getattr(self.instance, 'born_alive', 0))
        died = attrs.get('died_count', getattr(self.instance, 'died_count', 0))
        weaned = (getattr(self.instance, 'weaned_count', None) or 0)
        if born_alive < weaned + died:
            raise serializers.ValidationError({
                'born_alive': (
                    f"{weaned} sevré(s) et {died} mort(s) au nid : "
                    f"il ne peut pas y avoir moins de {weaned + died} né(s) vivant(s)."
                )
            })
        return attrs


class CareTreatmentSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les types de soins (vaccin, vitamine, déparasitant...) et leur durée de renouvellement.
    """
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    records_count = serializers.SerializerMethodField()

    class Meta:
        model = CareTreatment
        fields = [
            'id', 'owner', 'name', 'category', 'category_display', 'renewal_days',
            'notes', 'records_count', 'client_uuid', 'is_deleted', 'created_at', 'updated_at', 'created_by_user'
        ]
        read_only_fields = ['id', 'owner', 'records_count', 'is_deleted', 'created_at', 'updated_at', 'created_by_user']

    @extend_schema_field(serializers.IntegerField())
    def get_records_count(self, obj):
        return obj.records.filter(is_deleted=False).count()

    def validate_name(self, value):
        value = value.strip()
        user = getattr(self.context.get('request'), 'user', None)
        duplicates = CareTreatment.objects.filter(owner=user, name__iexact=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if user is not None and duplicates.exists():
            raise serializers.ValidationError("Un type de soin porte déjà ce nom.")
        return value


class CareRecordSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les soins effectués : type de soin, date, motif et lapins soignés.
    `next_due_date` est calculé (date + durée de renouvellement) sauf s'il est fourni.
    """
    treatment_name = serializers.CharField(source='treatment.name', read_only=True)
    treatment_category = serializers.CharField(source='treatment.category', read_only=True)
    treatment_category_display = serializers.CharField(source='treatment.get_category_display', read_only=True)
    renewal_days = serializers.IntegerField(source='treatment.renewal_days', read_only=True)
    days_until_due = serializers.IntegerField(read_only=True)
    rabbits_detail = serializers.SerializerMethodField()

    class Meta:
        model = CareRecord
        fields = [
            'id', 'owner', 'treatment', 'treatment_name', 'treatment_category',
            'treatment_category_display', 'renewal_days',
            'rabbits', 'rabbits_detail', 'date', 'purpose',
            'next_due_date', 'days_until_due', 'notes', 'client_uuid',
            'created_at', 'updated_at', 'created_by_user'
        ]
        read_only_fields = ['id', 'owner', 'days_until_due', 'is_deleted', 'created_at', 'updated_at', 'created_by_user']
        extra_kwargs = {
            'rabbits': {'error_messages': {'empty': "Sélectionnez au moins un lapin soigné."}},
        }

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_rabbits_detail(self, obj):
        return [
            {'id': r.id, 'name': r.name, 'tag_number': r.tag_number, 'gender': r.gender}
            for r in obj.rabbits.all()
        ]

    def _user(self):
        return getattr(self.context.get('request'), 'user', None)

    def validate_treatment(self, treatment):
        user = self._user()
        if user is not None and treatment.owner_id != user.id:
            raise serializers.ValidationError("Ce type de soin n'existe pas dans votre élevage.")
        return treatment

    def validate_rabbits(self, rabbits):
        if not rabbits:
            raise serializers.ValidationError("Sélectionnez au moins un lapin soigné.")
        user = self._user()
        if user is not None and any(r.owner_id != user.id for r in rabbits):
            raise serializers.ValidationError("Un des lapins n'appartient pas à votre élevage.")
        return rabbits

    def validate(self, attrs):
        treatment = attrs.get('treatment', getattr(self.instance, 'treatment', None))
        date = attrs.get('date', getattr(self.instance, 'date', None))

        if date is not None and date > timezone.localdate():
            raise serializers.ValidationError({'date': "Un soin effectué ne peut pas être daté dans le futur."})

        if 'next_due_date' in attrs:
            due = attrs['next_due_date']
            if due is not None and date is not None and due < date:
                raise serializers.ValidationError(
                    {'next_due_date': "Le renouvellement ne peut pas précéder le soin."}
                )
        elif treatment is not None and date is not None and (
            self.instance is None or 'date' in attrs or 'treatment' in attrs
        ):
            attrs['next_due_date'] = CareRecord.compute_next_due_date(treatment, date)
        return attrs


class CareEventSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les soins et rappels vétérinaires.
    """
    rabbit_name = serializers.CharField(source='rabbit.name', read_only=True)
    rabbit_tag = serializers.CharField(source='rabbit.tag_number', read_only=True)
    care_type_display = serializers.CharField(source='get_care_type_display', read_only=True)

    class Meta:
        model = CareEvent
        fields = [
            'id', 'owner', 'rabbit', 'rabbit_name', 'rabbit_tag',
            'care_type', 'care_type_display', 'title', 'date',
            'reminder_date', 'is_completed', 'notes', 'client_uuid',
            'created_at', 'updated_at', 'created_by_user'
        ]
        read_only_fields = ['id', 'owner', 'is_deleted', 'created_at', 'updated_at', 'created_by_user']


class FinanceTransactionSerializer(serializers.ModelSerializer, UserActionMixinSerializer):
    """
    Sérialiseur pour les flux financiers (entrées et dépenses).
    """
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)

    class Meta:
        model = FinanceTransaction
        fields = [
            'id', 'owner', 'transaction_type', 'transaction_type_display',
            'title', 'amount', 'date', 'category', 'notes', 'client_uuid',
            'created_at', 'updated_at', 'created_by_user'
        ]
        read_only_fields = ['id', 'owner', 'is_deleted', 'created_at', 'updated_at', 'created_by_user']

