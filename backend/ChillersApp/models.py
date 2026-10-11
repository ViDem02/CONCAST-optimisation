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
    
    def __str__(self):
        return f"{self.name} (U={self.insulation_u_value}, A={self.surface_area}m²)"


class ChillerSimulation(models.Model):
    """Chiller simulation configuration and results."""
    
    name = models.CharField(max_length=255, unique=True)
    chiller = models.ForeignKey(
        Chiller,
        on_delete=models.CASCADE,
        related_name='simulations'
    )
    max_temperature = models.IntegerField(
        help_text="Maximum temperature to maintain (°C)",
        validators=[MinValueValidator(-50)]
    )
    min_temperature = models.IntegerField(
        help_text="Minimum temperature to maintain (°C)",
        validators=[MinValueValidator(-50)]
    )
    target_temperature = models.FloatField(
        null=True,
        blank=True,
        help_text="Target temperature (°C). If not set, defaults to midpoint of min/max range.",
        validators=[MinValueValidator(-50)]
    )
    start_date = models.DateField(help_text="Simulation start date")
    end_date = models.DateField(help_text="Simulation end date")
    initial_window_hours = models.IntegerField(
        help_text="Initial window of time in hours",
        validators=[MinValueValidator(0)],
        default=0
    )
    
    # PD Controller parameters
    proportional_gain = models.FloatField(
        help_text="Proportional gain (Kp) for PD controller",
        validators=[MinValueValidator(0)],
        default=2.0
    )
    derivative_gain = models.FloatField(
        help_text="Derivative gain (Kd) for PD controller",
        validators=[MinValueValidator(0)],
        default=0.5
    )
    
    # Grid power options
    allow_grid_power = models.BooleanField(
        default=True,
        help_text="Allow using grid electricity. If False, chiller will only use available renewable generation."
    )
    
    # Minimum runtime constraint
    minimum_runtime_minutes = models.IntegerField(
        default=0,
        help_text="Minimum runtime in minutes when chiller is turned on. Prevents rapid on/off cycling. 0 = no constraint.",
        validators=[MinValueValidator(0)]
    )
    
    # Optional production plan link
    production_plan_result = models.ForeignKey(
        SimulationResults,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chiller_simulations',
        help_text="Optional: Link to production plan. If set, available generation = wasted energy from production plan"
    )
    
    # Dataset selection (used when production_plan_result is not set)
    generation_dataset = models.ForeignKey(
        'DatasetApp.GenerationDataset',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Generation dataset to use for simulation (if not using production plan result)"
    )
    
    prices_dataset = models.ForeignKey(
        'DatasetApp.PricesDataset',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Prices dataset to use for simulation"
    )
    
    temperature_dataset = models.ForeignKey(
        'DatasetApp.TemperatureDataset',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Temperature dataset to use for simulation"
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
    
    def __str__(self):
        return f"{self.name} - {self.chiller.name} ({self.start_date} to {self.end_date})"
