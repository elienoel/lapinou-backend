"""
Client minimal de l'API marchand GeniusPay (https://pay.genius.ci/docs/api).
Les clés viennent des variables d'environnement ; le mode sandbox ou live
dépend uniquement du préfixe des clés (pk_sandbox_ / pk_live_).
"""
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from django.conf import settings

TIMEOUT = 20
# Écart toléré entre l'horodatage d'un webhook et maintenant (anti-rejeu)
WEBHOOK_TOLERANCE = 300


class GeniusPayError(Exception):
    pass


def _request(method, path, body=None):
    if not settings.GENIUSPAY_API_KEY or not settings.GENIUSPAY_API_SECRET:
        raise GeniusPayError('GeniusPay n\'est pas configuré (clés API manquantes).')
    url = settings.GENIUSPAY_BASE_URL.rstrip('/') + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'X-API-Key': settings.GENIUSPAY_API_KEY,
        'X-API-Secret': settings.GENIUSPAY_API_SECRET,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            payload = json.loads(res.read() or b'{}')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors='replace')[:500]
        raise GeniusPayError(f'GeniusPay {exc.code} : {detail}') from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise GeniusPayError(f'GeniusPay injoignable : {exc}') from exc
    if not payload.get('success', True) or 'data' not in payload:
        raise GeniusPayError(f'Réponse GeniusPay inattendue : {str(payload)[:500]}')
    return payload['data']


def create_payment(*, amount, description, customer, metadata, success_url='', error_url=''):
    """Crée un paiement sur la page hébergée GeniusPay ; renvoie `data` (reference, checkout_url...)."""
    body = {
        'amount': amount,
        'currency': 'XOF',
        'description': description[:500],
        'customer': {k: v for k, v in customer.items() if v},
        'metadata': metadata,
    }
    if success_url:
        body['success_url'] = success_url
    if error_url:
        body['error_url'] = error_url
    return _request('POST', '/payments', body)


def get_payment(reference):
    return _request('GET', f'/payments/{reference}')


def verify_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """HMAC-SHA256 (hex) de « timestamp.corps » avec le secret du webhook."""
    secret = settings.GENIUSPAY_WEBHOOK_SECRET
    if not secret or not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > WEBHOOK_TOLERANCE:
            return False
    except ValueError:
        return False
    expected = hmac.new(
        secret.encode(), f'{timestamp}.'.encode() + body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.strip())
