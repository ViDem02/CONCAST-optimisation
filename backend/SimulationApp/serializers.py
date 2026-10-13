from rest_framework import serializers
from .models import SimulationResults


class SimulationResultsSerializer(serializers.ModelSerializer):
    """Serializer for SimulationResults model"""
    
    simulation_name = serializers.CharField(source='simulation.name', read_only=True)
    simulation_id = serializers.IntegerField(source='simulation.id', read_only=True)
    savings_euros = serializers.FloatField(read_only=True)
    savings_percent = serializers.FloatField(read_only=True)
    
    class Meta:
        model = SimulationResults
        fields = [
            'id',
            'simulation',
            'simulation_id',
            'simulation_name',
            'total_electricity_used_kWh',
            'grid_electricity_purchased_kWh',
            'solar_generated_kWh',
            'cogen_generated_kWh',
            'wasted_energy_kWh',
            'original_cost_euros',
            'optimized_cost_euros',
            'savings_euros',
            'savings_percent',
            'total_co2_kg',
            'timestep_data',
            'calculated_at',
            'timestep_minutes',
            'num_timesteps',
        ]
        read_only_fields = [
            'id',
            'simulation',
            'simulation_id',
            'simulation_name',
            'total_electricity_used_kWh',
            'grid_electricity_purchased_kWh',
            'solar_generated_kWh',
            'cogen_generated_kWh',
            'wasted_energy_kWh',
            'original_cost_euros',
            'optimized_cost_euros',
            'savings_euros',
            'savings_percent',
            'total_co2_kg',
            'timestep_data',
            'calculated_at',
            'timestep_minutes',
            'num_timesteps',
        ]


class SimulationResultsSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer without detailed timestep data"""
    
    simulation_name = serializers.CharField(source='simulation.name', read_only=True)
    savings_euros = serializers.FloatField(read_only=True)
    savings_percent = serializers.FloatField(read_only=True)
    
    class Meta:
        model = SimulationResults
        fields = [
            'id',
            'simulation',
            'simulation_name',
            'total_electricity_used_kWh',
            'grid_electricity_purchased_kWh',
            'solar_generated_kWh',
            'cogen_generated_kWh',
            'wasted_energy_kWh',
            'original_cost_euros',
            'optimized_cost_euros',
            'savings_euros',
            'savings_percent',
            'total_co2_kg',
            'calculated_at',
            'timestep_minutes',
            'num_timesteps',
        ]
        read_only_fields = fields
