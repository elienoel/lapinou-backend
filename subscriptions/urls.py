from django.urls import path

from .views import CheckoutView, GeniusPayWebhookView, PaymentRefreshView, SubscriptionStatusView

urlpatterns = [
    path('status/', SubscriptionStatusView.as_view(), name='subscription-status'),
    path('checkout/', CheckoutView.as_view(), name='subscription-checkout'),
    path('payments/<str:reference>/refresh/', PaymentRefreshView.as_view(), name='subscription-payment-refresh'),
    path('webhook/', GeniusPayWebhookView.as_view(), name='subscription-webhook'),
]
