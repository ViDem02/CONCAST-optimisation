from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import WeeklyProductionPlan, Process, Shift, Simulation
from .serializers import (
    WeeklyProductionPlanSerializer, ProcessSerializer, ShiftSerializer,
    SimulationSerializer
)


class WeeklyProductionPlanViewSet(viewsets.ModelViewSet):
    """API endpoint for WeeklyProductionPlan."""
    queryset = WeeklyProductionPlan.objects.all()
    serializer_class = WeeklyProductionPlanSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_optimized']
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']


class ProcessViewSet(viewsets.ModelViewSet):
    """API endpoint for Process."""
    queryset = Process.objects.all()
    serializer_class = ProcessSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['production_plan']
    search_fields = ['name']
    ordering_fields = ['name', 'electricity_consumption_kWh']


class ShiftViewSet(viewsets.ModelViewSet):
    """API endpoint for Shift."""
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['process', 'start_day', 'end_day']
    search_fields = ['name']
    ordering_fields = ['start_day', 'start_hour']


class SimulationViewSet(viewsets.ModelViewSet):
    """API endpoint for Simulation."""
    queryset = Simulation.objects.all()
    serializer_class = SimulationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['reference_production_plan']
    search_fields = ['name', 'notes']
    ordering_fields = ['name', 'start_date', 'created_at']
    
    @action(detail=True, methods=['post'], url_path='run')
    def run(self, request, pk=None):
        """
        Run simulation calculation for this simulation.
        
        POST /api/planning/simulations/{id}/run/
        
        Returns the calculated SimulationResults.
        """
        from SimulationApp.simulation import run_simulation
        from SimulationApp.serializers import SimulationResultsSerializer
        
        simulation = self.get_object()
        
        try:
            results = run_simulation(simulation.id)
            serializer = SimulationResultsSerializer(results)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

