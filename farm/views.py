from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, serializers as drf_serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from core.utils import CustomViewSet, build_success_response, build_error_response
from .models import (
    Breed, Cage, Rabbit, RabbitImage, Mating, Litter,
    CareTreatment, CareRecord, CareEvent, FinanceTransaction,
)
from .serializers import (
    BreedSerializer,
    CageSerializer,
    RabbitSerializer,
    MatingSerializer,
    LitterSerializer,
    CareTreatmentSerializer,
    CareRecordSerializer,
    CareEventSerializer,
    FinanceTransactionSerializer
)


@extend_schema(tags=['Cheptel & Lapins'])
class BreedViewSet(CustomViewSet):
    """
    ViewSet pour consulter et gérer les races de lapins.
    Accessible en lecture pour tous, réservé aux utilisateurs authentifiés pour modification.
    """
    queryset = Breed.objects.all()
    serializer_class = BreedSerializer
    user_field_lookup = None  # Les races sont partagées
    filterset_fields = {
        'name': ['exact', 'icontains'],
    }
    search_fields = ['name', 'description']
    export_columns = [
        ('ID', ['id']),
        ('Nom de la race', ['name']),
        ('Durée moyenne gestation (jours)', ['average_gestation_days']),
        ('Description', ['description']),
    ]
    export_filename = "races_lapins.xlsx"

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


@extend_schema(tags=['Cages'])
class CageViewSet(CustomViewSet):
    """
    ViewSet pour gérer les cages de l'élevage et leur nombre de loges.
    Chaque cage renvoie l'état de ses loges (libre ou occupée par un lapin).
    """
    queryset = Cage.objects.all().prefetch_related('rabbits', 'rabbits__litters_as_mother')
    serializer_class = CageSerializer
    user_field_lookup = 'owner'

    filterset_fields = {
        'name': ['exact', 'icontains'],
        'location': ['exact', 'icontains'],
        'rows_count': ['exact', 'gte', 'lte'],
        'columns_count': ['exact', 'gte', 'lte'],
    }
    search_fields = ['name', 'location', 'notes']
    export_columns = [
        ('ID', ['id']),
        ('Cage', ['name']),
        ('Emplacement', ['location']),
        ('Lignes', ['rows_count']),
        ('Colonnes', ['columns_count']),
        ('Nombre de loges', ['compartments_count']),
        ('Loges occupées', ['occupied_count']),
    ]
    export_filename = "cages.xlsx"


