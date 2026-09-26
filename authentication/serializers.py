from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import User, Notification, OTPVerification
from core.utils import UserActionMixinSerializer


class UserSerializer(serializers.ModelSerializer):
    """
    Sérialiseur pour le profil utilisateur et éleveur.
    """
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'phone_number', 'avatar', 'farm_name', 'location',
            'bio', 'currency', 'password', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])
        return user


MAX_AVATAR_BYTES = 5 * 1024 * 1024


class ProfileSerializer(serializers.ModelSerializer):
    """
    Profil modifiable par l'utilisateur connecté : le numéro de téléphone (identifiant de
    connexion) et le nom d'utilisateur ne changent pas ici.
    `remove_avatar=true` supprime la photo de profil.
    """
    remove_avatar = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'phone_number', 'avatar', 'farm_name', 'location',
            'bio', 'currency', 'created_at', 'updated_at', 'remove_avatar'
        ]
        read_only_fields = ['id', 'username', 'phone_number', 'created_at', 'updated_at']

    def validate_avatar(self, value):
        if value and value.size > MAX_AVATAR_BYTES:
            raise serializers.ValidationError(
                f"La photo dépasse {MAX_AVATAR_BYTES // (1024 * 1024)} Mo."
            )
        return value

    def update(self, instance, validated_data):
        remove = validated_data.pop('remove_avatar', False)
        old_avatar = instance.avatar if instance.avatar else None
        new_avatar = validated_data.get('avatar')

        if remove and not new_avatar:
            validated_data['avatar'] = None

        user = super().update(instance, validated_data)

        # Supprimer l'ancien fichier du stockage s'il a été remplacé ou retiré
        if old_avatar and (not user.avatar or user.avatar.name != old_avatar.name):
            old_avatar.delete(save=False)
        return user


class RequestOTPSerializer(serializers.Serializer):
    """
    Validation pour la demande d'envoi de code OTP.
    """
    phone_number = serializers.CharField(max_length=25, required=True)

    def validate_phone_number(self, value):
        cleaned = value.strip().replace(" ", "").replace("-", "")
        if len(cleaned) < 8:
            raise serializers.ValidationError("Numéro de téléphone invalide.")
        return cleaned


class VerifyOTPSerializer(serializers.Serializer):
    """
    Validation pour la vérification du code OTP et connexion.
    """
    phone_number = serializers.CharField(max_length=25, required=True)
    otp_code = serializers.CharField(max_length=6, min_length=4, required=True)
    farm_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_phone_number(self, value):
        return value.strip().replace(" ", "").replace("-", "")

    def validate_otp_code(self, value):
        return value.strip()


class NotificationSerializer(serializers.ModelSerializer):
    """
    Sérialiseur pour les notifications in-app.
    """
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'sender', 'sender_name', 'recipient', 'title',
            'message', 'notif_type', 'is_read', 'read_at',
            'created_at', 'expires_at'
        ]
        read_only_fields = ['id', 'created_at']

    @extend_schema_field(serializers.CharField())
    def get_sender_name(self, obj):
        if obj.sender:
            return obj.sender.farm_name or obj.sender.get_full_name() or obj.sender.username
        return "Système"
