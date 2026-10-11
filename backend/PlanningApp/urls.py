from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WeeklyProductionPlanViewSet, ProcessViewSet, ShiftViewSet,
    SimulationViewSet
)

router = DefaultRouter()
router.register(r'production-plans', WeeklyProductionPlanViewSet, basename='weeklyproductionplan')
router.register(r'processes', ProcessViewSet, basename='process')
router.register(r'shifts', ShiftViewSet, basename='shift')
router.register(r'simulations', SimulationViewSet, basename='simulation')

urlpatterns = [
    path('', include(router.urls)),
]
