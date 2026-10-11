from rest_framework import serializers
from .models import (
    TemperatureDataset, TemperatureRecord,
    PricesDataset, PricesRecord,
    GenerationDataset, GenerationRecord
)


class TemperatureRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemperatureRecord
        fields = ['id', 'temperature_dataset', 'timestamp', 'outside_temperature']
        read_only_fields = ['id']


class TemperatureDatasetSerializer(serializers.ModelSerializer):
    records = TemperatureRecordSerializer(many=True, read_only=True)
    
    class Meta:
        model = TemperatureDataset
        fields = ['id', 'is_active', 'name', 'records', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class PricesRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricesRecord
        fields = ['id', 'prices_dataset', 'timestamp', 'electricity_price', 'methane_price']
        read_only_fields = ['id']


class PricesDatasetSerializer(serializers.ModelSerializer):
    records = PricesRecordSerializer(many=True, read_only=True)
    
    class Meta:
        model = PricesDataset
        fields = ['id', 'is_active', 'name', 'records', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class GenerationRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenerationRecord
        fields = ['id', 'generation_dataset', 'timestamp', 'ele_generated_by_solar_kWh', 'ele_generated_by_cogen_kWh']
        read_only_fields = ['id']


class GenerationDatasetSerializer(serializers.ModelSerializer):
    records = GenerationRecordSerializer(many=True, read_only=True)
    
    class Meta:
        model = GenerationDataset
        fields = ['id', 'is_active', 'name', 'records', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
