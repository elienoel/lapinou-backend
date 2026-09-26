import django.core.validators
from django.db import migrations, models


def loges_to_rows(apps, schema_editor):
    """Les anciennes cages étaient une colonne unique de N loges : N lignes x 1 colonne."""
    Cage = apps.get_model('farm', 'Cage')
    for cage in Cage.objects.all():
        cage.rows_count = cage.compartments_count
        cage.columns_count = 1
        cage.save(update_fields=['rows_count', 'columns_count'])


def rows_to_loges(apps, schema_editor):
    Cage = apps.get_model('farm', 'Cage')
    for cage in Cage.objects.all():
        cage.compartments_count = min(cage.rows_count * cage.columns_count, 12)
        cage.save(update_fields=['compartments_count'])


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0003_cage'),
    ]

    operations = [
        migrations.AddField(
            model_name='cage',
            name='columns_count',
            field=models.PositiveSmallIntegerField(default=1, help_text='Nombre de colonnes de loges', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(6)]),
        ),
        migrations.AddField(
            model_name='cage',
            name='rows_count',
            field=models.PositiveSmallIntegerField(default=3, help_text='Nombre de lignes (étages) de loges', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)]),
        ),
        migrations.RunPython(loges_to_rows, rows_to_loges),
        migrations.RemoveField(
            model_name='cage',
            name='compartments_count',
        ),
    ]
