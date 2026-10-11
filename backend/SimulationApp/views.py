from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import SimulationResults
from .serializers import SimulationResultsSerializer, SimulationResultsSummarySerializer
from .simulation import run_simulation


class SimulationResultsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing SimulationResults.
    
    Provides list and retrieve endpoints.
    SimulationResults can only be created through the run_simulation action.
    """
    queryset = SimulationResults.objects.all()
    serializer_class = SimulationResultsSerializer
    
    def get_serializer_class(self):
        """
        Use summary serializer for list view unless include_timestep_data is requested.
        For retrieve view, use summary serializer unless include_timestep_data is requested.
        """
        include_timestep = self.request.query_params.get('include_timestep_data', '').lower() in ['true', '1', 'yes']
        
        if include_timestep:
            return SimulationResultsSerializer
        
        if self.action in ['list', 'retrieve']:
            return SimulationResultsSummarySerializer
        
        return SimulationResultsSerializer
    
    @action(detail=False, methods=['post'], url_path='run-simulation')
    def run_simulation_action(self, request):
        """
        Run a simulation calculation.
        
        POST /api/simulation-results/run-simulation/
        Body: {"simulation_id": 1}
        
        Returns the calculated SimulationResults.
        """
        simulation_id = request.data.get('simulation_id')
        
        if not simulation_id:
            return Response(
                {'error': 'simulation_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            results = run_simulation(simulation_id)
            serializer = self.get_serializer(results)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'], url_path='timestep-data')
    def get_timestep_data(self, request, pk=None):
        """
        Get detailed timestep data for a simulation result.
        
        GET /api/simulation-results/{id}/timestep-data/
        
        Returns only the timestep_data field.
        """
        results = self.get_object()
        return Response({
            'simulation_id': results.simulation.id,
            'simulation_name': results.simulation.name,
            'timestep_data': results.timestep_data,
        })
    
    @action(detail=True, methods=['get'], url_path='export-csv')
    def export_csv(self, request, pk=None):
        """
        Export simulation results to CSV format for MATLAB.
        
        GET /api/simulation-results/{id}/export-csv/
        
        Returns CSV file with timestep data.
        """
        from .utils import export_simulation_results_to_csv
        
        results = self.get_object()
        
        try:
            response = export_simulation_results_to_csv(results)
            return response
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
