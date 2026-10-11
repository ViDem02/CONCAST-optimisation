from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SimulationResultsViewSet

router = DefaultRouter()
router.register(r'simulation-results', SimulationResultsViewSet, basename='simulationresults')

urlpatterns = [
    path('', include(router.urls)),
]
