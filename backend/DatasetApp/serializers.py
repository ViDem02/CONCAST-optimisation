from django.db.models import Count, Max, Min
from rest_framework import serializers
from .models import (
    TemperatureDataset, TemperatureRecord,
    PricesDataset, PricesRecord,
    GenerationDataset, GenerationRecord
)


class DatasetSummaryMixin(serializers.Serializer):
    """Number of hourly records and dates covered, instead of every record."""
    record_count = serializers.SerializerMethodField()
    first_timestamp = serializers.SerializerMethodField()
    last_timestamp = serializers.SerializerMethodField()

    def _summary(self, obj):
        if not hasattr(obj, '_summary'):
            obj._summary = obj.records.aggregate(n=Count('id'), first=Min('timestamp'), last=Max('timestamp'))
        return obj._summary

    def get_record_count(self, obj):
        return self._summary(obj)['n']

    def get_first_timestamp(self, obj):
        return self._summary(obj)['first']

    def get_last_timestamp(self, obj):
        return self._summary(obj)['last']


DATASET_FIELDS = ['id', 'name', 'record_count', 'first_timestamp', 'last_timestamp', 'created_at', 'updated_at']


class TemperatureRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemperatureRecord
        fields = ['id', 'temperature_dataset', 'timestamp', 'outside_temperature']
        read_only_fields = ['id']


class TemperatureDatasetSerializer(DatasetSummaryMixin, serializers.ModelSerializer):
    class Meta:
        model = TemperatureDataset
        fields = DATASET_FIELDS
        read_only_fields = ['id', 'created_at', 'updated_at']


class PricesRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricesRecord
        fields = ['id', 'prices_dataset', 'timestamp', 'electricity_price']
        read_only_fields = ['id']


class PricesDatasetSerializer(DatasetSummaryMixin, serializers.ModelSerializer):
    class Meta:
        model = PricesDataset
        fields = DATASET_FIELDS
        read_only_fields = ['id', 'created_at', 'updated_at']


class GenerationRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenerationRecord
        fields = ['id', 'generation_dataset', 'timestamp', 'ele_generated_by_solar_kWh', 'ele_generated_by_cogen_kWh']
        read_only_fields = ['id']


class GenerationDatasetSerializer(DatasetSummaryMixin, serializers.ModelSerializer):
    class Meta:
        model = GenerationDataset
        fields = DATASET_FIELDS
        read_only_fields = ['id', 'created_at', 'updated_at']
