import json
import logging
import uuid as uuid_lib
from copy import deepcopy
from datetime import datetime
from functools import wraps

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from openpyxl import Workbook
import pandas as pd
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_field

from authentication.models import Notification, User

logger = logging.getLogger(__name__)

BOOLEAN_LOOKUP = ['exact']
DATE_LOOKUP = ['exact', 'in', 'startswith', 'endswith', 'icontains', 'lte', 'gte']
NUMBER_LOOKUP = ['exact', 'lte', 'gte', 'lt', 'gt']
TEXT_LOOKUP = ['exact', 'in', 'startswith', 'endswith', 'icontains']


def notify(
    recipients,
    title,
    message="",
    notif_type="info",
    sender=None,
    related_object=None,
    expires_in=None,
    send_email_notification=False,
):
    """
    Envoie une notification in-app (et email si activé) à un ou plusieurs utilisateurs.
    """
    if not recipients:
        return None

    if not isinstance(recipients, (list, tuple)):
        recipients = [recipients]

    content_type = None
    object_id = None
    if related_object is not None:
        content_type = ContentType.objects.get_for_model(related_object.__class__)
        object_id = getattr(related_object, 'pk', None)

    notifications = []
    for recipient in recipients:
        notif = Notification.objects.create(
            sender=sender,
            recipient=recipient,
            title=title,
            message=message,
            notif_type=notif_type,
            content_type=content_type,
            object_id=object_id,
            expires_at=timezone.now() + expires_in if expires_in else None,
        )
        notifications.append(notif)

        if send_email_notification and getattr(recipient, 'email', None):
            try:
                send_mail(
                    subject=title,
                    message=message,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@lapinou.app'),
                    recipient_list=[recipient.email],
                    fail_silently=True,
                )
            except Exception as mail_err:
                logger.warning("Erreur lors de l'envoi de l'email de notification: %s", mail_err)

    return notifications


class UserActionMixinSerializer(serializers.Serializer):
    """
    Mixin serializer pour renvoyer le nom/prénom ou username de l'utilisateur
    qui a créé ou mis à jour une ressource.
    """
    created_by_user = serializers.SerializerMethodField('get_created_by_user')
    updated_by_user = serializers.SerializerMethodField('get_updated_by_user')

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_created_by_user(self, obj):
        user = getattr(obj, 'created_by', None) or getattr(obj, 'owner', None) or getattr(obj, 'author', None) or getattr(obj, 'seller', None)
        if user:
            name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
            return name or getattr(user, 'username', None)
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_updated_by_user(self, obj):
        user = getattr(obj, 'updated_by', None)
        if user:
            name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
            return name or getattr(user, 'username', None)
        return None


def get_extra_args(request):
    """
    Extrait les paramètres contextuels de la requête (utilisateur, filtres communs, date système).
    """
    date_system = None
    if hasattr(request, 'GET'):
        date_system = request.GET.get('date_system')
    if not date_system and hasattr(request, 'query_params'):
        date_system = request.query_params.get('date_system')

    if not date_system:
        date_system = datetime.today().strftime('%Y-%m-%d')

    return {
        'date_system': date_system,
        'user': getattr(request, 'user', None),
    }


def build_success_response(data, message_code="success", message_default="",
                           message_details="", extra_fields=None):
    """
    Construit une réponse de succès standardisée.
    """
    response = {
        "success": True,
        "message": {
            "code": message_code,
            "default": message_default,
            "details": message_details
        },
        "data": data
    }
    if extra_fields:
        response.update(extra_fields)
    return response


def build_error_response(message_default, message_details="", errors=None,
                         data=None, message_code="error"):
    """
    Construit une réponse d'erreur standardisée.
    """
    response = {
        "success": False,
        "message": {
            "code": message_code,
            "default": message_default,
            "details": message_details
        },
        "data": data if data is not None else {}
    }
    if errors:
        response["errors"] = errors
    return response


def build_paginated_response(data, paginate_info, message_code="search",
                             message_default="", message_details=""):
    """
    Construit une réponse paginée standardisée.
    """
    return {
        "success": True,
        "message": {
            "code": message_code,
            "default": message_default,
            "details": message_details
        },
        "data": data,
        "paginate": paginate_info
    }


class CustomPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(build_paginated_response(
            data=data,
            paginate_info={
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            },
            message_code='list',
            message_default='Informations chargées',
            message_details=''
        ))


