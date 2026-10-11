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
    reference_production_plan_name = serializers.CharField(
        source='reference_production_plan.name', 
        read_only=True
    )
    
    class Meta:
        model = Simulation
        fields = [
            'id', 'name', 'notes', 'reference_production_plan', 
            'reference_production_plan_name', 'start_date', 'end_date', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