@extend_schema(tags=['Cheptel & Lapins'])
class RabbitViewSet(CustomViewSet):
    """
    ViewSet complet pour la gestion des lapins reproducteurs,
    leur statut, généalogie et historique.
    """
    queryset = Rabbit.objects.all().select_related('breed', 'sire', 'dam', 'cage').prefetch_related('litters_as_mother')
    serializer_class = RabbitSerializer
    user_field_lookup = 'owner'

    filterset_fields = {
        'gender': ['exact'],
        'status': ['exact'],
        'breed': ['exact'],
        'color': ['exact', 'icontains'],
        'cage_number': ['exact', 'icontains'],
        'cage': ['exact'],
        'tag_number': ['exact', 'icontains'],
    }
    search_fields = ['name', 'tag_number', 'color', 'cage_number', 'notes', 'breed__name']
    export_columns = [
        ('ID', ['id']),
        ('Nom', ['name']),
        ('Bague / N°', ['tag_number']),
        ('Sexe', ['gender_display']),
        ('Race', ['breed_name']),
        ('Statut', ['status_display']),
        ('Cage', ['cage_number']),
        ('Père', ['sire_name']),
        ('Mère', ['dam_name']),
        ('Poids (kg)', ['weight_kg']),
    ]
    export_filename = "lapins.xlsx"

    @action(detail=True, methods=['get'])
    def genealogy(self, request, pk=None):
        """
        Retourne l'arbre généalogique du lapin sur 3 générations (parents et grands-parents).
        """
        rabbit = self.get_object(pk=pk)

        def serialize_rabbit_summary(r):
            if not r:
                return None
            return {
                'id': r.id,
                'name': r.name,
                'tag_number': r.tag_number,
                'gender': r.gender,
                'breed': r.breed.name if r.breed else None,
                'photo': r.photo.url if r.photo else None,
            }

        sire = rabbit.sire
        dam = rabbit.dam

        paternal_grandsire = sire.sire if sire else None
        paternal_granddam = sire.dam if sire else None
        maternal_grandsire = dam.sire if dam else None
        maternal_granddam = dam.dam if dam else None

        data = {
            'rabbit': serialize_rabbit_summary(rabbit),
            'parents': {
                'sire': serialize_rabbit_summary(sire),
                'dam': serialize_rabbit_summary(dam),
            },
            'grandparents': {
                'paternal_grandsire': serialize_rabbit_summary(paternal_grandsire),
                'paternal_granddam': serialize_rabbit_summary(paternal_granddam),
                'maternal_grandsire': serialize_rabbit_summary(maternal_grandsire),
                'maternal_granddam': serialize_rabbit_summary(maternal_granddam),
            }
        }
        return Response(build_success_response(
            data=data,
            message_code='genealogy-loaded',
            message_default='Arbre généalogique chargé avec succès'
        ))

    @action(detail=True, methods=['post'])
    def upload_photo(self, request, pk=None):
        """
        Téléverse une photo pour un lapin (avec paramètre optionnel is_primary=true).
        """
        rabbit = self.get_object(pk=pk)
        file = request.FILES.get('photo') or request.FILES.get('image')
        if not file:
            return Response(build_error_response(
                message_default="Aucun fichier photo fourni",
                message_details="Le champ 'photo' ou 'image' est obligatoire"
            ), status=status.HTTP_400_BAD_REQUEST)

        is_primary = str(request.data.get('is_primary', 'false')).lower() in ['true', '1']
        caption = request.data.get('caption', '')


        # Enregistrer dans la galerie d'images
        rabbit_image = RabbitImage.objects.create(
            rabbit=rabbit,
            image=file,
            caption=caption,
            is_primary=is_primary or (rabbit.images.count() == 0)
        )

        if is_primary or not rabbit.photo:
            rabbit.photo = rabbit_image.image
            rabbit.save(update_fields=['photo', 'updated_at'])
            rabbit.images.exclude(id=rabbit_image.id).update(is_primary=False)

        return Response(build_success_response(
            data=RabbitSerializer(rabbit, context={'request': request}).data,
            message_code='photo-uploaded',
            message_default='Photo ajoutée avec succès'
        ), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='images/(?P<image_id>[^/.]+)/set-primary')
    def set_primary_photo(self, request, pk=None, image_id=None):
        """
        Définit une photo de la galerie comme photo principale du lapin.
        """
        rabbit = self.get_object(pk=pk)
        try:
            target_image = rabbit.images.get(id=image_id)
        except RabbitImage.DoesNotExist:
            return Response(build_error_response(
                message_default="Photo introuvable dans la galerie de ce lapin"
            ), status=status.HTTP_404_NOT_FOUND)

        rabbit.images.all().update(is_primary=False)
        target_image.is_primary = True
        target_image.save(update_fields=['is_primary'])

        # Mettre à jour la photo principale sur le modèle Rabbit
        rabbit.photo = target_image.image
        rabbit.save(update_fields=['photo', 'updated_at'])

        return Response(build_success_response(
            data=RabbitSerializer(rabbit, context={'request': request}).data,
            message_code='photo-updated',
            message_default='Photo principale mise à jour avec succès'
        ))

    @action(detail=True, methods=['delete'], url_path='images/(?P<image_id>[^/.]+)')
    def delete_photo(self, request, pk=None, image_id=None):
        """
        Supprime une photo de la galerie du lapin.
        """
        rabbit = self.get_object(pk=pk)
        try:
            target_image = rabbit.images.get(id=image_id)
        except RabbitImage.DoesNotExist:
            return Response(build_error_response(
                message_default="Photo introuvable dans la galerie de ce lapin"
            ), status=status.HTTP_404_NOT_FOUND)

        was_primary = target_image.is_primary
        target_image.delete()

        # Si c'était la photo principale, en choisir une autre ou None
        if was_primary:
            next_img = rabbit.images.first()
            if next_img:
                next_img.is_primary = True
                next_img.save(update_fields=['is_primary'])
                rabbit.photo = next_img.image
            else:
                rabbit.photo = None
            rabbit.save(update_fields=['photo', 'updated_at'])

        return Response(build_success_response(
            data=RabbitSerializer(rabbit, context={'request': request}).data,
            message_code='photo-deleted',
            message_default='Photo supprimée avec succès'
        ))


