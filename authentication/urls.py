from django.urls import path
from rest_framework.routers import DefaultRouter
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
] + router.urls
