from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class WeeklyProductionPlan(models.Model):
    """Weekly production plan (a template that repeats every week)."""
    name = models.CharField(max_length=255, unique=True)
    is_optimized = models.BooleanField(
        default=False, verbose_name='created by an optimisation',
        help_text='True for plans written by a shift optimisation'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'production plan'
    
    def __str__(self):
        return f"{self.name} (optimised)" if self.is_optimized else self.name


class Process(models.Model):
    """Production process with electricity consumption."""
    name = models.CharField(max_length=255)
    electricity_consumption_kWh = models.IntegerField(
        verbose_name='power while running (kW)',
        help_text="Electricity drawn while the process is running, i.e. kWh consumed in one hour",
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
        verbose_name = 'process'
        verbose_name_plural = 'processes'
    
    def __str__(self):
        return f"{self.name} ({self.electricity_consumption_kWh} kW)"


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
        verbose_name='may start later by (min)',
        help_text="How many minutes the optimisation may delay this shift (multiple of 5, 0 = never later)",
        validators=[MinValueValidator(0)]
    )
    max_backwards_minutes = models.IntegerField(
        verbose_name='may start earlier by (min)',
        help_text="How many minutes the optimisation may bring this shift forward (multiple of 5, 0 = never earlier)",
        validators=[MinValueValidator(0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['start_day', 'start_hour', 'start_minutes']
        unique_together = [['name', 'process']]
    
    def clean(self):
        errors = {}
        for field, upper in [('start_hour', 23), ('end_hour', 23), ('start_minutes', 55), ('end_minutes', 55)]:
            value = getattr(self, field)
            if value is not None and not 0 <= value <= upper:
                errors[field] = f'Must be between 0 and {upper}'
        for field in ('start_minutes', 'end_minutes', 'max_forward_minutes', 'max_backwards_minutes'):
            value = getattr(self, field)
            if value is not None and value % 5 != 0 and field not in errors:
                errors[field] = 'Must be a multiple of 5'
        if errors:
            raise ValidationError(errors)
    
    def __str__(self):
        return f"{self.name} - {self.get_start_day_display()} {self.start_hour:02d}:{self.start_minutes:02d} to {self.get_end_day_display()} {self.end_hour:02d}:{self.end_minutes:02d}"


class Simulation(models.Model):
    """Cost of one production plan (optionally compared with a second one) over a period."""
    name = models.CharField(max_length=255, unique=True)
    notes = models.TextField(blank=True)
    original_production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.CASCADE,
        related_name='simulations_original',
        verbose_name='current plan',
        help_text="The plan whose electricity cost is calculated",
        null=True,
    )
    optimized_production_plan = models.ForeignKey(
        WeeklyProductionPlan,
        on_delete=models.CASCADE,
        related_name='simulations_optimized',
        verbose_name='plan to compare',
        help_text="Optional: a second plan (usually an optimised one) to compare with the current plan",
        null=True,
        blank=True,
    )
    generation_dataset = models.ForeignKey(
        'DatasetApp.GenerationDataset',
        on_delete=models.PROTECT,
        related_name='simulations',
        verbose_name='on-site generation',
        help_text="Solar and cogeneration data to use",
        null=True,
    )
    prices_dataset = models.ForeignKey(
        'DatasetApp.PricesDataset',
        on_delete=models.PROTECT,
        related_name='simulations',
        verbose_name='electricity prices',
        help_text="Grid electricity prices to use",
        null=True,
    )
    start_date = models.DateField(help_text="First day of the period")
    end_date = models.DateField(help_text="Last day of the period (included)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'cost simulation'
    
    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': 'The last day must not be before the first day'})
        if self.original_production_plan_id and self.original_production_plan_id == self.optimized_production_plan_id:
            raise ValidationError({'optimized_production_plan': 'Choose a different plan from the current plan'})
    
    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"
