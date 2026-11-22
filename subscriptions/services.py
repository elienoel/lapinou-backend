from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from . import geniuspay, plans
from .models import Subscription, SubscriptionPayment

# Statuts GeniusPay considérés comme définitivement échoués
FAILED_STATUSES = {'failed', 'cancelled', 'canceled', 'expired', 'refunded'}


class PlanLimitReached(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = 'plan-limit'

    def __init__(self, sub, count, adding):
        plan = sub.active_plan
        required = plans.plan_for_rabbits(count + adding)
        self.detail = {
            'success': False,
            'message': {
                'code': 'plan-limit',
                'default': 'Limite de votre abonnement atteinte',
                'details': (
                    f"Votre formule {plan.name} permet {plan.max_rabbits} lapins "
                    f"({count} enregistrés). Passez à la formule {required.name} "
                    f"({required.price} F/mois) pour en ajouter."
                ),
            },
            'errors': {'subscription': f"Formule {required.name} nécessaire."},
            'data': {
                'plan': plan.code, 'limit': plan.max_rabbits, 'count': count,
                'required_plan': required.code,
            },
        }


def get_subscription(user):
    sub, _ = Subscription.objects.get_or_create(user=user)
    return sub


def rabbit_count(user):
    from farm.models import Rabbit
    return Rabbit.objects.filter(owner=user, is_deleted=False).count()


def ensure_can_add_rabbits(user, adding=1):
    """Refuse (HTTP 402) la création de fiches au-delà du palier en vigueur."""
    if adding <= 0:
        return
    sub = get_subscription(user)
    count = rabbit_count(user)
    if not sub.active_plan.allows(count + adding):
        raise PlanLimitReached(sub, count, adding)


def status_payload(user):
    sub = get_subscription(user)
    count = rabbit_count(user)
    plan = sub.active_plan
    return {
        'plan': plan.code,
        'plan_name': plan.name,
        'limit': plan.max_rabbits,
        'rabbit_count': count,
        'current_period_end': sub.current_period_end if sub.is_active else None,
        'days_left': sub.days_left,
        'required_plan': plans.plan_for_rabbits(count).code,
        'plans': [plans.PLANS[code].as_dict() for code in plans.ORDER],
    }


def confirm_payment(payment):
    """
    Relit le statut chez GeniusPay (jamais sur la seule foi d'un webhook) et
    crédite la période une seule fois. Renvoie le paiement à jour.
    """
    if payment.status != SubscriptionPayment.Status.PENDING or not payment.reference:
        return payment
    remote = geniuspay.get_payment(payment.reference)
    remote_status = str(remote.get('status', '')).lower()

    with transaction.atomic():
        payment = SubscriptionPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != SubscriptionPayment.Status.PENDING:
            return payment
        payment.raw = remote
        if remote_status == 'completed' and _amount_ok(remote, payment):
            payment.status = SubscriptionPayment.Status.COMPLETED
            payment.paid_at = timezone.now()
            get_subscription(payment.user).credit(payment.plan)
        elif remote_status in FAILED_STATUSES:
            payment.status = SubscriptionPayment.Status.FAILED
        payment.save(update_fields=['raw', 'status', 'paid_at', 'updated_at'])
    return payment


def _amount_ok(remote, payment):
    try:
        return float(remote.get('amount')) >= payment.amount
    except (TypeError, ValueError):
        return False
