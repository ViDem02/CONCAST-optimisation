from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    TemperatureDataset, TemperatureRecord,
    PricesDataset, PricesRecord,
    GenerationDataset, GenerationRecord
)
from .serializers import (
    TemperatureDatasetSerializer, TemperatureRecordSerializer,
    PricesDatasetSerializer, PricesRecordSerializer,
    GenerationDatasetSerializer, GenerationRecordSerializer
)


class TemperatureDatasetViewSet(viewsets.ModelViewSet):
    """API endpoint for TemperatureDataset."""
    queryset = TemperatureDataset.objects.all()
    serializer_class = TemperatureDatasetSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['name']
    search_fields = ['name']
    ordering_fields = ['created_at', 'name']


class TemperatureRecordViewSet(viewsets.ModelViewSet):
    """API endpoint for TemperatureRecord."""
    queryset = TemperatureRecord.objects.all()
    serializer_class = TemperatureRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['temperature_dataset']
    ordering_fields = ['timestamp']


class PricesDatasetViewSet(viewsets.ModelViewSet):
    """API endpoint for PricesDataset."""
    queryset = PricesDataset.objects.all()
    serializer_class = PricesDatasetSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['name']
    search_fields = ['name']
    ordering_fields = ['created_at', 'name']


class PricesRecordViewSet(viewsets.ModelViewSet):
    """API endpoint for PricesRecord."""
    queryset = PricesRecord.objects.all()
    serializer_class = PricesRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['prices_dataset']
    ordering_fields = ['timestamp']


class GenerationDatasetViewSet(viewsets.ModelViewSet):
    """API endpoint for GenerationDataset."""
    queryset = GenerationDataset.objects.all()
    serializer_class = GenerationDatasetSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['name']
    search_fields = ['name']
    ordering_fields = ['created_at', 'name']


class GenerationRecordViewSet(viewsets.ModelViewSet):
    """API endpoint for GenerationRecord."""
    queryset = GenerationRecord.objects.all()
    serializer_class = GenerationRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['generation_dataset']
    ordering_fields = ['timestamp']
