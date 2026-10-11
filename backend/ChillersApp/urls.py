from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChillerViewSet, ChillerSimulationViewSet

router = DefaultRouter()
router.register(r'chillers', ChillerViewSet, basename='chiller')
router.register(r'chiller-simulations', ChillerSimulationViewSet, basename='chillersimulation')

urlpatterns = [
    path('', include(router.urls)),
]
