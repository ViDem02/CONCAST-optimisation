from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TemperatureDatasetViewSet, TemperatureRecordViewSet,
    PricesDatasetViewSet, PricesRecordViewSet,
    GenerationDatasetViewSet, GenerationRecordViewSet
)

router = DefaultRouter()
router.register(r'temperature-datasets', TemperatureDatasetViewSet, basename='temperaturedataset')
router.register(r'temperature-records', TemperatureRecordViewSet, basename='temperaturerecord')
router.register(r'prices-datasets', PricesDatasetViewSet, basename='pricesdataset')
router.register(r'prices-records', PricesRecordViewSet, basename='pricesrecord')
router.register(r'generation-datasets', GenerationDatasetViewSet, basename='generationdataset')
router.register(r'generation-records', GenerationRecordViewSet, basename='generationrecord')

urlpatterns = [
    path('', include(router.urls)),
]
