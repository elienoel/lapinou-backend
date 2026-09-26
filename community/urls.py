from rest_framework.routers import DefaultRouter
from .views import (
    PostViewSet,
    CommentViewSet,
    MarketplaceListingViewSet,
)

router = DefaultRouter()
router.register(r'posts', PostViewSet, basename='post')
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'marketplace', MarketplaceListingViewSet, basename='marketplace')

urlpatterns = router.urls
