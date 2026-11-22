import json
import logging

from django.conf import settings
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import build_error_response, build_success_response
from . import geniuspay, plans, services
from .models import SubscriptionPayment

logger = logging.getLogger(__name__)


def _payment_data(payment):
    return {
        'reference': payment.reference,
        'plan': payment.plan,
        'amount': payment.amount,
        'status': payment.status,
        'checkout_url': payment.checkout_url,
        'paid_at': payment.paid_at,
    }


@extend_schema(tags=['Abonnements'])
class SubscriptionStatusView(APIView):
    """Formule en vigueur, limite de fiches lapins, fin de période et tarifs."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(build_success_response(services.status_payload(request.user)))


@extend_schema(tags=['Abonnements'])
class CheckoutView(APIView):
    """
    Démarre le paiement d'un mois de formule (`plan` = breeder ou pro) et renvoie
    l'adresse de la page de paiement GeniusPay (Mobile Money, carte).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = request.data.get('plan')
        plan = plans.PLANS.get(code)
        if plan is None or plan.price == 0:
            return Response(build_error_response(
                'Formule inconnue', errors={'plan': 'Choisissez la formule Éleveur ou Pro.'}
            ), status=status.HTTP_400_BAD_REQUEST)
        count = services.rabbit_count(request.user)
        if not plan.allows(count):
            needed = plans.plan_for_rabbits(count)
            return Response(build_error_response(
                'Formule trop petite',
                errors={'plan': f"Vous avez {count} lapins : la formule {needed.name} est nécessaire."},
            ), status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        with transaction.atomic():
            payment = SubscriptionPayment.objects.create(user=user, plan=plan.code, amount=plan.price)
        try:
            remote = geniuspay.create_payment(
                amount=plan.price,
                description=f"Clap'in — formule {plan.name}, {plans.PERIOD_DAYS} jours",
                customer={
                    'name': user.get_full_name() or getattr(user, 'farm_name', '') or user.username,
                    'phone': getattr(user, 'phone_number', '') or '',
                    'email': user.email or '',
                },
                metadata={'payment_id': payment.pk, 'user_id': user.pk, 'plan': plan.code},
                success_url=settings.GENIUSPAY_SUCCESS_URL,
                error_url=settings.GENIUSPAY_ERROR_URL,
            )
        except geniuspay.GeniusPayError as exc:
            logger.error('GeniusPay checkout failed: %s', exc)
            payment.status = SubscriptionPayment.Status.FAILED
            payment.raw = {'error': str(exc)}
            payment.save(update_fields=['status', 'raw', 'updated_at'])
            return Response(build_error_response(
                'Paiement indisponible',
                message_details='Le service de paiement ne répond pas, réessayez dans un instant.',
            ), status=status.HTTP_502_BAD_GATEWAY)

        payment.reference = remote.get('reference')
        payment.checkout_url = remote.get('checkout_url') or remote.get('payment_url') or ''
        payment.raw = remote
        payment.save(update_fields=['reference', 'checkout_url', 'raw', 'updated_at'])
        return Response(build_success_response(
            _payment_data(payment), message_code='checkout-created',
            message_default='Paiement créé',
        ), status=status.HTTP_201_CREATED)


@extend_schema(tags=['Abonnements'])
class PaymentRefreshView(APIView):
    """Relit chez GeniusPay le statut d'un paiement (au retour de la page de paiement)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, reference):
        payment = SubscriptionPayment.objects.filter(user=request.user, reference=reference).first()
        if payment is None:
            return Response(build_error_response('Paiement introuvable'), status=status.HTTP_404_NOT_FOUND)
        try:
            payment = services.confirm_payment(payment)
        except geniuspay.GeniusPayError as exc:
            logger.warning('GeniusPay refresh failed for %s: %s', reference, exc)
        return Response(build_success_response({
            'payment': _payment_data(payment),
            'subscription': services.status_payload(request.user),
        }))


@method_decorator(csrf_exempt, name='dispatch')
@extend_schema(tags=['Abonnements'], exclude=True)
class GeniusPayWebhookView(APIView):
    """
    Notification GeniusPay. La signature est vérifiée, puis le statut est
    toujours relu via l'API avant de créditer quoi que ce soit.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        body = request.body
        if not geniuspay.verify_signature(
            body,
            request.headers.get('X-Webhook-Timestamp', ''),
            request.headers.get('X-Webhook-Signature', ''),
        ):
            return Response({'detail': 'invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            event = json.loads(body)
        except ValueError:
            return Response({'detail': 'invalid json'}, status=status.HTTP_400_BAD_REQUEST)

        reference = (event.get('data') or {}).get('reference')
        payment = SubscriptionPayment.objects.filter(reference=reference).first() if reference else None
        if payment is not None:
            try:
                services.confirm_payment(payment)
            except geniuspay.GeniusPayError as exc:
                logger.error('GeniusPay webhook confirm failed for %s: %s', reference, exc)
                # GeniusPay renverra la notification
                return Response({'detail': 'retry'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'received': True})
