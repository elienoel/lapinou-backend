import os

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from .models import Message

MAX_MESSAGE_CHARS = 4000
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_AUDIO_DURATION_MS = 10 * 60 * 1000
AUDIO_EXTENSIONS = {'.m4a', '.aac', '.mp3', '.wav', '.ogg', '.opus', '.webm', '.3gp', '.mp4'}


def looks_like_audio(head):
    """Contrôle sommaire de l'en-tête du fichier (évite d'accepter n'importe quoi renommé en .m4a)."""
    return (
        head[4:8] == b'ftyp'                                     # m4a / mp4 / 3gp
        or head[:4] == b'RIFF' and head[8:12] == b'WAVE'         # wav
        or head[:3] == b'ID3'                                    # mp3 avec tags
        or len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0  # mp3 / aac ADTS
        or head[:4] == b'OggS'                                   # ogg / opus
        or head[:4] == b'\x1a\x45\xdf\xa3'                        # webm
    )


def display_name(user):
    return user.farm_name or user.get_full_name() or user.username


def absolute_url(request, file_field):
    if not file_field:
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


def serialize_user(user, request):
    return {
        'id': user.id,
        'name': display_name(user),
        'farm_name': user.farm_name,
        'location': user.location,
        'avatar': absolute_url(request, user.avatar),
    }


class MessageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)
    audio = serializers.FileField(required=False, allow_null=True)
    audio_duration_ms = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'content', 'image',
            'audio', 'audio_duration_ms', 'created_at', 'is_read',
        ]
        read_only_fields = ['id', 'conversation', 'sender', 'created_at', 'is_read']

    def get_is_read(self, obj):
        return obj.read_at is not None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        data['image'] = absolute_url(request, instance.image)
        data['audio'] = absolute_url(request, instance.audio)
        return data

    def validate_content(self, value):
        value = (value or '').strip()
        if len(value) > MAX_MESSAGE_CHARS:
            raise serializers.ValidationError(f'Message trop long ({MAX_MESSAGE_CHARS} caractères maximum).')
        return value

    def validate_image(self, f):
        if f is None:
            return f
        ext = os.path.splitext(f.name or '')[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            raise serializers.ValidationError('Format non pris en charge (jpg, png, gif ou webp).')
        if f.size > MAX_IMAGE_BYTES:
            raise serializers.ValidationError(f'La photo dépasse {MAX_IMAGE_BYTES // (1024 * 1024)} Mo.')
        try:
            Image.open(f).verify()
        except (UnidentifiedImageError, OSError, SyntaxError):
            raise serializers.ValidationError("Ce fichier n'est pas une image valide.")
        finally:
            f.seek(0)
        return f

    def validate_audio(self, f):
        if f is None:
            return f
        ext = os.path.splitext(f.name or '')[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            raise serializers.ValidationError('Format audio non pris en charge.')
        if f.size > MAX_AUDIO_BYTES:
            raise serializers.ValidationError(f'La note vocale dépasse {MAX_AUDIO_BYTES // (1024 * 1024)} Mo.')
        head = f.read(16)
        f.seek(0)
        if not looks_like_audio(head):
            raise serializers.ValidationError("Ce fichier n'est pas un enregistrement audio valide.")
        return f

    def validate_audio_duration_ms(self, value):
        if value is not None and value > MAX_AUDIO_DURATION_MS:
            raise serializers.ValidationError('Note vocale trop longue (10 minutes maximum).')
        return value

    def validate(self, attrs):
        text = (attrs.get('content') or '').strip()
        image, audio = attrs.get('image'), attrs.get('audio')
        if audio and image:
            raise serializers.ValidationError({'audio': 'Envoyez une photo ou une note vocale, pas les deux.'})
        if not text and not image and not audio:
            raise serializers.ValidationError({'content': 'Écrivez un message, joignez une photo ou une note vocale.'})
        if not audio:
            attrs.pop('audio_duration_ms', None)
        return attrs
