import shutil
from pathlib import Path

from django.conf import settings
from django.db import migrations

# Fichiers déposés par l'éleveur dans backend/statics/breeds/ (hors media/, donc pas servis
# tels quels) : on les copie dans MEDIA_ROOT/breeds/ et on les rattache à la race correspondante.
# Les races sans fichier gardent une image vide (icône par défaut côté app) en attendant une vraie photo.
BREED_IMAGES = {
    'Fauve de Bourgogne': None,
    'Géant des Flandres': 'Lapin_geant_des_flandres.jpeg',
    'Néo-Zélandais': 'Rabbit-Neo_Zelandais.jpg',
    'Californien': 'Californian-Rabbit.jpg',
    'Rex': None,
    'Papillon Français': 'papillon_francais.png',
    'Argenté de Champagne': None,
    'Bélier Français': None,
    'Chinchilla': None,
    'Gris du Bourbonnais': None,
    # Souches commerciales Hypharm (pas des races au sens strict, mais utilisées telles
    # quelles par l'éleveur dans son cheptel).
    'PS 119': 'lapin-male-PS119-hypharm.png',
    'PS 59': 'lapin-male-PS59-hypharm.png',
    'PS 40': 'lapin-male-PS40-hypharm.png',
    'PS Hyla Optima': 'lapin-PS-hyla-optima-hypharm.png',
    'PS Hyplus Optima': 'Femelle-hyplus-02.webp',
}

SOURCE_DIR = Path(__file__).resolve().parent.parent.parent / 'statics' / 'breeds'


def seed_breeds(apps, schema_editor):
    Breed = apps.get_model('farm', 'Breed')
    media_breeds_dir = Path(settings.MEDIA_ROOT) / 'breeds'
    media_breeds_dir.mkdir(parents=True, exist_ok=True)

    for name, filename in BREED_IMAGES.items():
        breed, _ = Breed.objects.get_or_create(name=name)

        if filename is None or breed.image:
            continue

        source = SOURCE_DIR / filename
        if not source.exists():
            continue

        destination = media_breeds_dir / filename
        if not destination.exists():
            shutil.copyfile(source, destination)

        breed.image.name = f'breeds/{filename}'
        breed.save(update_fields=['image'])


def noop_reverse(apps, schema_editor):
    # Les races créées restent (elles peuvent déjà être utilisées par des lapins) ;
    # seule la jointure vers les fichiers image n'a pas vraiment de sens à "annuler".
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0010_breed_image'),
    ]

    operations = [
        migrations.RunPython(seed_breeds, noop_reverse),
    ]
