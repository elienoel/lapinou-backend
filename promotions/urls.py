from django.urls import path

from .views import ActiveCarouselsView

urlpatterns = [
    path('carousels/', ActiveCarouselsView.as_view(), name='promo-carousels'),
]
