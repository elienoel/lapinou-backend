from rest_framework.routers import DefaultRouter
from .views import MedicationViewSet, PharmacyViewSet

router = DefaultRouter()
router.register(r'medications', MedicationViewSet, basename='medication')
router.register(r'pharmacies', PharmacyViewSet, basename='pharmacy')

urlpatterns = router.urls
