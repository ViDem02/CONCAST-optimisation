from datetime import timedelta

from rest_framework import serializers
from .models import Optimization


class ReferenceWeekMixin:
    """The last day of the reference week defaults to 6 days after the first one."""

    def validate(self, attrs):
        start = attrs.get('reference_week_start', getattr(self.instance, 'reference_week_start', None))
        if start and not attrs.get('reference_week_end') and not getattr(self.instance, 'reference_week_end', None):
            attrs['reference_week_end'] = start + timedelta(days=6)
        end = attrs.get('reference_week_end', getattr(self.instance, 'reference_week_end', None))
        if start and end and (end - start).days != 6:
            raise serializers.ValidationError({'reference_week_end': 'The reference period must be exactly one week.'})
        return attrs


class OptimizationSerializer(ReferenceWeekMixin, serializers.ModelSerializer):
    reference_production_plan_name = serializers.CharField(
        source='reference_production_plan.name',
        read_only=True
    )
    optimized_production_plan_name = serializers.CharField(
        source='optimized_production_plan.name',
        read_only=True,
        allow_null=True
    )
    optimizer_label = serializers.CharField(
        source='get_optimizer_display',
        read_only=True
    )
    is_completed = serializers.BooleanField(read_only=True)
    live = serializers.SerializerMethodField()
    
    def get_live(self, obj):
        from .background import progress_of
        return progress_of(obj)
    
    class Meta:
        model = Optimization
        fields = [
            'live',
            'id',
            'name',
            'notes',
            'optimizer',
            'optimizer_label',
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


class OptimizationDetailSerializer(ReferenceWeekMixin, serializers.ModelSerializer):
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
    optimizer_label = serializers.CharField(
        source='get_optimizer_display',
        read_only=True
    )
    is_completed = serializers.BooleanField(read_only=True)
    live = serializers.SerializerMethodField()
    
    def get_live(self, obj):
        from .background import progress_of
        return progress_of(obj)
    
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
