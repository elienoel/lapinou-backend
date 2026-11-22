from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_save


def _seed_new_farm(sender, instance, created, raw=False, **kwargs):
    """Un nouveau compte reçoit les types de soins par défaut (vaccin VHD, vitamines...)."""
    if created and not raw:
        from .defaults import create_default_care_treatments
        create_default_care_treatments(instance)


class FarmConfig(AppConfig):
    name = 'farm'

    def ready(self):
        post_save.connect(
            _seed_new_farm, sender=settings.AUTH_USER_MODEL,
            dispatch_uid='farm-default-care-treatments',
        )
