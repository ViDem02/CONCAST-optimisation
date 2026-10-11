from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class WeeklyProductionPlan(models.Model):
    """Weekly production plan with optimization flag."""
    name = models.CharField(max_length=255, unique=True)
    is_optimized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({'optimized' if self.is_optimized else 'not optimized'})"


class Process(models.Model):
    """Production process with electricity consumption."""
    name = models.CharField(max_length=255)
    electricity_consumption_kWh = models.IntegerField(
        help_text="Electricity consumption in kWh",
        validators=[MinValueValidator(0)]
    )
    production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.CASCADE,
        related_name='processes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = [['name', 'production_plan']]
    
    def __str__(self):
        return f"{self.name} ({self.electricity_consumption_kWh} kWh)"


class Shift(models.Model):
    """Shift schedule for a production process."""
    WEEKDAYS = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    name = models.CharField(max_length=255)
    process = models.ForeignKey(
        Process,
        on_delete=models.CASCADE,
        related_name='shifts'
    )
    start_day = models.IntegerField(choices=WEEKDAYS)
    end_day = models.IntegerField(choices=WEEKDAYS)
    start_hour = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Start hour (0-23)"
    )
    start_minutes = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Start minutes (0-55, must be multiple of 5)",
        default=0
    )
    end_hour = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="End hour (0-23)"
    )
    end_minutes = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="End minutes (0-55, must be multiple of 5)",
        default=0
    )
    max_forward_minutes = models.IntegerField(
        help_text="Maximum minutes the shift can be moved forward (must be multiple of 5)",
        validators=[MinValueValidator(0)]
    )
    max_backwards_minutes = models.IntegerField(
        help_text="Maximum minutes the shift can be moved backward (must be multiple of 5)",
        validators=[MinValueValidator(0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['start_day', 'start_hour', 'start_minutes']
        unique_together = [['name', 'process']]
    
    def clean(self):
        if self.start_hour < 0 or self.start_hour > 23:
            raise ValidationError({'start_hour': 'Start hour must be between 0 and 23'})
        if self.end_hour < 0 or self.end_hour > 23:
            raise ValidationError({'end_hour': 'End hour must be between 0 and 23'})
        if self.start_minutes < 0 or self.start_minutes > 55:
            raise ValidationError({'start_minutes': 'Start minutes must be between 0 and 55'})
        if self.end_minutes < 0 or self.end_minutes > 55:
            raise ValidationError({'end_minutes': 'End minutes must be between 0 and 55'})
        if self.start_minutes % 5 != 0:
            raise ValidationError({'start_minutes': 'Must be a multiple of 5'})
        if self.end_minutes % 5 != 0:
            raise ValidationError({'end_minutes': 'Must be a multiple of 5'})
        if self.max_forward_minutes % 5 != 0:
            raise ValidationError({'max_forward_minutes': 'Must be a multiple of 5'})
        if self.max_backwards_minutes % 5 != 0:
            raise ValidationError({'max_backwards_minutes': 'Must be a multiple of 5'})
    
    def __str__(self):
        return f"{self.name} - {self.get_start_day_display()} {self.start_hour:02d}:{self.start_minutes:02d} to {self.get_end_day_display()} {self.end_hour:02d}:{self.end_minutes:02d}"


class Simulation(models.Model):
    """Simulation configuration."""
    name = models.CharField(max_length=255, unique=True)
    notes = models.TextField(blank=True)
    # Deprecated: use original_production_plan and optimized_production_plan
    reference_production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.CASCADE,
        related_name='simulations',
        null=True,
        blank=True,
        help_text="[Deprecated] Use original_production_plan / optimized_production_plan"
    )
    original_production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.CASCADE,
        related_name='simulations_original',
        help_text="Weekly production plan without optimization",
        null=True,
        blank=True,
    )
    optimized_production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.CASCADE,
        related_name='simulations_optimized',
        help_text="Weekly production plan after optimization",
        null=True,
        blank=True,
    )
    generation_dataset = models.ForeignKey(
        'DatasetApp.GenerationDataset',
        on_delete=models.PROTECT,
        related_name='simulations',
        help_text="Generation dataset to use for this simulation", 
        null=True,
        blank=True,
    )
    prices_dataset = models.ForeignKey(
        'DatasetApp.PricesDataset',
        on_delete=models.PROTECT,
        related_name='simulations',
        help_text="Prices dataset to use for this simulation",
        null=True,
        blank=True,
    )
    start_date = models.DateField(help_text="Date at which the simulation starts")
    end_date = models.DateField(help_text="Date at which the simulation ends")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': 'End date must be after start date'})
    
    def __str__(self):
        try:
            orig = getattr(self, 'original_production_plan', None)
            opti = getattr(self, 'optimized_production_plan', None)
            if orig and opti:
                return f"{self.name} [{orig.name} → {opti.name}] ({self.start_date} to {self.end_date})"
        except Exception:
            pass
        return f"{self.name} ({self.start_date} to {self.end_date})"