def apply_query_filters(queryset, request, filterset_fields=None, search_fields=None):
    """
    Applique la recherche globale (search / global_search) et les filtres de colonnes
    dynamiques au queryset. Adapté aux modèles de Lapinou (lapins, saillies, soins, finances, annonces).
    """
    if queryset is None:
        return queryset

    search_query = (request.GET.get('global_search') or request.GET.get('search') or '').strip()

    candidate_lookups = []
    if search_fields:
        for f in search_fields:
            candidate_lookups.append(f"{f}__icontains" if '__' not in f else f)

    if filterset_fields:
        if isinstance(filterset_fields, dict):
            for field, lookups in filterset_fields.items():
                if any(lk in ['icontains', 'exact', 'startswith', 'endswith'] for lk in lookups):
                    base_field = field
                    if base_field.endswith('__exact'):
                        base_field = base_field[:-7]
                    candidate_lookups.append(f"{base_field}__icontains" if not base_field.endswith('__icontains') else base_field)
        elif isinstance(filterset_fields, (list, tuple)):
            for f in filterset_fields:
                candidate_lookups.append(f"{f}__icontains" if '__' not in f else f)

    try:
        model = queryset.model
        model_fields = {f.name: f for f in model._meta.fields}

        # Champs textuels fréquents du projet Lapinou
        lapinou_common_fields = [
            'name', 'tag_number', 'breed__name', 'color', 'cage_number',
            'title', 'category', 'notes', 'content', 'location',
            'first_name', 'last_name', 'username', 'email', 'farm_name'
        ]
        for cname in lapinou_common_fields:
            if '__' in cname:
                candidate_lookups.append(f"{cname}__icontains")
            elif cname in model_fields:
                candidate_lookups.append(f"{cname}__icontains")

        # Relations Lapinou
        fk_relationships = [
            ('rabbit', ['rabbit__name__icontains', 'rabbit__tag_number__icontains']),
            ('mother', ['mother__name__icontains', 'mother__tag_number__icontains']),
            ('father', ['father__name__icontains', 'father__tag_number__icontains']),
            ('male', ['male__name__icontains', 'male__tag_number__icontains']),
            ('female', ['female__name__icontains', 'female__tag_number__icontains']),
            ('sire', ['sire__name__icontains', 'sire__tag_number__icontains']),
            ('dam', ['dam__name__icontains', 'dam__tag_number__icontains']),
            ('owner', ['owner__username__icontains', 'owner__farm_name__icontains']),
            ('author', ['author__username__icontains', 'author__farm_name__icontains']),
            ('seller', ['seller__username__icontains', 'seller__farm_name__icontains']),
            ('post', ['post__title__icontains']),
        ]
        for fk_name, rel_lookups in fk_relationships:
            if fk_name in model_fields:
                candidate_lookups.extend(rel_lookups)

    except Exception as e:
        logger.debug(f"apply_query_filters model inspect warning: {e}")

    # Déduplication
    seen = set()
    deduped_lookups = []
    for lk in candidate_lookups:
        clean_lk = lk.replace('__exact__icontains', '__icontains')
        if clean_lk not in seen:
            seen.add(clean_lk)
            deduped_lookups.append(clean_lk)

    # Validation sûre des lookups
    valid_lookups = []
    for lk in deduped_lookups:
        try:
            queryset.filter(Q(**{lk: 'test'}))
            valid_lookups.append(lk)
        except Exception:
            pass

    # Traitement de global_search / search
    if search_query:
        q_global = Q()
        for lk in valid_lookups:
            q_global |= Q(**{lk: search_query})

        # Mots multiples (ex: prénom nom, tag et race)
        words = search_query.split()
        if len(words) >= 2:
            w1, w2 = words[0], words[1]
            for fn, ln in [('first_name__icontains', 'last_name__icontains'), ('name__icontains', 'tag_number__icontains')]:
                if fn in valid_lookups and ln in valid_lookups:
                    q_global |= (Q(**{fn: w1}) & Q(**{ln: w2}))
                    q_global |= (Q(**{fn: w2}) & Q(**{ln: w1}))

        clean_num = search_query.lstrip('0') or '0'
        if clean_num.isdigit():
            num_val = int(clean_num)
            for id_field in ['id', 'pk', 'rabbit__id', 'male__id', 'female__id']:
                try:
                    queryset.filter(Q(**{id_field: num_val}))
                    q_global |= Q(**{id_field: num_val})
                except Exception:
                    pass

        if q_global:
            try:
                queryset = queryset.filter(q_global).distinct()
            except Exception as e:
                logger.warning(f"Failed to apply search filter: {e}")

    # Traitement des filtres individuels
    system_keys = {
        'order_by', 'page', 'page_size', 'all', 'export', 'global_search',
        'search', 'search_type', 'tab', 'format'
    }
    for key, val in request.GET.items():
        if key in system_keys or val is None or val == '' or val in ['null', 'undefined', 'None']:
            continue
        val_str = str(val).strip()
        if val_str.lower() == 'true':
            typed_val = True
        elif val_str.lower() == 'false':
            typed_val = False
        else:
            typed_val = val_str

        applied = False

        # Intervalles (_min, _max, _from, _to)
        if key.endswith('_min'):
            base_key = key[:-4]
            try:
                queryset = queryset.filter(**{f"{base_key}__gte": typed_val})
                applied = True
            except Exception:
                pass
        elif key.endswith('_max'):
            base_key = key[:-4]
            try:
                queryset = queryset.filter(**{f"{base_key}__lte": typed_val})
                applied = True
            except Exception:
                pass
        elif key.endswith('_from'):
            base_key = key[:-5]
            try:
                queryset = queryset.filter(**{f"{base_key}__gte": typed_val})
                applied = True
            except Exception:
                pass
        elif key.endswith('_to'):
            base_key = key[:-3]
            try:
                queryset = queryset.filter(**{f"{base_key}__lte": typed_val})
                applied = True
            except Exception:
                pass

        if applied:
            continue

        try:
            queryset = queryset.filter(**{key: typed_val})
        except Exception:
            if '__' not in key and isinstance(typed_val, str):
                try:
                    queryset = queryset.filter(**{f"{key}__icontains": typed_val})
                except Exception:
                    pass

    return queryset


