from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OptimizationViewSet

router = DefaultRouter()
router.register(r'optimizations', OptimizationViewSet, basename='optimization')

urlpatterns = [
    path('', include(router.urls)),
]
