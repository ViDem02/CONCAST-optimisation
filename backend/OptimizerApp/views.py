from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Optimization
from .serializers import OptimizationSerializer, OptimizationDetailSerializer
from .optimizer_packager import run_optimization


class OptimizationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Optimization objects.
    
    Endpoints:
    - GET /api/optimizer/optimizations/ - List all optimizations
    - POST /api/optimizer/optimizations/ - Create new optimization
    - GET /api/optimizer/optimizations/{id}/ - Get optimization details
    - PUT /api/optimizer/optimizations/{id}/ - Update optimization
    - DELETE /api/optimizer/optimizations/{id}/ - Delete optimization
    - POST /api/optimizer/optimizations/{id}/run/ - Run optimization calculation
    """
    queryset = Optimization.objects.all()
    serializer_class = OptimizationSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['reference_production_plan', 'reference_week_start', 'reference_week_end']
    search_fields = ['name', 'notes']
    ordering_fields = ['created_at', 'completed_at', 'cost_savings_euros']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return OptimizationDetailSerializer
        return OptimizationSerializer
    
    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """
        Run optimization calculation for this optimization object.
        
        POST /api/optimizer/optimizations/{id}/run/
        
        Returns the updated optimization object with results.
        """
        optimization = self.get_object()
        
        try:
            result = run_optimization(optimization.id)
            serializer = OptimizationDetailSerializer(result)
            
            return Response({
                'message': 'Optimization completed successfully',
                'optimization': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def run_by_id(self, request):
        """
        Run optimization by providing optimization_id in request body.
        
        POST /api/optimizer/optimizations/run_by_id/
        Body: {"optimization_id": 1}
        """
        optimization_id = request.data.get('optimization_id')
        
        if not optimization_id:
            return Response({
                'error': 'optimization_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            optimization = Optimization.objects.get(id=optimization_id)
        except Optimization.DoesNotExist:
            return Response({
                'error': f'Optimization with id {optimization_id} does not exist'
            }, status=status.HTTP_404_NOT_FOUND)
        
        try:
            result = run_optimization(optimization_id)
            serializer = OptimizationDetailSerializer(result)
            
            return Response({
                'message': 'Optimization completed successfully',
                'optimization': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
