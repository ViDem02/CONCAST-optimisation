from django.db import models
from django.core.validators import MinValueValidator
from PlanningApp.models import WeeklyProductionPlan
from .optimizers import OPTIMIZER_CHOICES, DEFAULT_OPTIMIZER


class Optimization(models.Model):
    """
    Optimization entity that stores an optimization run.
    
    Takes a reference production plan and creates an optimized version
    by shifting process shifts within allowed time windows to minimize costs.
    """
    name = models.CharField(max_length=255, unique=True)
    notes = models.TextField(blank=True, help_text="Additional notes about this optimization")
    
    optimizer = models.CharField(
        max_length=50,
        choices=OPTIMIZER_CHOICES,
        default=DEFAULT_OPTIMIZER,
        help_text="Optimization algorithm used to compute the shifts"
    )
    
    reference_production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.PROTECT,
        related_name='optimizations_as_reference',
        help_text="The original production plan to optimize"
    )
    
    optimized_production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='optimizations_as_result',
        help_text="The resulting optimized production plan (created after optimization)"
    )
    
    optimized_plan_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name for the optimized production plan (if empty, auto-generates from reference plan name)"
    )
    
    reference_week_start = models.DateField(
        help_text="Start date of the reference week for generation and prices data"
    )
    
    reference_week_end = models.DateField(
        help_text="End date of the reference week for generation and prices data"
    )
    
    generation_dataset = models.ForeignKey(
        'DatasetApp.GenerationDataset',
        on_delete=models.PROTECT,
        help_text="Generation dataset to use for optimization",
        null=True,
    )
    
    prices_dataset = models.ForeignKey(
        'DatasetApp.PricesDataset',
        on_delete=models.PROTECT,
        help_text="Prices dataset to use for optimization",
        null=True,
    )
    
    # Optimization results
    initial_cost_euros = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Cost before optimization (€)"
    )
    
    optimized_cost_euros = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Cost after optimization (€)"
    )
    
    cost_savings_euros = models.FloatField(
        null=True,
        blank=True,
        help_text="Cost savings achieved (€)"
    )
    
    cost_savings_percent = models.FloatField(
        null=True,
        blank=True,
        help_text="Cost savings as percentage (%)"
    )
    
    optimization_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Detailed optimization data including shift changes, iterations, etc."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name}"
    
    def is_completed(self):
        """Check if optimization has been completed."""
        return self.optimized_production_plan is not None and self.completed_at is not None
