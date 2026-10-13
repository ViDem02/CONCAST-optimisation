from rest_framework import serializers
from .models import WeeklyProductionPlan, Process, Shift, Simulation


class ShiftSerializer(serializers.ModelSerializer):
    start_day_display = serializers.CharField(source='get_start_day_display', read_only=True)
    end_day_display = serializers.CharField(source='get_end_day_display', read_only=True)
    
    class Meta:
        model = Shift
        fields = [
            'id', 'name', 'process', 'start_day', 'start_day_display', 
            'end_day', 'end_day_display', 'start_hour', 'start_minutes',
            'end_hour', 'end_minutes', 'max_forward_minutes', 'max_backwards_minutes', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProcessSerializer(serializers.ModelSerializer):
    shifts = ShiftSerializer(many=True, read_only=True)
    
    class Meta:
        model = Process
        fields = [
            'id', 'name', 'electricity_consumption_kWh', 
            'production_plan', 'shifts', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WeeklyProductionPlanSerializer(serializers.ModelSerializer):
    processes = ProcessSerializer(many=True, read_only=True)
    
    class Meta:
        model = WeeklyProductionPlan
        fields = ['id', 'name', 'is_optimized', 'processes', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class SimulationSerializer(serializers.ModelSerializer):
    original_production_plan_name = serializers.CharField(source='original_production_plan.name', read_only=True)
    optimized_production_plan_name = serializers.CharField(
        source='optimized_production_plan.name', read_only=True, allow_null=True)
    generation_dataset_name = serializers.CharField(source='generation_dataset.name', read_only=True)
    prices_dataset_name = serializers.CharField(source='prices_dataset.name', read_only=True)
    results = serializers.SerializerMethodField()

    class Meta:
        model = Simulation
        fields = [
            'id', 'name', 'notes',
            'original_production_plan', 'original_production_plan_name',
            'optimized_production_plan', 'optimized_production_plan_name',
            'generation_dataset', 'generation_dataset_name', 'prices_dataset', 'prices_dataset_name',
            'start_date', 'end_date', 'results', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_results(self, obj):
        """Summary of the results, or None if the simulation has not been calculated."""
        results = getattr(obj, 'results', None)
        if results is None:
            return None
        return {
            'id': results.id,
            'original_cost_euros': results.original_cost_euros,
            'optimized_cost_euros': results.optimized_cost_euros,
            'savings_euros': results.savings_euros,
            'savings_percent': results.savings_percent,
            'calculated_at': results.calculated_at,
        }