def dynamic_filter_with_pagination(
    filterset_fields=None,
    pagination_class=CustomPagination,
    serializer_class=None,
    ordering=('-id',),
    export_columns=None,
    export_filename="export.xlsx"
):
    """
    Décorateur pour filtrer, paginer et exporter une action de vue.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            queryset = func(self, request, *args, **kwargs)
            order_by = request.GET.get('order_by', '-id')
            export = request.GET.get('export', 'false').lower()
            all_data = request.GET.get('all', 'false').lower()
            extra_args = get_extra_args(request=request)

            if queryset is None:
                return Response(build_error_response(
                    message_default="No queryset returned from the view function",
                    message_details="The decorated view function must return a queryset",
                    message_code="no-queryset"
                ), status=status.HTTP_400_BAD_REQUEST)

            queryset = apply_query_filters(
                queryset=queryset,
                request=request,
                filterset_fields=filterset_fields,
                search_fields=getattr(self, 'search_fields', None)
            )

            try:
                queryset = queryset.order_by(order_by)
            except Exception:
                queryset = queryset.order_by('-id')

            serializer = serializer_class or getattr(self, 'serializer_class', None)

            # Export Excel
            if export == 'true' and export_columns:
                data = serializer(queryset, many=True, context={'extra_args': extra_args}).data
                wb = Workbook()
                ws = wb.active
                ws.title = "Export"

                headers = [col[0] for col in export_columns]
                ws.append(headers)

                def get_nested_value(obj, path):
                    for key in path:
                        if isinstance(obj, dict):
                            obj = obj.get(key)
                        else:
                            obj = getattr(obj, key, None)
                        if obj is None:
                            return None
                    return obj

                for item in data:
                    row = [get_nested_value(item, path) for _, path in export_columns]
                    ws.append(row)

                response = HttpResponse(
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = f'attachment; filename="{export_filename}"'
                wb.save(response)
                return response

            # All data (pas de pagination)
            if all_data == 'true':
                serialized = serializer(queryset, many=True, context={'extra_args': extra_args})
                return Response(build_success_response(
                    data=serialized.data,
                    message_code="search",
                    message_default="Données chargées",
                    message_details=""
                ))

            # Paginated response
            paginator = pagination_class()
            page = paginator.paginate_queryset(queryset, request)
            if page is not None:
                serialized = serializer(page, many=True, context={'extra_args': extra_args})
                return paginator.get_paginated_response(serialized.data)

            serialized = serializer(queryset, many=True, context={'extra_args': extra_args})
            return Response(build_success_response(
                data=serialized.data,
                message_code="search",
                message_default="Données chargées",
                message_details=""
            ))

        return wrapper
    return decorator


def column_letter_to_index(column_letter):
    """Convertit une lettre de colonne Excel (A, B, C...) en index 0-based."""
    result = 0
    for char in column_letter.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1


def excel_import_with_mapping(
    serializer_class,
    required_fields=None,
    optional_fields=None,
    validation_callback=None,
    success_message="Données importées avec succès",
    batch_size=100
):
    """
    Décorateur pour l'importation de fichiers Excel avec mapping de colonnes.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            try:
                extra_args = get_extra_args(request=request)

                if not request.user.is_authenticated:
                    return Response(build_error_response(
                        message_default='Authentification requise.',
                        message_details='',
                        errors={'not-auth': 'Authentification requise.'}
                    ), status=status.HTTP_401_UNAUTHORIZED)

                if 'excel_file' not in request.FILES:
                    return Response(build_error_response(
                        message_default='Fichier Excel requis.',
                        message_details='Veuillez fournir un fichier Excel via le paramètre excel_file',
                        errors={'missing-file': 'Fichier Excel requis.'}
                    ), status=status.HTTP_400_BAD_REQUEST)

                excel_file = request.FILES['excel_file']
                if not excel_file.name.endswith(('.xlsx', '.xls')):
                    return Response(build_error_response(
                        message_default='Format de fichier invalide.',
                        message_details='Seuls les fichiers .xlsx et .xls sont acceptés',
                        errors={'invalid-format': 'Format de fichier invalide.'}
                    ), status=status.HTTP_400_BAD_REQUEST)

                column_mapping = getattr(request, 'data', request.POST).get('column_mapping')
                if isinstance(column_mapping, bytes):
                    column_mapping = column_mapping.decode('utf-8')
                if isinstance(column_mapping, str):
                    try:
                        column_mapping = json.loads(column_mapping)
                    except json.JSONDecodeError as e:
                        return Response(build_error_response(
                            message_default='Mapping des colonnes invalide.',
                            message_details=str(e),
                            errors={'invalid-mapping': str(e)}
                        ), status=status.HTTP_400_BAD_REQUEST)

                if not column_mapping:
                    return Response(build_error_response(
                        message_default='Mapping des colonnes requis.',
                        message_details='Veuillez fournir le mapping entre colonnes Excel et champs du modèle',
                        errors={'missing-mapping': 'Mapping requis'}
                    ), status=status.HTTP_400_BAD_REQUEST)

                try:
                    df = pd.read_excel(excel_file)
                except Exception as e:
                    return Response(build_error_response(
                        message_default='Erreur lors de la lecture du fichier Excel.',
                        message_details=str(e),
                        errors={'read-error': str(e)}
                    ), status=status.HTTP_400_BAD_REQUEST)

                excel_columns = df.columns.tolist()
                converted_mapping = {}
                missing_columns = []

                for excel_col_letter, model_field in column_mapping.items():
                    try:
                        col_index = column_letter_to_index(excel_col_letter)
                        if col_index >= len(excel_columns):
                            missing_columns.append(excel_col_letter)
                        else:
                            actual_column_name = excel_columns[col_index]
                            converted_mapping[actual_column_name] = model_field
                    except Exception:
                        missing_columns.append(excel_col_letter)

                if missing_columns:
                    return Response(build_error_response(
                        message_default='Colonnes manquantes dans le fichier Excel.',
                        message_details=f'Colonnes non trouvées: {", ".join(missing_columns)}',
                        errors={'missing-columns': missing_columns}
                    ), status=status.HTTP_400_BAD_REQUEST)

                column_mapping = converted_mapping

                if required_fields:
                    missing_required = [f for f in required_fields if f not in column_mapping.values()]
                    if missing_required:
                        return Response(build_error_response(
                            message_default='Champs obligatoires manquants dans le mapping.',
                            message_details=f'Champs manquants: {", ".join(missing_required)}',
                            errors={'missing-required-fields': missing_required}
                        ), status=status.HTTP_400_BAD_REQUEST)

                processed_data = []
                errors = []
                for index, row in df.iterrows():
                    row_data = {}
                    for excel_col, model_field in column_mapping.items():
                        val = row[excel_col]
                        if pd.isna(val):
                            val = None
                        elif isinstance(val, str):
                            val = val.strip()
                            if val == '':
                                val = None
                        row_data[model_field] = val

                    # Assigner le propriétaire automatiquement si le modèle l'attend
                    if hasattr(self, 'queryset') and hasattr(self.queryset.model, 'owner'):
                        row_data['owner'] = request.user.pk

                    if validation_callback:
                        try:
                            val_res = validation_callback(row_data, index + 1)
                            if val_res is not True:
                                errors.append({'row': index + 1, 'error': val_res})
                                continue
                        except Exception as err:
                            errors.append({'row': index + 1, 'error': str(err)})
                            continue

                    processed_data.append(row_data)

                saved_count = 0
                validation_errors = []
                for i in range(0, len(processed_data), batch_size):
                    batch = processed_data[i:i + batch_size]
                    for idx, data in enumerate(batch):
                        try:
                            serializer = serializer_class(data=data, context={'extra_args': extra_args, 'request': request})
                            if serializer.is_valid():
                                serializer.save()
                                saved_count += 1
                            else:
                                validation_errors.append({'row': i + idx + 1, 'errors': serializer.errors})
                        except Exception as e:
                            validation_errors.append({'row': i + idx + 1, 'error': str(e)})

                response_data = build_success_response(
                    data={
                        "import_summary": {
                            "total_rows": len(df),
                            "processed_rows": len(processed_data),
                            "saved_rows": saved_count,
                            "errors_count": len(errors) + len(validation_errors),
                            "processing_errors": errors,
                            "validation_errors": validation_errors
                        }
                    },
                    message_code='import-completed',
                    message_default=success_message,
                    message_details=f'{saved_count} enregistrements importés avec succès'
                )
                if errors or validation_errors:
                    response_data["success"] = saved_count > 0
                    response_data["message"]["code"] = "import-with-errors"
                    response_data["message"]["default"] = f"Import avec {len(errors) + len(validation_errors)} erreurs"

                return Response(response_data, status=status.HTTP_200_OK)

            except Exception as e:
                logger.exception("Erreur lors de l'import: %s", e)
                return Response(build_error_response(
                    message_default="Une erreur est survenue lors de l'importation.",
                    message_details=str(e),
                    errors={'exception': str(e)}
                ), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return wrapper
    return decorator


def duplicate_object(instance, ignored_related=None):
    """
    Duplique une instance de modèle avec ses relations ForeignKey associées.
    """
    ignored_related = ignored_related or []
    model_name = instance._meta.model_name
    app_name = instance._meta.app_label
    model_of_duplication = apps.get_model(app_name, model_name)

    new_instance = deepcopy(instance)
    new_instance.pk = None
    new_instance.save()

    all_models = apps.get_models()
    for model in all_models:
        for field in model._meta.get_fields():
            if field.is_relation and field.many_to_one and field.related_model == model_of_duplication:
                related_name = field.related_query_name()
                if related_name not in ignored_related:
                    try:
                        related_objects = getattr(instance, related_name).all()
                        for rel_obj in related_objects:
                            new_rel = deepcopy(rel_obj)
                            new_rel.pk = None
                            setattr(new_rel, field.name, new_instance)
                            new_rel.save()
                    except Exception as e:
                        logger.debug("Duplication relation %s skipped: %s", related_name, e)

    return new_instance


class CustomViewSet(viewsets.ViewSet):
    """
    ViewSet standardisé et prêt à l'emploi pour le projet Lapinou.
    Offre :
    - Réponses structurées JSON standardisées (success, message, data, paginate)
    - Filtrage dynamique multi-critères et recherche textuelle / globale
    - Tri automatique
    - Exportation Excel directe via ?export=true ou action export_excel
    - Pagination uniforme avec CustomPagination
    - Sécurité des requêtes : filtre automatiquement par propriétaire (`owner` ou `author` ou `seller`)
      si l'utilisateur est authentifié et si le modèle possède l'un de ces champs.
    """
    permission_classes = [permissions.IsAuthenticated]

    queryset = None
    serializer_class = None
    read_only_serializer_class = None
    list_serializer_class = None
    filterset_fields = None
    search_fields = None
    export_columns = None
    export_filename = "export.xlsx"

    lookup_field = 'pk'
    lookup_url_kwarg = None
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    # Définir user_field_lookup = 'owner' (défaut) ou 'author'/'seller'/None pour isolation multi-éleveurs
    user_field_lookup = 'owner'

    def get_queryset(self):
        if self.queryset is not None:
            qs = self.queryset.all()
        else:
            raise AttributeError(
                f"'{self.__class__.__name__}' doit définir `queryset` ou redéfinir `get_queryset()`."
            )

        # Isolation des données par utilisateur/éleveur si applicable
        user = getattr(self.request, 'user', None)
        if user and user.is_authenticated and not user.is_superuser:
            model = qs.model
            model_fields = [f.name for f in model._meta.fields]

            lookup = getattr(self, 'user_field_lookup', 'owner')
            if lookup is None:
                # Ressource partagée (ex. fil communautaire, races, annonces) : aucune isolation
                pass
            elif lookup in model_fields:
                qs = qs.filter(**{lookup: user})
            elif 'owner' in model_fields:
                qs = qs.filter(owner=user)
            elif 'author' in model_fields:
                qs = qs.filter(author=user)
            elif 'seller' in model_fields:
                qs = qs.filter(seller=user)

        return qs

    def filter_queryset(self, queryset):
        return apply_query_filters(
            queryset=queryset,
            request=self.request,
            filterset_fields=getattr(self, 'filterset_fields', None),
            search_fields=getattr(self, 'search_fields', None)
        )

    def paginate_queryset(self, queryset):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        self.paginator = paginator
        return page

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def get_serializer_class(self):
        if self.list_serializer_class is not None:
            return self.list_serializer_class
        elif self.read_only_serializer_class is not None:
            return self.read_only_serializer_class
        return self.serializer_class

    def get_serializer_context(self):
        extra_args = get_extra_args(request=self.request) if hasattr(self, 'request') else {}
        return {
            'request': getattr(self, 'request', None),
            'format': getattr(self, 'format_kwarg', None),
            'view': self,
            'extra_args': extra_args,
        }

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        return serializer_class(*args, **kwargs)

    def get_object(self, pk=None):
        queryset = self.get_queryset()
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = pk or (self.kwargs.get(lookup_url_kwarg) if hasattr(self, 'kwargs') else None) or (self.kwargs.get('pk') if hasattr(self, 'kwargs') else None)

        if lookup_value is None:
            raise AttributeError(
                f"Expected view {self.__class__.__name__} to be called with URL kwarg '{lookup_url_kwarg}' or 'pk'."
            )

        obj = get_object_or_404(queryset, **{self.lookup_field: lookup_value})
        self.check_object_permissions(self.request, obj)
        return obj

    def list(self, request):
        try:
            extra_args = get_extra_args(request=request)
            serializer_class = self.get_serializer_class()
            queryset = self.get_queryset()

            # Filtres dynamiques & recherche
            queryset = apply_query_filters(
                queryset=queryset,
                request=request,
                filterset_fields=getattr(self, 'filterset_fields', None),
                search_fields=getattr(self, 'search_fields', None)
            )

            # Tri
            order_by = request.GET.get('order_by', '-id')
            try:
                if ',' in order_by:
                    order_fields = [f.strip() for f in order_by.split(',') if f.strip()]
                    queryset = queryset.order_by(*order_fields)
                else:
                    queryset = queryset.order_by(order_by)
            except Exception:
                queryset = queryset.order_by('-id')

            # Export Excel direct via ?export=true
            export = request.GET.get('export', 'false').lower()
            if export == 'true' and getattr(self, 'export_columns', None):
                return self._export_excel_response(queryset, request)

            # All data (sans pagination)
            all_data = request.GET.get('all', 'false').lower()
            if all_data == 'true':
                serializer = serializer_class(queryset, many=True, context={'extra_args': extra_args, 'request': request})
                return Response(build_success_response(
                    data=serializer.data,
                    message_code='list',
                    message_default='Informations chargées',
                    message_details=''
                ))

            # Paginé
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(queryset, request)
            if page is not None:
                serializer = serializer_class(page, many=True, context={'extra_args': extra_args, 'request': request})
                return paginator.get_paginated_response(serializer.data)

            # Fallback
            serializer = serializer_class(queryset, many=True, context={'extra_args': extra_args, 'request': request})
            return Response(build_success_response(
                data=serializer.data,
                message_code='list',
                message_default='Informations chargées',
                message_details=''
            ))

        except Exception as e:
            logger.exception("Erreur lors de la liste: %s", e)
            return Response(build_error_response(
                message_default='Une erreur est survenue lors de la récupération des données',
                message_details=str(e),
                errors={'error500': str(e)}
            ), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request):
        try:
            extra_args = get_extra_args(request=request)
            serializer = self.serializer_class(
                data=request.data,
                context={'extra_args': extra_args, 'request': request}
            )

            if serializer.is_valid():
                model = self.queryset.model if self.queryset is not None else None
                save_kwargs = {}
                if model:
                    model_fields = [f.name for f in model._meta.fields]
                    if 'owner' in model_fields and 'owner' not in serializer.validated_data and request.user.is_authenticated:
                        save_kwargs['owner'] = request.user
                    elif 'author' in model_fields and 'author' not in serializer.validated_data and request.user.is_authenticated:
                        save_kwargs['author'] = request.user
                    elif 'seller' in model_fields and 'seller' not in serializer.validated_data and request.user.is_authenticated:
                        save_kwargs['seller'] = request.user

                instance = serializer.save(**save_kwargs)

                return Response(build_success_response(
                    data=serializer.data,
                    message_code='data-saved',
                    message_default='Information enregistrée avec succès',
                    message_details=''
                ), status=status.HTTP_201_CREATED)

            logger.warning("Serializer validation errors: %s", serializer.errors)
            return Response(build_error_response(
                message_default="Une erreur est survenue lors de l'enregistrement",
                message_details="",
                errors=serializer.errors
            ), status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.exception("Create error: %s", e)
            return Response(build_error_response(
                message_default="Erreur interne du serveur lors de la création",
                message_details=str(e),
                errors={'exception': str(e)}
            ), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, pk=None):
        try:
            extra_args = get_extra_args(request=request)
            obj = self.get_object(pk=pk)

            serializer_class = self.read_only_serializer_class or self.serializer_class
            serializer = serializer_class(obj, context={'extra_args': extra_args, 'request': request})

            return Response(build_success_response(
                data=serializer.data,
                message_code='data-found',
                message_default='Données trouvées avec succès.',
                message_details=''
            ), status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Retrieve error: %s", e)
            return Response(build_error_response(
                message_default='Une erreur est survenue lors de la récupération des données.',
                message_details=str(e),
                errors={'error500': str(e)}
            ), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, pk=None, *args, **kwargs):
        try:
            extra_args = get_extra_args(request=request)
            instance = self.get_object(pk=pk)

            serializer = self.serializer_class(
                instance=instance,
                data=request.data,
                partial=True,
                context={'extra_args': extra_args, 'request': request}
            )

            if serializer.is_valid():
                instance = serializer.save()
                return Response(build_success_response(
                    data=serializer.data,
                    message_code='data-saved',
                    message_default='Données mises à jour avec succès.',
                    message_details=''
                ), status=status.HTTP_200_OK)

            return Response(build_error_response(
                message_default='Erreur lors de la validation des données.',
                message_details='',
                errors=serializer.errors
            ), status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.exception("Update error: %s", e)
            return Response(build_error_response(
                message_default='Une erreur est survenue lors de la mise à jour des données.',
                message_details=str(e),
                errors={'error500': str(e)}
            ), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def partial_update(self, request, pk=None, *args, **kwargs):
        return self.update(request, pk=pk, *args, **kwargs)

    def destroy(self, request, pk=None):
        try:
            instance = self.get_object(pk=pk)
            instance.delete()

            return Response(build_success_response(
                data={},
                message_code='success',
                message_default='Données supprimées avec succès.',
                message_details=''
            ), status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Destroy error: %s", e)
            return Response(build_error_response(
                message_default='Une erreur est survenue lors de la suppression.',
                message_details=str(e),
                errors={'error500': str(e)}
            ), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _export_excel_response(self, queryset, request):
        """Méthode interne pour produire le flux binaire Excel."""
        extra_args = get_extra_args(request=request)
        serializer_class = self.get_serializer_class()
        data = serializer_class(queryset, many=True, context={'extra_args': extra_args, 'request': request}).data

        wb = Workbook()
        ws = wb.active
        ws.title = "Export"

        headers = [col[0] for col in self.export_columns]
        ws.append(headers)

        def get_nested(obj, path):
            for key in path:
                if isinstance(obj, dict):
                    obj = obj.get(key)
                else:
                    obj = getattr(obj, key, None)
                if obj is None:
                    return None
            return obj

        for item in data:
            row = [get_nested(item, path) for _, path in self.export_columns]
            ws.append(row)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{self.export_filename}"'
        wb.save(response)
        return response

    @action(detail=False, methods=['get'])
    def export_excel(self, request, *args, **kwargs):
        """Action d'export Excel spécifique."""
        if not getattr(self, 'export_columns', None):
            return Response(build_error_response(
                message_default="Exportation non configurée pour ce modèle",
                message_details="export_columns n'est pas défini sur ce ViewSet"
            ), status=status.HTTP_400_BAD_REQUEST)

        queryset = self.get_queryset()
        queryset = apply_query_filters(
            queryset=queryset,
            request=request,
            filterset_fields=getattr(self, 'filterset_fields', None),
            search_fields=getattr(self, 'search_fields', None)
        )
        return self._export_excel_response(queryset, request)


def number_to_words_fr(n) -> str:
    """Convertit un nombre entier en toutes lettres en français."""
    if n is None:
        return ''
    try:
        num = int(abs(n))
    except (ValueError, TypeError):
        return ''
    if num == 0:
        return 'zéro'

    units = ['', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf']
    teens = ['dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf']
    tens = ['', 'dix', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante', 'soixante-dix', 'quatre-vingt', 'quatre-vingt-dix']

    def convert_under_100(val: int) -> str:
        if val < 10:
            return units[val]
        if val < 20:
            return teens[val - 10]
        ten_val = val // 10
        unit_val = val % 10

        if ten_val == 7:
            if unit_val == 1:
                return 'soixante et onze'
            return 'soixante-' + teens[unit_val]
        if ten_val == 8:
            if unit_val == 0:
                return 'quatre-vingts'
            return 'quatre-vingt-' + units[unit_val]
        if ten_val == 9:
            return 'quatre-vingt-' + teens[unit_val]

        if unit_val == 1 and 2 <= ten_val <= 6:
            return tens[ten_val] + ' et un'
        if unit_val > 0:
            return tens[ten_val] + '-' + units[unit_val]
        return tens[ten_val]

    def convert_under_1000(val: int) -> str:
        hundred = val // 100
        rest = val % 100
        res = ''
        if hundred == 1:
            res = 'cent'
        elif hundred > 1:
            res = units[hundred] + (' cents' if rest == 0 else ' cent')

        if rest > 0:
            rest_str = convert_under_100(rest)
            res = (res + ' ' + rest_str) if res else rest_str
        return res

    def convert_chunks(val: int) -> str:
        if val == 0:
            return ''
        if val < 1000:
            return convert_under_1000(val)

        billions = val // 1_000_000_000
        millions = (val % 1_000_000_000) // 1_000_000
        thousands = (val % 1_000_000) // 1000
        remainder = val % 1000

        parts = []
        if billions > 0:
            parts.append('un milliard' if billions == 1 else f"{convert_under_1000(billions)} milliards")
        if millions > 0:
            parts.append('un million' if millions == 1 else f"{convert_under_1000(millions)} millions")
        if thousands > 0:
            if thousands == 1:
                parts.append('mille')
            else:
                th_str = convert_under_1000(thousands)
                if th_str.endswith('cents'):
                    th_str = th_str[:-1]
                if th_str.endswith('quatre-vingts'):
                    th_str = th_str[:-1]
                parts.append(th_str + ' mille')
        if remainder > 0:
            parts.append(convert_under_1000(remainder))

        return ' '.join(parts)

    sign = 'moins ' if n < 0 else ''
    return (sign + convert_chunks(num)).strip()


def amount_to_words_fr(amount, currency: str = 'FCFA', cents_label: str = 'centimes') -> str:
    """Convertit un montant en toutes lettres en français."""
    if amount is None:
        return f"zéro {currency}"
    try:
        val = float(amount)
    except (ValueError, TypeError):
        return f"zéro {currency}"

    sign = 'moins ' if val < 0 else ''
    abs_val = abs(val)
    integer_part = int(abs_val)
    decimal_part = int(round((abs_val - integer_part) * 100))

    integer_words = number_to_words_fr(integer_part)
    result = f"{sign}{integer_words} {currency}".strip()

    if decimal_part > 0:
        result += f" et {number_to_words_fr(decimal_part)} {cents_label}"

    return result
