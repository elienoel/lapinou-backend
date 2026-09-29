import random
from datetime import timedelta
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from core.utils import CustomViewSet, build_success_response, build_error_response
from .models import User, Notification, OTPVerification
from .serializers import (
    UserSerializer,
    NotificationSerializer,
    ProfileSerializer,
    RequestOTPSerializer,
    VerifyOTPSerializer,
)


@extend_schema(
    tags=['Authentification & OTP'],
    summary='Demander un code OTP par téléphone (SMS/WhatsApp)',
    description='Envoie un code OTP à 6 chiffres pour initier la connexion ou l\'inscription.',
    request=RequestOTPSerializer,
)
class RequestOTPView(APIView):
    """
    Endpoint public pour demander un code OTP par SMS / WhatsApp.
    POST /api/auth/request-otp/
    Payload: { "phone_number": "+2250102030405" }
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(build_error_response(
                message_default="Numéro de téléphone invalide",
                errors=serializer.errors
            ), status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data['phone_number']

        # En environnement de dev / démo ou avant passerelle SMS tierce :
        # Code OTP à 6 chiffres (par défaut ou fixe '123456' pour test rapide, avec code aléatoire)
        # On génère un code à 6 chiffres
        # otp_code = str(random.randint(100000, 999999))
        # Pour faciliter les tests d'intégration immédiats, si c'est un numéro de test type '01020304' ou dev
        otp_code = '123456'

        expires_at = timezone.now() + timedelta(minutes=5)

        # Invalider les anciens codes OTP pour ce numéro
        OTPVerification.objects.filter(phone_number=phone_number, is_used=False).update(is_used=True)

        # Enregistrer le nouveau code OTP
        OTPVerification.objects.create(
            phone_number=phone_number,
            otp_code=otp_code,
            expires_at=expires_at
        )

        # Ici on peut brancher une passerelle SMS réelle (Twilio, Termii, Orange SMS, etc.)
        # Pour le retour API, on retourne le code dans la réponse pour faciliter le dev/test immédiat
        return Response(build_success_response(
            data={
                "phone_number": phone_number,
                "expires_in_seconds": 300,
                "dev_otp": otp_code,  # Fourni en mode dev pour simplifier les tests
            },
            message_code="otp-sent",
            message_default=f"Code de vérification envoyé au {phone_number}"
        ), status=status.HTTP_200_OK)


@extend_schema(
    tags=['Authentification & OTP'],
    summary='Vérifier le code OTP et générer les jetons JWT',
    description='Valide le code OTP envoyé par SMS, crée le compte éleveur s\'il n\'existe pas, et retourne les jetons d\'accès JWT et le profil.',
    request=VerifyOTPSerializer,
)
class VerifyOTPView(APIView):
    """
    Endpoint public pour vérifier le code OTP et générer les tokens JWT.
    POST /api/auth/verify-otp/
    Payload: { "phone_number": "...", "otp_code": "123456", "farm_name": "...", "first_name": "..." }
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(build_error_response(
                message_default="Données invalides",
                errors=serializer.errors
            ), status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data['phone_number']
        otp_code = serializer.validated_data['otp_code']
        farm_name = serializer.validated_data.get('farm_name')
        first_name = serializer.validated_data.get('first_name')
        last_name = serializer.validated_data.get('last_name')

        # Trouver l'OTP actif le plus récent
        otp_record = OTPVerification.objects.filter(
            phone_number=phone_number,
            is_used=False
        ).order_by('-created_at').first()

        # Accepter aussi '123456' en mode passe-partout de développement
        is_valid_otp = False
        if otp_code == '123456':
            is_valid_otp = True
        elif otp_record and otp_record.is_valid() and otp_record.otp_code == otp_code:
            is_valid_otp = True

        if not is_valid_otp:
            if otp_record:
                otp_record.attempts += 1
                otp_record.save(update_fields=['attempts'])
            return Response(build_error_response(
                message_default="Code de vérification invalide ou expiré",
                message_code="invalid-otp"
            ), status=status.HTTP_400_BAD_REQUEST)

        # Marquer l'OTP comme utilisé
        if otp_record:
            otp_record.is_used = True
            otp_record.save(update_fields=['is_used'])

        # Récupérer ou créer l'utilisateur éleveur
        user = User.objects.filter(phone_number=phone_number).first()
        is_new_user = False

        if not user:
            is_new_user = True
            username = f"user_{phone_number.replace('+', '').replace(' ', '')}"
            # S'assurer de l'unicité du username
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1

            user = User.objects.create(
                username=username,
                phone_number=phone_number,
                farm_name=farm_name or "Mon Élevage",
                first_name=first_name or "",
                last_name=last_name or "",
            )
        else:
            # Mettre à jour les informations complémentaires si fournies
            updated_fields = []
            if farm_name and not user.farm_name:
                user.farm_name = farm_name
                updated_fields.append('farm_name')
            if first_name and not user.first_name:
                user.first_name = first_name
                updated_fields.append('first_name')
            if last_name and not user.last_name:
                user.last_name = last_name
                updated_fields.append('last_name')
            if updated_fields:
                user.save(update_fields=updated_fields)

        # Générer les tokens JWT
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        user_data = UserSerializer(user, context={'request': request}).data

        return Response(build_success_response(
            data={
                "user": user_data,
                "token": access_token,
                "refresh": refresh_token,
                "is_new_user": is_new_user,
            },
            message_code="auth-success",
            message_default="Connexion réussie !"
        ), status=status.HTTP_200_OK)


@extend_schema(tags=['Authentification & OTP'])
class UserViewSet(CustomViewSet):
    """
    ViewSet pour la gestion des profils utilisateurs / éleveurs.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filterset_fields = {
        'username': ['exact', 'icontains'],
        'email': ['exact', 'icontains'],
        'farm_name': ['exact', 'icontains'],
        'location': ['exact', 'icontains'],
    }
    search_fields = ['username', 'email', 'farm_name', 'first_name', 'last_name', 'location']
    export_columns = [
        ('ID', ['id']),
        ('Nom utilisateur', ['username']),
        ('Email', ['email']),
        ('Élevage', ['farm_name']),
        ('Téléphone', ['phone_number']),
        ('Localisation', ['location']),
    ]
    export_filename = "eleveurs_lapinou.xlsx"

    def get_permissions(self):
        if self.action in ['create', 'register']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return User.objects.none()
        if user.is_superuser:
            return User.objects.all()
        return User.objects.filter(pk=user.pk)

    @action(detail=False, methods=['get', 'put', 'patch', 'delete'])
    def me(self, request):
        """
        GET : profil de l'utilisateur connecté.
        PUT/PATCH : met à jour le profil (multipart accepté pour la photo `avatar`,
        `remove_avatar=true` pour la retirer).
        DELETE : supprime définitivement le compte et ses données (corps `{"confirm": true}` requis).
        """
        user = request.user

        if request.method == 'DELETE':
            if request.data.get('confirm') not in (True, 'true', 'True', '1', 1):
                return Response(build_error_response(
                    message_default='Confirmation requise pour supprimer le compte',
                    errors={'confirm': 'Envoyez confirm=true pour confirmer la suppression.'}
                ), status=status.HTTP_400_BAD_REQUEST)
            self._delete_user_files(user)
            user.delete()
            return Response(build_success_response(
                data={},
                message_code='account-deleted',
                message_default='Compte supprimé'
            ))

        if request.method == 'GET':
            serializer = ProfileSerializer(user, context={'request': request})
            return Response(build_success_response(
                data=serializer.data,
                message_code='profile-loaded',
                message_default='Profil utilisateur chargé'
            ))

        serializer = ProfileSerializer(
            user, data=request.data, partial=(request.method == 'PATCH'),
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(build_success_response(
                data=serializer.data,
                message_code='profile-updated',
                message_default='Profil mis à jour avec succès'
            ))
        return Response(build_error_response(
            message_default='Erreur de validation',
            errors=serializer.errors
        ), status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _delete_user_files(user):
        """Supprime du stockage les fichiers de l'utilisateur (la suppression en base ne le fait pas)."""
        from community.models import Post, PostMedia, MarketplaceListing
        from farm.models import Rabbit, RabbitImage
        from chat.models import Message

        files = [user.avatar]
        files += [m.file for m in PostMedia.objects.filter(post__author=user)]
        files += [p.image for p in Post.objects.filter(author=user)]
        files += [l.photo for l in MarketplaceListing.objects.filter(seller=user)]
        files += [r.photo for r in Rabbit.objects.filter(owner=user)]
        files += [i.image for i in RabbitImage.objects.filter(rabbit__owner=user)]
        for m in Message.objects.filter(sender=user):
            files += [m.image, m.audio]
        for f in files:
            if f:
                f.delete(save=False)


@extend_schema(tags=['Authentification & OTP'])
class NotificationViewSet(CustomViewSet):
    """
    ViewSet pour consulter et marquer comme lues les notifications de l'utilisateur.
    """
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    user_field_lookup = 'recipient'
    filterset_fields = {
        'notif_type': ['exact'],
        'is_read': ['exact'],
    }
    search_fields = ['title', 'message']

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object(pk=pk)
        notification.mark_as_read()
        return Response(build_success_response(
            data=self.get_serializer(notification).data,
            message_code='marked-read',
            message_default='Notification marquée comme lue'
        ))

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return Response(build_success_response(
            data={'marked_count': updated},
            message_code='all-marked-read',
            message_default=f'{updated} notifications marquées comme lues'
        ))
