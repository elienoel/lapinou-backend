import os

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from .models import PostMedia

MAX_MEDIA_PER_POST = 10
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 100 * 1024 * 1024

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.webm', '.3gp'}


def classify_and_validate(uploaded_files):
    """
    Vérifie les fichiers envoyés avec une publication et renvoie une liste de
    (fichier, type de média). Lève une ValidationError sur le champ `media`
    si l'un d'eux est refusé : aucun fichier n'est alors enregistré.
    """
    if len(uploaded_files) > MAX_MEDIA_PER_POST:
        raise serializers.ValidationError(
            {'media': f'Maximum {MAX_MEDIA_PER_POST} photos/vidéos par publication.'}
        )

    result = []
    for f in uploaded_files:
        ext = os.path.splitext(f.name or '')[1].lower()
        if ext in IMAGE_EXTENSIONS:
            if f.size > MAX_IMAGE_BYTES:
                raise serializers.ValidationError(
                    {'media': f'« {f.name} » dépasse {MAX_IMAGE_BYTES // (1024 * 1024)} Mo.'}
                )
            try:
                Image.open(f).verify()
            except (UnidentifiedImageError, OSError, SyntaxError):
                raise serializers.ValidationError({'media': f'« {f.name} » n\'est pas une image valide.'})
            finally:
                f.seek(0)
            result.append((f, PostMedia.MediaType.IMAGE))
        elif ext in VIDEO_EXTENSIONS:
            if f.size > MAX_VIDEO_BYTES:
                raise serializers.ValidationError(
                    {'media': f'« {f.name} » dépasse {MAX_VIDEO_BYTES // (1024 * 1024)} Mo.'}
                )
            result.append((f, PostMedia.MediaType.VIDEO))
        else:
            raise serializers.ValidationError(
                {'media': f'Format non pris en charge : « {f.name} ». Photos (jpg, png, gif, webp) ou vidéos (mp4, mov, webm, 3gp).'}
            )
    return result
