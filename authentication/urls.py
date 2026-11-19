from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserViewSet,
    NotificationViewSet,
    RequestOTPView,
    VerifyOTPView,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('request-otp/', RequestOTPView.as_view(), name='request-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    # Renouvelle le jeton d'accès à partir du jeton de renouvellement (rotation activée)
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
] + router.urls
