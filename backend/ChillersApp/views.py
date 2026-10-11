"""REST API views for ChillersApp."""

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
import csv

from .models import Chiller, ChillerSimulation
from .serializers import (
    ChillerSerializer, 
    ChillerSimulationListSerializer,
    ChillerSimulationDetailSerializer
)
from .chiller_control import run_chiller_simulation


class ChillerViewSet(viewsets.ModelViewSet):
    """API endpoint for Chiller."""
    
    queryset = Chiller.objects.all()
    serializer_class = ChillerSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'insulation_u_value', 'surface_area', 'created_at']
    ordering = ['-created_at']


class ChillerSimulationViewSet(viewsets.ModelViewSet):
    """API endpoint for ChillerSimulation with run action."""
    
    queryset = ChillerSimulation.objects.all()
    serializer_class = ChillerSimulationListSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['chiller']
    search_fields = ['name', 'chiller__name']
    ordering_fields = ['name', 'start_date', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Use detailed serializer for retrieve action."""
        if self.action == 'retrieve':
            return ChillerSimulationDetailSerializer
        return ChillerSimulationListSerializer
    
    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """
        Run chiller simulation with PD control.
        
        POST /api/chillers/simulations/{id}/run/
        """
        simulation = self.get_object()
        
        try:
            result = run_chiller_simulation(simulation.id)
            serializer = ChillerSimulationDetailSerializer(result)
            
            return Response({
                'status': 'success',
                'message': f'Simulation "{simulation.name}" completed successfully',
                'data': serializer.data
            })
        
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def run_by_id(self, request):
        """
        Run simulation by ID provided in request body.
        
        POST /api/chillers/simulations/run_by_id/
        Body: {"simulation_id": 1}
        """
        simulation_id = request.data.get('simulation_id')
        
        if not simulation_id:
            return Response({
                'status': 'error',
                'message': 'simulation_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            simulation = ChillerSimulation.objects.get(id=simulation_id)
        except ChillerSimulation.DoesNotExist:
            return Response({
                'status': 'error',
                'message': f'Simulation with ID {simulation_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        try:
            result = run_chiller_simulation(simulation.id)
            serializer = ChillerSimulationDetailSerializer(result)
            
            return Response({
                'status': 'success',
                'message': f'Simulation "{simulation.name}" completed successfully',
                'data': serializer.data
            })
        
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def export_csv(self, request, pk=None):
        """
        Export simulation results to CSV file.
        
        GET /api/chillers/chiller-simulations/{id}/export_csv/
        """
        simulation = self.get_object()
        
        if not simulation.chiller_power_delivery or not simulation.calculated_temperature:
            return Response({
                'status': 'error',
                'message': 'Simulation has no results yet. Run simulation first.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="chiller_simulation_{simulation.id}_{simulation.name}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'Timestamp',
            'Chiller Temperature (°C)',
            'Outside Temperature (°C)',
            'Power Delivery (kW)',
            'Grid Consumption (kW)',
            'Wasted Energy (kW)'
        ])
        
        # Write data
        temp_data = simulation.calculated_temperature
        power_data = simulation.chiller_power_delivery
        
        from datetime import datetime
        for i, timestamp in enumerate(temp_data['timestamps']):
            # Parse ISO format and convert to desired format
            dt = datetime.fromisoformat(timestamp)
            formatted_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Get outside temperature if available (for backward compatibility)
            outside_temp = temp_data.get('outside_temperature_C', [None] * len(temp_data['timestamps']))[i]
            
            writer.writerow([
                formatted_timestamp,
                temp_data['temperature_C'][i],
                outside_temp if outside_temp is not None else '',
                power_data['power_kW'][i],
                power_data['grid_consumption_kW'][i],
                power_data['wasted_energy_kW'][i]
            ])
        
        return response
