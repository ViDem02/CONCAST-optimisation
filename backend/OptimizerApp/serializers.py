from rest_framework import serializers
from .models import Optimization


class OptimizationSerializer(serializers.ModelSerializer):
    reference_production_plan_name = serializers.CharField(
        source='reference_production_plan.name',
        read_only=True
    )
    optimized_production_plan_name = serializers.CharField(
        source='optimized_production_plan.name',
        read_only=True,
        allow_null=True
    )
    is_completed = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Optimization
        fields = [
            'id',
            'name',
            'notes',
            'reference_production_plan',
            'reference_production_plan_name',
            'optimized_production_plan',
            'optimized_production_plan_name',
            'reference_week_start',
            'reference_week_end',
            'initial_cost_euros',
            'optimized_cost_euros',
            'cost_savings_euros',
            'cost_savings_percent',
            'optimization_data',
            'is_completed',
            'created_at',
            'completed_at'
        ]
        read_only_fields = [
            'optimized_production_plan',
            'initial_cost_euros',
            'optimized_cost_euros',
            'cost_savings_euros',
            'cost_savings_percent',
            'optimization_data',
            'completed_at'
        ]


class OptimizationDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with full optimization data."""
    reference_production_plan_name = serializers.CharField(
        source='reference_production_plan.name',
        read_only=True
    )
    optimized_production_plan_name = serializers.CharField(
        source='optimized_production_plan.name',
        read_only=True,
        allow_null=True
    )
    is_completed = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Optimization
        fields = '__all__'
        read_only_fields = [
            'optimized_production_plan',
            'initial_cost_euros',
            'optimized_cost_euros',
            'cost_savings_euros',
            'cost_savings_percent',
            'optimization_data',
            'completed_at'
        ]
