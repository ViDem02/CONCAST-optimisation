from datetime import timedelta

from django.core.exceptions import ValidationError
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
        verbose_name='plan to optimise',
        help_text="The production plan whose flexible shifts will be moved"
    )
    
    optimized_production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='optimizations_as_result',
        verbose_name='optimised plan',
        help_text="The new production plan written by the optimisation"
    )
    
    optimized_plan_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='name of the optimised plan',
        help_text="Leave empty to use the name of the plan to optimise followed by \"_optimized\""
    )
    
    reference_week_start = models.DateField(
        verbose_name='reference week: first day',
        help_text="Usually a Monday. The solar/cogeneration and prices of this week are used to choose the shifts"
    )
    
    reference_week_end = models.DateField(
        blank=True,
        verbose_name='reference week: last day',
        help_text="Leave empty: it is set to 6 days after the first day"
    )
    
    generation_dataset = models.ForeignKey(
        'DatasetApp.GenerationDataset',
        on_delete=models.PROTECT,
        verbose_name='on-site generation',
        help_text="Solar and cogeneration data to use",
        null=True,
    )
    
    prices_dataset = models.ForeignKey(
        'DatasetApp.PricesDataset',
        on_delete=models.PROTECT,
        verbose_name='electricity prices',
        help_text="Grid electricity prices to use",
        null=True,
    )
    
    notes = models.TextField(blank=True, help_text="Optional notes")
    
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
    
    # Live state of the calculation (see OptimizerApp.background)
    STATUS_CHOICES = [('new', 'Not calculated'), ('running', 'Calculating'), ('done', 'Calculated'), ('failed', 'Failed')]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new', editable=False)
    progress = models.JSONField(null=True, blank=True, editable=False,
                                help_text="Current step of the calculation, updated while it runs")
    error = models.TextField(blank=True, editable=False, help_text="Why the last calculation failed")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'shift optimisation'
    
    def __str__(self):
        return f"{self.name}"
    
    def clean(self):
        if self.reference_week_start and not self.reference_week_end:
            self.reference_week_end = self.reference_week_start + timedelta(days=6)
        if self.reference_week_start and self.reference_week_end \
                and (self.reference_week_end - self.reference_week_start).days != 6:
            raise ValidationError({'reference_week_end': 'The reference period must be exactly one week: '
                                                         'leave this empty or choose the day 6 days after the first day.'})
    
    def is_completed(self):
        """Check if optimization has been completed."""
        return self.optimized_production_plan is not None and self.completed_at is not None
