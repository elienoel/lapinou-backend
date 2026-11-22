from django.db import migrations


def fill(apps, schema_editor):
    """Calcule l'aperçu flou, les dimensions et le poids des médias existants."""
    from community.models import image_preview

    PostMedia = apps.get_model('community', 'PostMedia')
    for media in PostMedia.objects.all():
        changed = []
        try:
            if not media.size and media.file:
                media.size = media.file.size
                changed.append('size')
        except (OSError, ValueError):
            pass
        if media.media_type == 'image' and not media.preview and media.file:
            media.preview, media.width, media.height = image_preview(media.file)
            changed += ['preview', 'width', 'height']
        if changed:
            media.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [('community', '0005_media_preview')]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
