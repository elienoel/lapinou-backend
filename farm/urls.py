from rest_framework.routers import DefaultRouter
from .views import (
    BreedViewSet,
    CageViewSet,
    RabbitViewSet,
    MatingViewSet,
    LitterViewSet,
    CareTreatmentViewSet,
    CareRecordViewSet,
    CareEventViewSet,
    FinanceTransactionViewSet,
)

router = DefaultRouter()
router.register(r'breeds', BreedViewSet, basename='breed')
router.register(r'cages', CageViewSet, basename='cage')
router.register(r'rabbits', RabbitViewSet, basename='rabbit')
router.register(r'matings', MatingViewSet, basename='mating')
router.register(r'litters', LitterViewSet, basename='litter')
router.register(r'care-treatments', CareTreatmentViewSet, basename='care-treatment')
router.register(r'care-records', CareRecordViewSet, basename='care-record')
router.register(r'care-events', CareEventViewSet, basename='care-event')
router.register(r'finances', FinanceTransactionViewSet, basename='finance')

urlpatterns = router.urls
