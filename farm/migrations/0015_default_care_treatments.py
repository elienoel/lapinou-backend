from django.conf import settings
from django.db import migrations


def seed_existing_farms(apps, schema_editor):
    """Les comptes existants sans aucun type de soin reçoivent la liste par défaut."""
    from farm.defaults import create_default_care_treatments

    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    CareTreatment = apps.get_model('farm', 'CareTreatment')
    for user in User.objects.exclude(care_treatments__isnull=False):
        create_default_care_treatments(user, CareTreatment)


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0014_litter_kits'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_existing_farms, migrations.RunPython.noop),
    ]
