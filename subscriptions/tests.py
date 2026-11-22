import hashlib
import hmac
import json
import time
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from farm.models import Litter, Rabbit

from . import plans
from .models import Subscription, SubscriptionPayment
from .services import get_subscription

SECRET = 'whsec_sandbox_test'
KEYS = dict(GENIUSPAY_API_KEY='pk_sandbox_x', GENIUSPAY_API_SECRET='sk_sandbox_x',
            GENIUSPAY_WEBHOOK_SECRET=SECRET)


def signed(payload):
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()
    return body, {'HTTP_X_WEBHOOK_TIMESTAMP': ts, 'HTTP_X_WEBHOOK_SIGNATURE': sig}


@override_settings(**KEYS)
class SubscriptionTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='eleveur', password='x', phone_number='+2250700000000')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.born = date.today() - timedelta(days=300)

    def _rabbits(self, n, start=0):
        for i in range(start, start + n):
            Rabbit.objects.create(owner=self.user, name=f'L{i}', tag_number=f'T{i}', gender='F', birth_date=self.born)

    def _add_via_api(self, tag):
        return self.client.post('/api/farm/rabbits/', {
            'name': tag, 'tag_number': tag, 'gender': 'M', 'birth_date': self.born.isoformat(),
        }, format='json')

    # --- paliers et blocage -----------------------------------------------

    def test_plans_and_required_plan(self):
        self.assertEqual(plans.plan_for_rabbits(4).code, plans.FREE)
        self.assertEqual(plans.plan_for_rabbits(5).code, plans.BREEDER)
        self.assertEqual(plans.plan_for_rabbits(10).code, plans.BREEDER)
        self.assertEqual(plans.plan_for_rabbits(11).code, plans.PRO)

    def test_free_plan_blocks_the_fifth_rabbit(self):
        self._rabbits(3)
        self.assertEqual(self._add_via_api('OK4').status_code, 201)
        res = self._add_via_api('NON5')
        self.assertEqual(res.status_code, 402, res.content)
        self.assertEqual(res.data['message']['code'], 'plan-limit')
        self.assertEqual(res.data['data']['required_plan'], plans.BREEDER)
        self.assertFalse(Rabbit.objects.filter(tag_number='NON5').exists())

    def test_breeder_allows_ten_and_pro_is_unlimited(self):
        get_subscription(self.user).credit(plans.BREEDER)
        self._rabbits(9)
        self.assertEqual(self._add_via_api('R10').status_code, 201)
        self.assertEqual(self._add_via_api('R11').status_code, 402)
        get_subscription(self.user).credit(plans.PRO)
        self.assertEqual(self._add_via_api('R11').status_code, 201)

    def test_expired_subscription_falls_back_to_free_but_keeps_rabbits(self):
        sub = get_subscription(self.user)
        sub.credit(plans.BREEDER)
        self._rabbits(8)
        sub.current_period_end = timezone.now() - timedelta(minutes=1)
        sub.save()
        status = self.client.get('/api/subscriptions/status/').data['data']
        self.assertEqual((status['plan'], status['limit'], status['rabbit_count']), ('free', 4, 8))
        self.assertEqual(status['required_plan'], plans.BREEDER)
        self.assertEqual(self._add_via_api('X').status_code, 402)
        # les fiches existantes restent modifiables
        rabbit = Rabbit.objects.filter(owner=self.user).first()
        self.assertEqual(self.client.patch(f'/api/farm/rabbits/{rabbit.id}/', {'name': 'Neuf'}, format='json').status_code, 200)

    def test_sync_retry_of_an_existing_rabbit_is_not_blocked(self):
        self._rabbits(3)
        payload = {'name': 'A', 'tag_number': 'A1', 'gender': 'M', 'birth_date': self.born.isoformat(),
                   'client_uuid': '7f9c2b1e-1111-4a4a-8b8b-000000000001'}
        self.assertEqual(self.client.post('/api/farm/rabbits/', payload, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/farm/rabbits/', payload, format='json').status_code, 201)

    def test_weaning_and_later_naming_respect_the_limit(self):
        self._rabbits(2)
        mother = Rabbit.objects.create(owner=self.user, name='Mère', tag_number='F0', gender='F', birth_date=self.born)
        litter = Litter.objects.create(owner=self.user, mother=mother, birth_date=date.today() - timedelta(days=50), born_alive=4)
        kits = [{'name': f'K{i}', 'tag_number': f'K{i}', 'gender': 'M'} for i in range(2)]
        res = self.client.post(f'/api/farm/litters/{litter.id}/wean/', {'count': 4, 'rabbits': kits}, format='json')
        self.assertEqual(res.status_code, 402)
        res = self.client.post(f'/api/farm/litters/{litter.id}/wean/', {'count': 4, 'rabbits': kits[:1]}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        res = self.client.post(f'/api/farm/litters/{litter.id}/register-kits/', {'rabbits': [kits[1]]}, format='json')
        self.assertEqual(res.status_code, 402)

    # --- paiement ----------------------------------------------------------

    @mock.patch('subscriptions.geniuspay._request')
    def test_checkout_creates_a_geniuspay_payment(self, request):
        request.return_value = {'reference': 'MTX-1', 'checkout_url': 'https://pay.genius.ci/checkout/MTX-1', 'status': 'pending'}
        res = self.client.post('/api/subscriptions/checkout/', {'plan': 'breeder'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data['data']['checkout_url'], 'https://pay.genius.ci/checkout/MTX-1')
        method, path, body = request.call_args.args
        self.assertEqual((method, path, body['amount'], body['currency']), ('POST', '/payments', 1200, 'XOF'))
        self.assertEqual(body['customer']['phone'], '+2250700000000')
        self.assertEqual(SubscriptionPayment.objects.get().reference, 'MTX-1')

    def test_checkout_refuses_free_or_too_small_plans(self):
        self.assertEqual(self.client.post('/api/subscriptions/checkout/', {'plan': 'free'}, format='json').status_code, 400)
        self._rabbits(12)
        self.assertEqual(self.client.post('/api/subscriptions/checkout/', {'plan': 'breeder'}, format='json').status_code, 400)

    def _pending(self, plan='breeder', amount=1200, ref='MTX-9'):
        return SubscriptionPayment.objects.create(user=self.user, plan=plan, amount=amount, reference=ref)

    def test_webhook_with_bad_signature_is_rejected(self):
        self._pending()
        body, headers = signed({'event': 'payment.success', 'data': {'reference': 'MTX-9'}})
        headers['HTTP_X_WEBHOOK_SIGNATURE'] = '0' * 64
        res = APIClient().post('/api/subscriptions/webhook/', body, content_type='application/json', **headers)
        self.assertEqual(res.status_code, 401)
        self.assertFalse(get_subscription(self.user).is_active)

    @mock.patch('subscriptions.geniuspay._request')
    def test_valid_webhook_credits_30_days_once_after_rechecking_status(self, request):
        request.return_value = {'reference': 'MTX-9', 'status': 'completed', 'amount': 1200}
        self._pending()
        for _ in range(2):
            body, headers = signed({'event': 'payment.success', 'data': {'reference': 'MTX-9'}})
            res = APIClient().post('/api/subscriptions/webhook/', body, content_type='application/json', **headers)
            self.assertEqual(res.status_code, 200)
        request.assert_called_once_with('GET', '/payments/MTX-9')
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.active_plan.code, plans.BREEDER)
        self.assertIn(sub.days_left, (29, 30))
        self.assertEqual(SubscriptionPayment.objects.get().status, 'completed')

    @mock.patch('subscriptions.geniuspay._request')
    def test_webhook_claiming_success_is_ignored_if_geniuspay_says_failed(self, request):
        request.return_value = {'reference': 'MTX-9', 'status': 'failed', 'amount': 1200}
        self._pending()
        body, headers = signed({'event': 'payment.success', 'data': {'reference': 'MTX-9', 'status': 'completed'}})
        APIClient().post('/api/subscriptions/webhook/', body, content_type='application/json', **headers)
        self.assertFalse(get_subscription(self.user).is_active)
        self.assertEqual(SubscriptionPayment.objects.get().status, 'failed')

    @mock.patch('subscriptions.geniuspay._request')
    def test_refresh_after_return_and_renewal_extends_the_period(self, request):
        request.return_value = {'reference': 'MTX-9', 'status': 'completed', 'amount': 1200}
        self._pending()
        res = self.client.post('/api/subscriptions/payments/MTX-9/refresh/')
        self.assertEqual(res.data['data']['subscription']['plan'], plans.BREEDER)
        first_end = get_subscription(self.user).current_period_end

        request.return_value = {'reference': 'MTX-10', 'status': 'completed', 'amount': 1200}
        self._pending(ref='MTX-10')
        self.client.post('/api/subscriptions/payments/MTX-10/refresh/')
        self.assertEqual(get_subscription(self.user).current_period_end, first_end + timedelta(days=30))

    def test_another_users_payment_is_not_visible(self):
        self._pending()
        other = get_user_model().objects.create_user(username='autre', password='x')
        client = APIClient()
        client.force_authenticate(other)
        self.assertEqual(client.post('/api/subscriptions/payments/MTX-9/refresh/').status_code, 404)