@extend_schema(tags=['Accouplements & Saillies'])
class MatingViewSet(CustomViewSet):
    """
    ViewSet pour gérer les accouplements et calculer automatiquement
    les dates de palpation (J+12), de boîte à nid (J+28) et de mise bas (J+31).
    """
    queryset = Mating.objects.all().select_related('male', 'female')
    serializer_class = MatingSerializer
    user_field_lookup = 'owner'

    filterset_fields = {
        'status': ['exact'],
        'male': ['exact'],
        'female': ['exact'],
        'mating_date': ['exact', 'gte', 'lte'],
    }
    search_fields = ['male__name', 'female__name', 'male__tag_number', 'female__tag_number', 'notes']
    export_columns = [
        ('ID', ['id']),
        ('Date saillie', ['mating_date']),
        ('Mâle', ['male_name']),
        ('Femelle', ['female_name']),
        ('Statut', ['status_display']),
        ('Date palpation', ['palpation_date']),
        ('Date nid', ['nest_box_date']),
        ('Date mise bas prévue', ['expected_kindling_date']),
    ]
    export_filename = "accouplements.xlsx"

    def perform_create_calculation(self, validated_data):
        mating_date = validated_data.get('mating_date')
        if mating_date:
            if not validated_data.get('palpation_date'):
                validated_data['palpation_date'] = mating_date + timedelta(days=12)
            if not validated_data.get('nest_box_date'):
                validated_data['nest_box_date'] = mating_date + timedelta(days=28)
            if not validated_data.get('expected_kindling_date'):
                validated_data['expected_kindling_date'] = mating_date + timedelta(days=31)

    def create(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={'request': request, 'extra_args': {'user': request.user}}
        )
        if serializer.is_valid():
            self.perform_create_calculation(serializer.validated_data)
            instance = serializer.save(owner=request.user)

            # Mettre à jour le statut de la femelle en "En gestation"
            female = instance.female
            if female and female.status != Rabbit.Status.PREGNANT:
                female.status = Rabbit.Status.PREGNANT
                female.save(update_fields=['status'])

            return Response(build_success_response(
                data=serializer.data,
                message_code='data-saved',
                message_default='Accouplement enregistré avec les prédictions calculées'
            ), status=status.HTTP_201_CREATED)

        return Response(build_error_response(
            message_default="Erreur d'enregistrement",
            errors=serializer.errors
        ), status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _has_active_mating(female, exclude_id=None):
        active = Mating.objects.filter(
            female=female,
            status__in=[Mating.Status.PENDING, Mating.Status.CONFIRMED],
        )
        if exclude_id is not None:
            active = active.exclude(pk=exclude_id)
        return active.exists()

    def _release_female(self, female, exclude_id=None):
        """Remet la femelle en reproductrice active si elle n'a plus de gestation en cours."""
        if female.status == Rabbit.Status.PREGNANT and not self._has_active_mating(female, exclude_id):
            female.status = Rabbit.Status.ACTIVE
            female.save(update_fields=['status'])

    def update(self, request, pk=None, *args, **kwargs):
        instance = self.get_object(pk=pk)
        old_female = instance.female
        old_date = instance.mating_date

        serializer = self.serializer_class(
            instance=instance,
            data=request.data,
            partial=True,
            context={'request': request, 'extra_args': {'user': request.user}}
        )
        if not serializer.is_valid():
            return Response(build_error_response(
                message_default='Erreur lors de la validation des données.',
                errors=serializer.errors
            ), status=status.HTTP_400_BAD_REQUEST)

        # Recalculer les échéances si la date de saillie change (sauf dates fournies explicitement)
        data = serializer.validated_data
        new_date = data.get('mating_date')
        if new_date and new_date != old_date:
            for field, days in (('palpation_date', 12), ('nest_box_date', 28), ('expected_kindling_date', 31)):
                if field not in request.data:
                    data[field] = new_date + timedelta(days=days)

        instance = serializer.save()

        # Synchroniser le statut des femelles concernées
        female = instance.female
        is_active = instance.status in (Mating.Status.PENDING, Mating.Status.CONFIRMED)
        if female.pk != old_female.pk:
            self._release_female(old_female, exclude_id=instance.pk)
        if is_active:
            if female.status != Rabbit.Status.PREGNANT:
                female.status = Rabbit.Status.PREGNANT
                female.save(update_fields=['status'])
        else:
            self._release_female(female, exclude_id=instance.pk)

        return Response(build_success_response(
            data=serializer.data,
            message_code='data-saved',
            message_default='Accouplement mis à jour avec succès'
        ), status=status.HTTP_200_OK)

    def _mating_response(self, request, mating, message):
        mating = self.get_queryset().get(pk=mating.pk)
        return Response(build_success_response(
            data=self.serializer_class(mating, context={'request': request}).data,
            message_code='data-saved',
            message_default=message,
        ), status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def palpation(self, request, pk=None):
        """
        Confirme que la palpation a été effectuée (gestation confirmée) à la date `done_at`
        (aujourd'hui par défaut). Uniquement pour une saillie en attente de palpation.
        """
        mating = self.get_object(pk=pk)
        if mating.status != Mating.Status.PENDING:
            return Response(build_error_response(
                message_default='Action impossible',
                errors={'status': "Cette saillie n'est plus en attente de palpation."}
            ), status=status.HTTP_400_BAD_REQUEST)

        done_at = timezone.localdate()
        if request.data.get('done_at'):
            try:
                done_at = drf_serializers.DateField().to_internal_value(request.data.get('done_at'))
            except drf_serializers.ValidationError:
                return Response(build_error_response(
                    message_default='Date invalide', errors={'done_at': 'Date invalide.'}
                ), status=status.HTTP_400_BAD_REQUEST)
        if done_at < mating.mating_date or done_at > timezone.localdate():
            return Response(build_error_response(
                message_default='Date invalide',
                errors={'done_at': "La palpation doit avoir lieu entre la saillie et aujourd'hui."}
            ), status=status.HTTP_400_BAD_REQUEST)

        mating.status = Mating.Status.CONFIRMED
        mating.palpation_done_at = done_at
        mating.save(update_fields=['status', 'palpation_done_at', 'updated_at'])
        return self._mating_response(request, mating, 'Palpation enregistrée : gestation confirmée')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Annule la saillie (échec constaté, par exemple à la palpation) : elle passe à « infructueux »
        et la femelle redevient disponible. `reason` (facultatif) est ajouté aux notes.
        """
        mating = self.get_object(pk=pk)
        if mating.status not in (Mating.Status.PENDING, Mating.Status.CONFIRMED):
            return Response(build_error_response(
                message_default='Action impossible',
                errors={'status': "Cette saillie est déjà terminée."}
            ), status=status.HTTP_400_BAD_REQUEST)

        mating.status = Mating.Status.FAILED
        reason = (request.data.get('reason') or '').strip()
        if reason:
            mating.notes = f"{mating.notes}\nÉchec : {reason}" if mating.notes else f"Échec : {reason}"
        mating.save(update_fields=['status', 'notes', 'updated_at'])
        self._release_female(mating.female, exclude_id=mating.pk)
        return self._mating_response(request, mating, 'Saillie annulée')


@extend_schema(tags=['Mises bas & Lapereaux'])
class LitterViewSet(CustomViewSet):
    """
    ViewSet pour enregistrer les mises bas et suivre les portées.
    """
    queryset = Litter.objects.all().select_related('mother', 'mother__cage', 'father', 'mating')
    serializer_class = LitterSerializer
    user_field_lookup = 'owner'

    filterset_fields = {
        'mother': ['exact'],
        'father': ['exact'],
        'birth_date': ['exact', 'gte', 'lte'],
    }
    search_fields = ['mother__name', 'father__name', 'notes']
    export_columns = [
        ('ID', ['id']),
        ('Date mise bas', ['birth_date']),
        ('Mère', ['mother_name']),
        ('Père', ['father_name']),
        ('Nés vivants', ['born_alive']),
        ('Mort-nés', ['still_born']),
        ('Total nés', ['total_born']),
        ('Sevrés', ['weaned_count']),
        ('Date sevrage', ['weaning_date']),
    ]
    export_filename = "mises_bas.xlsx"

    def create(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={'request': request, 'extra_args': {'user': request.user}}
        )
        if serializer.is_valid():
            birth_date = serializer.validated_data.get('birth_date')
            if birth_date and not serializer.validated_data.get('weaning_date'):
                serializer.validated_data['weaning_date'] = birth_date + timedelta(days=45)

            instance = serializer.save(owner=request.user)

            # Mettre à jour la mère en "En allaitement"
            mother = instance.mother
            if mother:
                mother.status = Rabbit.Status.LACTATING
                mother.save(update_fields=['status'])

            # Marquer l'accouplement lié comme mise bas réalisée
            if instance.mating:
                instance.mating.status = Mating.Status.KINDLED
                instance.mating.save(update_fields=['status'])

            return Response(build_success_response(
                data=serializer.data,
                message_code='data-saved',
                message_default='Mise bas enregistrée avec succès'
            ), status=status.HTTP_201_CREATED)

        return Response(build_error_response(
            message_default="Erreur d'enregistrement",
            errors=serializer.errors
        ), status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def wean(self, request, pk=None):
        """
        Enregistre un sevrage (total ou partiel) : `count` lapereaux, à la date `weaned_at`
        (aujourd'hui par défaut). Si `rabbits` est fourni (une entrée {name, tag_number, gender,
        color?} par lapereau sevré), leurs fiches sont créées, rattachées à la mère et au père,
        et placées dans la même loge que la mère.
        """
        litter = self.get_object(pk=pk)
        remaining = litter.kits_remaining
        data = request.data

        try:
            count = int(data.get('count'))
        except (TypeError, ValueError):
            return self._wean_error({'count': 'Indiquez le nombre de lapereaux sevrés.'})
        if count < 1 or count > remaining:
            return self._wean_error({
                'count': f"Entre 1 et {remaining} lapereau(x) restent à sevrer." if remaining
                else "Tous les lapereaux de cette portée sont déjà sevrés."
            })

        weaned_at = timezone.localdate()
        if data.get('weaned_at'):
            try:
                weaned_at = drf_serializers.DateField().to_internal_value(data.get('weaned_at'))
            except drf_serializers.ValidationError:
                return self._wean_error({'weaned_at': 'Date invalide.'})
        if weaned_at < litter.birth_date:
            return self._wean_error({'weaned_at': 'Le sevrage ne peut pas précéder la naissance.'})

        kits = data.get('rabbits') or []
        if kits and len(kits) != count:
            return self._wean_error({'rabbits': f"{count} fiche(s) attendue(s), {len(kits)} reçue(s)."})

        mother = litter.mother
        in_cage = bool(mother.cage_id and mother.compartment_number)
        try:
            with transaction.atomic():
                created = []
                errors = {}
                for index, kit in enumerate(kits):
                    payload = {
                        'name': kit.get('name'),
                        'tag_number': kit.get('tag_number'),
                        'gender': kit.get('gender'),
                        'color': kit.get('color') or mother.color,
                        'birth_date': litter.birth_date,
                        'sire': litter.father_id,
                        'dam': mother.id,
                        'breed': mother.breed_id,
                        # ils sont encore dans la loge de leur mère au moment du sevrage
                        'cage': in_cage and mother.cage_id or None,
                        'compartment_number': in_cage and mother.compartment_number or None,
                        'status': Rabbit.Status.ACTIVE,
                    }
                    serializer = RabbitSerializer(data=payload, context={'request': request})
                    if serializer.is_valid():
                        created.append(serializer.save(owner=request.user))
                    else:
                        errors[str(index)] = serializer.errors
                if errors:
                    raise ValueError(errors)

                litter.weaned_count = (litter.weaned_count or 0) + count
                litter.weaned_at = weaned_at
                litter.save(update_fields=['weaned_count', 'weaned_at', 'updated_at'])

                # Portée entièrement sevrée : la mère n'allaite plus (sauf autre portée au nid)
                if litter.kits_remaining == 0 and mother.status == Rabbit.Status.LACTATING:
                    still_nursing = any(
                        other.kits_remaining > 0
                        for other in mother.litters_as_mother.filter(is_deleted=False).exclude(pk=litter.pk)
                    )
                    if not still_nursing:
                        mother.status = Rabbit.Status.ACTIVE
                        mother.save(update_fields=['status'])
        except ValueError as exc:
            return self._wean_error({'rabbits': exc.args[0]})

        litter = self.get_queryset().get(pk=litter.pk)
        return Response(build_success_response(
            data={
                'litter': self.serializer_class(litter, context={'request': request}).data,
                'rabbits': RabbitSerializer(created, many=True, context={'request': request}).data,
            },
            message_code='litter-weaned',
            message_default=f'{count} lapereau(x) sevré(s)'
        ), status=status.HTTP_200_OK)

    @staticmethod
    def _wean_error(errors):
        return Response(build_error_response(
            message_default='Sevrage impossible', errors=errors
        ), status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Soins & Entretien'])
class CareTreatmentViewSet(CustomViewSet):
    """
    Types de soins de l'élevage (vaccin, vitamine, déparasitant...) avec leur durée avant renouvellement.
    """
    queryset = CareTreatment.objects.all()
    serializer_class = CareTreatmentSerializer
    user_field_lookup = 'owner'

    filterset_fields = {
        'category': ['exact'],
        'name': ['exact', 'icontains'],
    }
    search_fields = ['name', 'notes']

    def destroy(self, request, pk=None):
        treatment = self.get_object(pk=pk)
        if treatment.records.filter(is_deleted=False).exists():
            return Response(build_error_response(
                message_default="Suppression impossible",
                message_details="Ce type de soin a déjà été utilisé : supprimez d'abord les soins enregistrés.",
                errors={'treatment': "Ce type de soin est utilisé dans l'historique des soins."}
            ), status=status.HTTP_400_BAD_REQUEST)
        treatment.is_deleted = True
        treatment.deleted_at = timezone.now()
        treatment.save(update_fields=['is_deleted', 'deleted_at'])
        return Response(build_success_response(
            data={}, message_code='success', message_default='Données supprimées avec succès.'
        ))


@extend_schema(tags=['Soins & Entretien'])
class CareRecordViewSet(CustomViewSet):
    """
    Soins effectués (date, motif, lapins soignés) et rappels des prochains soins.
    """
    queryset = CareRecord.objects.all().select_related('treatment').prefetch_related('rabbits')
    serializer_class = CareRecordSerializer
    user_field_lookup = 'owner'

    filterset_fields = {
        'treatment': ['exact'],
        'rabbits': ['exact'],
        'date': ['exact', 'gte', 'lte'],
        'next_due_date': ['exact', 'gte', 'lte'],
    }
    search_fields = ['treatment__name', 'purpose', 'rabbits__name', 'rabbits__tag_number', 'notes']

    def _due_status(self, days):
        if days < 0:
            return 'overdue'
        return 'soon' if days <= CareRecord.SOON_DAYS else 'upcoming'

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """
        Prochains soins à effectuer, du plus urgent au plus lointain.
        Pour chaque lapin et chaque type de soin, seul le soin le plus récent compte : un renouvellement
        déjà fait fait disparaître l'échéance précédente. Les lapins réformés ne sont pas rappelés.
        Chaque entrée regroupe les lapins concernés par la même échéance ; `status` vaut
        `overdue` (en retard), `soon` (dans les 7 jours) ou `upcoming`.
        """
        today = timezone.localdate()
        latest_seen = set()
        items = []
        for record in self.get_queryset().order_by('-date', '-id'):
            due_rabbits = []
            for rabbit in record.rabbits.filter(is_deleted=False):
                key = (rabbit.id, record.treatment_id)
                if key in latest_seen:
                    continue
                latest_seen.add(key)
                if rabbit.status != Rabbit.Status.RETIRED:
                    due_rabbits.append(rabbit)
            if record.next_due_date is None or not due_rabbits:
                continue
            days = (record.next_due_date - today).days
            items.append({
                'record': record.id,
                'treatment': record.treatment_id,
                'treatment_name': record.treatment.name,
                'treatment_category': record.treatment.category,
                'purpose': record.purpose,
                'last_date': record.date,
                'due_date': record.next_due_date,
                'days_until_due': days,
                'status': self._due_status(days),
                'rabbits': [
                    {'id': r.id, 'name': r.name, 'tag_number': r.tag_number, 'gender': r.gender}
                    for r in due_rabbits
                ],
            })
        items.sort(key=lambda item: (item['due_date'], item['treatment_name']))
        return Response(build_success_response(
            data=items,
            message_code='care-upcoming-loaded',
            message_default='Prochains soins à effectuer'
        ))


@extend_schema(tags=['Carnet de Santé & Traitements'])
class CareEventViewSet(CustomViewSet):
    """
    ViewSet pour le carnet de santé, vaccins et traitements antiparasitaires.
    """
    queryset = CareEvent.objects.all().select_related('rabbit')
    serializer_class = CareEventSerializer
    user_field_lookup = 'owner'

    filterset_fields = {
        'care_type': ['exact'],
        'rabbit': ['exact'],
        'is_completed': ['exact'],
        'date': ['exact', 'gte', 'lte'],
    }
    search_fields = ['title', 'rabbit__name', 'rabbit__tag_number', 'notes']
    export_columns = [
        ('ID', ['id']),
        ('Date', ['date']),
        ('Lapin', ['rabbit_name']),
        ('Type de soin', ['care_type_display']),
        ('Titre', ['title']),
        ('Effectué', ['is_completed']),
        ('Rappel', ['reminder_date']),
    ]
    export_filename = "soins_lapins.xlsx"

    @action(detail=False, methods=['get'])
    def upcoming_reminders(self, request):
        """
        Retourne les rappels de soins à venir.
        """
        user = request.user
        upcoming = self.get_queryset().filter(
            reminder_date__isnull=False,
            is_completed=False
        ).order_by('reminder_date')

        serializer = self.get_serializer(upcoming, many=True)
        return Response(build_success_response(
            data=serializer.data,
            message_code='reminders-loaded',
            message_default='Rappels de soins à venir'
        ))


@extend_schema(tags=['Comptabilité & Finances'])
class FinanceTransactionViewSet(CustomViewSet):
    """
    ViewSet pour la comptabilité : entrées / ventes et dépenses d'exploitation.
    """
    queryset = FinanceTransaction.objects.all()
    serializer_class = FinanceTransactionSerializer
    user_field_lookup = 'owner'

    filterset_fields = {
        'transaction_type': ['exact'],
        'category': ['exact', 'icontains'],
        'date': ['exact', 'gte', 'lte'],
    }
    search_fields = ['title', 'category', 'notes']
    export_columns = [
        ('ID', ['id']),
        ('Date', ['date']),
        ('Type', ['transaction_type_display']),
        ('Titre', ['title']),
        ('Montant', ['amount']),
        ('Catégorie', ['category']),
    ]
    export_filename = "finances_elevage.xlsx"

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Fournit le total des revenus, des dépenses et le bénéfice net.
        """
        from django.db.models import Sum
        qs = self.get_queryset()

        total_income = qs.filter(transaction_type='income').aggregate(total=Sum('amount'))['total'] or 0
        total_expense = qs.filter(transaction_type='expense').aggregate(total=Sum('amount'))['total'] or 0
        balance = float(total_income) - float(total_expense)

        return Response(build_success_response(
            data={
                'total_income': float(total_income),
                'total_expense': float(total_expense),
                'balance': balance,
            },
            message_code='summary-loaded',
            message_default='Résumé financier calculé'
        ))
