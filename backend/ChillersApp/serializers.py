"""Serializers for ChillersApp REST API."""

from rest_framework import serializers
from .models import Chiller, ChillerSimulation


class ChillerSerializer(serializers.ModelSerializer):
    """Serializer for Chiller model."""
    
    class Meta:
        model = Chiller
        fields = [
            'id', 'name', 'insulation_u_value', 'surface_area',
            'nominal_capacity_kW', 'nominal_cooling_rate', 'chiller_efficiency',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class ChillerSimulationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing chiller simulations."""
    
    chiller_name = serializers.CharField(source='chiller.name', read_only=True)
    has_results = serializers.SerializerMethodField()
    production_plan_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ChillerSimulation
        fields = [
            'id', 'name', 'chiller', 'chiller_name',
            'start_date', 'end_date',
            'min_temperature', 'max_temperature',
            'initial_window_hours',
            'proportional_gain', 'derivative_gain',
            'production_plan_result', 'production_plan_name',
            'has_results', 'created_at'
        ]
        read_only_fields = ['created_at']
    
    def get_has_results(self, obj):
        """Check if simulation has results."""
        return bool(obj.chiller_power_delivery and obj.calculated_temperature)
    
    def get_production_plan_name(self, obj):
        """Get production plan name if linked."""
        if obj.production_plan_result:
            return obj.production_plan_result.simulation.name
        return None


class ChillerSimulationDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for chiller simulation with results."""
    
    chiller_name = serializers.CharField(source='chiller.name', read_only=True)
    chiller_details = ChillerSerializer(source='chiller', read_only=True)
    production_plan_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ChillerSimulation
        fields = [
            'id', 'name', 'chiller', 'chiller_name', 'chiller_details',
            'start_date', 'end_date',
            'min_temperature', 'max_temperature',
            'target_temperature', 'initial_window_hours',
            'proportional_gain', 'derivative_gain',
            'allow_grid_power', 'minimum_runtime_minutes',
            'production_plan_result', 'production_plan_name',
            'chiller_power_delivery', 'calculated_temperature',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'chiller_power_delivery', 'calculated_temperature',
            'created_at', 'updated_at'
        ]
    
    def get_production_plan_name(self, obj):
        """Get production plan name if linked."""
        if obj.production_plan_result:
            return obj.production_plan_result.simulation.name
        return None


# Keep old serializer for backward compatibility
ChillerSimulationSerializer = ChillerSimulationListSerializer
