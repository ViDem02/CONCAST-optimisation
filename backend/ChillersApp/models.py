from django.db import models
from django.core.validators import MinValueValidator
from SimulationApp.models import SimulationResults


class Chiller(models.Model):
    """Chiller configuration for temperature control."""
    name = models.CharField(max_length=255, unique=True)
    insulation_u_value = models.FloatField(
        help_text="Insulation U-value (W/m²K)",
        validators=[MinValueValidator(0)]
    )
    surface_area = models.FloatField(
        help_text="Surface area in m²",
        validators=[MinValueValidator(0)]
    )
    nominal_capacity_kW = models.FloatField(
        help_text="Nominal cooling capacity in kW",
        validators=[MinValueValidator(0)],
        default=10.0
    )
    nominal_cooling_rate = models.FloatField(
        help_text="Nominal cooling rate in °C per hour at full capacity",
        validators=[MinValueValidator(0)],
        default=3.0
    )
    chiller_efficiency = models.FloatField(
        default=1.0,
        help_text="Chiller cooling efficiency (0.0 to 1.0). Lower values = less powerful chiller. Default 1.0 = full power.",
        validators=[MinValueValidator(0.0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'cold room'
    
    def __str__(self):
        return f"{self.name} (U={self.insulation_u_value}, A={self.surface_area}m²)"


class ChillerSimulation(models.Model):
    """Chiller simulation configuration and results."""
    
    name = models.CharField(max_length=255, unique=True)
    chiller = models.ForeignKey(
        Chiller,
        on_delete=models.CASCADE,
        related_name='simulations',
        verbose_name='cold room'
    )
    max_temperature = models.IntegerField(
        verbose_name='maximum temperature (°C)',
        help_text="The room must not get warmer than this",
        validators=[MinValueValidator(-50)]
    )
    min_temperature = models.IntegerField(
        verbose_name='minimum temperature (°C)',
        help_text="The room must not get colder than this",
        validators=[MinValueValidator(-50)]
    )
    target_temperature = models.FloatField(
        null=True,
        blank=True,
        verbose_name='target temperature (°C)',
        help_text="Temperature the controller aims for. Leave empty to use the middle of the allowed range",
        validators=[MinValueValidator(-50)]
    )
    start_date = models.DateField(help_text="First day of the simulation")
    end_date = models.DateField(help_text="Last day of the simulation (included)")
    initial_window_hours = models.IntegerField(
        verbose_name='start-up period (hours)',
        help_text="Hours at the start during which the temperature may still be outside the allowed range",
        validators=[MinValueValidator(0)],
        default=0
    )
    
    # PD Controller parameters
    proportional_gain = models.FloatField(
        help_text="Proportional gain (Kp) of the PD controller: higher reacts faster, but may overshoot",
        validators=[MinValueValidator(0)],
        default=2.0
    )
    derivative_gain = models.FloatField(
        help_text="Derivative gain (Kd) of the PD controller: higher damps oscillations",
        validators=[MinValueValidator(0)],
        default=0.5
    )
    
    # Grid power options
    allow_grid_power = models.BooleanField(
        default=True,
        verbose_name='allow buying from the grid',
        help_text="Untick to cool only with on-site generation (the temperature may then leave the allowed range)"
    )
    
    # Minimum runtime constraint
    minimum_runtime_minutes = models.IntegerField(
        default=0,
        verbose_name='minimum runtime (min)',
        help_text="Once started, the unit runs at least this long, to avoid frequent on/off cycles (0 = no minimum)",
        validators=[MinValueValidator(0)]
    )
    
    # Optional production plan link
    production_plan_result = models.ForeignKey(
        SimulationResults,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chiller_simulations',
        verbose_name='use surplus of cost simulation',
        help_text="Optional: if set, the cold room only uses the generation left unused by the production "
                  "in that cost simulation (same dates required) instead of the full generation"
    )
    
    # Dataset selection (used when production_plan_result is not set)
    generation_dataset = models.ForeignKey(
        'DatasetApp.GenerationDataset',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='on-site generation',
        help_text="Solar and cogeneration data (needed unless a cost simulation is linked)"
    )
    
    temperature_dataset = models.ForeignKey(
        'DatasetApp.TemperatureDataset',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='outside temperature',
        help_text="Outside temperature data"
    )
    
    # Results fields (populated after simulation)
    chiller_power_delivery = models.JSONField(
        null=True,
        blank=True,
        help_text="Time series of power delivery to the chiller (JSON array)"
    )
    calculated_temperature = models.JSONField(
        null=True,
        blank=True,
        help_text="Time series of calculated temperatures (JSON array)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'cold-room simulation'
    
    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        if self.min_temperature is not None and self.max_temperature is not None \
                and self.min_temperature >= self.max_temperature:
            errors['max_temperature'] = 'The maximum temperature must be above the minimum temperature'
        if self.start_date and self.end_date and self.start_date > self.end_date:
            errors['end_date'] = 'The last day must not be before the first day'
        if not self.production_plan_result_id and not self.generation_dataset_id:
            errors['generation_dataset'] = 'Choose the on-site generation data (or link a cost simulation below)'
        if errors:
            raise ValidationError(errors)
    
    def __str__(self):
        return f"{self.name} - {self.chiller.name} ({self.start_date} to {self.end_date})"
