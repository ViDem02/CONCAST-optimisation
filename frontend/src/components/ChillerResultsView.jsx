import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { chillerApi } from '../services/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, AreaChart } from 'recharts';
import '../styles/ResultsView.css';

function ChillerResultsView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [simulation, setSimulation] = useState(null);
  const [allSimulations, setAllSimulations] = useState([]);
  const [selectedSimulationId, setSelectedSimulationId] = useState(id || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exportingCsv, setExportingCsv] = useState(false);

  useEffect(() => {
    if (selectedSimulationId) {
      fetchSimulation(selectedSimulationId);
    } else {
      fetchAllSimulations();
    }
  }, [selectedSimulationId]);

  const fetchAllSimulations = async () => {
    try {
      setLoading(true);
      const response = await chillerApi.listSimulations();
      const sims = response.data.results || response.data;
      // Filter to only show simulations with results
      const withResults = sims.filter(s => s.has_results);
      setAllSimulations(withResults);
      
      if (withResults.length > 0 && !selectedSimulationId) {
        setSelectedSimulationId(withResults[0].id);
      }
      
      setError(null);
    } catch (err) {
      setError('Failed to load chiller simulations: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSimulation = async (simId) => {
    try {
      setLoading(true);
      const response = await chillerApi.getSimulation(simId);
      setSimulation(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load simulation details: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSimulationChange = (e) => {
    const newId = e.target.value;
    setSelectedSimulationId(newId);
    navigate(`/chiller-results/${newId}`);
  };

  const handleExportCsv = async () => {
    if (!simulation) return;

    try {
      setExportingCsv(true);
      const response = await chillerApi.exportCsv(simulation.id);
      
      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `chiller_simulation_${simulation.id}_${simulation.name}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert('Failed to export CSV: ' + err.message);
    } finally {
      setExportingCsv(false);
    }
  };

  const formatNumber = (num, decimals = 2) => {
    if (num === null || num === undefined) return 'N/A';
    return Number(num).toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  };

  const prepareChartData = () => {
    if (!simulation || !simulation.calculated_temperature || !simulation.chiller_power_delivery) {
      return [];
    }

    const tempData = simulation.calculated_temperature;
    const powerData = simulation.chiller_power_delivery;

    return tempData.timestamps.map((timestamp, index) => ({
      timestamp: new Date(timestamp).toLocaleString('en-GB', { 
        month: 'short', 
        day: 'numeric', 
        hour: '2-digit', 
        minute: '2-digit' 
      }),
      temperature: tempData.temperature_C[index],
      outside_temperature: tempData.outside_temperature_C ? tempData.outside_temperature_C[index] : null,
      power_delivery: powerData.power_kW[index],
      grid_consumption: powerData.grid_consumption_kW[index],
      wasted_energy: powerData.wasted_energy_kW[index],
      generated_energy_used: powerData.power_kW[index] - powerData.grid_consumption_kW[index],
      min_temp: simulation.min_temperature,
      max_temp: simulation.max_temperature,
      target_temp: tempData.target_temp
    }));
  };

  if (loading) {
    return <div className="loading">Loading chiller simulation...</div>;
  }

  if (error) {
    return (
      <div className="error-container">
        <p className="error">{error}</p>
        <button onClick={selectedSimulationId ? () => fetchSimulation(selectedSimulationId) : fetchAllSimulations}>
          Retry
        </button>
      </div>
    );
  }

  if (!simulation && allSimulations.length === 0) {
    return (
      <div className="empty-state">
        <h3>No Chiller Simulation Results Available</h3>
        <p>No chiller simulation results have been calculated yet.</p>
        <p>Run chiller simulations using the Django admin or management commands to see results here.</p>
      </div>
    );
  }

  const chartData = prepareChartData();

  return (
    <div className="results-view">
      <div className="results-header">
        <div>
          <h2>Chiller Simulation Results</h2>
        </div>
        <div className="header-actions">
          {allSimulations.length > 0 && (
            <select
              value={selectedSimulationId || ''}
              onChange={handleSimulationChange}
              className="result-selector"
            >
              {allSimulations.map((sim) => (
                <option key={sim.id} value={sim.id}>
                  {sim.name} ({sim.start_date} to {sim.end_date})
                </option>
              ))}
            </select>
          )}
          <button
            onClick={handleExportCsv}
            disabled={exportingCsv || !simulation}
            className="btn btn-secondary"
          >
            {exportingCsv ? 'Exporting...' : 'Export to CSV'}
          </button>
        </div>
      </div>

      {simulation && (
        <>
          <div className="results-summary">
            <h3>Summary</h3>
            <div className="summary-grid">
              <div className="summary-card">
                <div className="card-icon">🌡️</div>
                <div className="card-content">
                  <div className="card-label">Temperature Range</div>
                  <div className="card-value">
                    {simulation.min_temperature}°C - {simulation.max_temperature}°C
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">📊</div>
                <div className="card-content">
                  <div className="card-label">Actual Temperature</div>
                  <div className="card-value">
                    {formatNumber(simulation.calculated_temperature.min_temp)}°C - {formatNumber(simulation.calculated_temperature.max_temp)}°C
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">🎯</div>
                <div className="card-content">
                  <div className="card-label">Average Temperature</div>
                  <div className="card-value">
                    {formatNumber(simulation.calculated_temperature.avg_temp)}°C
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">❄️</div>
                <div className="card-content">
                  <div className="card-label">Total Cooling Energy</div>
                  <div className="card-value">
                    {formatNumber(simulation.chiller_power_delivery.total_cooling_kWh)} kWh
                  </div>
                </div>
              </div>

              <div className="summary-card highlight">
                <div className="card-icon">🔌</div>
                <div className="card-content">
                  <div className="card-label">Grid Consumption</div>
                  <div className="card-value">
                    {formatNumber(simulation.chiller_power_delivery.total_grid_consumption_kWh)} kWh
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">♻️</div>
                <div className="card-content">
                  <div className="card-label">Wasted Energy</div>
                  <div className="card-value">
                    {formatNumber(simulation.chiller_power_delivery.total_wasted_kWh)} kWh
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">🏢</div>
                <div className="card-content">
                  <div className="card-label">Chiller</div>
                  <div className="card-value">
                    {simulation.chiller_name}
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">📅</div>
                <div className="card-content">
                  <div className="card-label">Simulation Period</div>
                  <div className="card-value">
                    {simulation.start_date} to {simulation.end_date}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="results-metadata">
            <div className="metadata-item">
              <span className="label">PD Controller:</span>
              <span className="value">Kp={simulation.proportional_gain}, Kd={simulation.derivative_gain}</span>
            </div>
            <div className="metadata-item">
              <span className="label">Initial Window:</span>
              <span className="value">{simulation.initial_window_hours} hours</span>
            </div>
            <div className="metadata-item">
              <span className="label">Minimum Runtime:</span>
              <span className="value">{simulation.minimum_runtime_minutes || 0} minutes</span>
            </div>
            <div className="metadata-item">
              <span className="label">Insulation:</span>
              <span className="value">U={simulation.chiller_details.insulation_u_value} W/m²K, A={simulation.chiller_details.surface_area} m²</span>
            </div>
            <div className="metadata-item">
              <span className="label">Chiller Efficiency:</span>
              <span className="value">{simulation.chiller_details.chiller_efficiency || 1.0}</span>
            </div>
            <div className="metadata-item">
              <span className="label">Grid Power Allowed:</span>
              <span className="value">{simulation.allow_grid_power ? 'Yes' : 'No'}</span>
            </div>
            {simulation.target_temperature !== null && simulation.target_temperature !== undefined && (
              <div className="metadata-item">
                <span className="label">Target Temperature:</span>
                <span className="value">{simulation.target_temperature}°C (manual)</span>
              </div>
            )}
            {simulation.production_plan_name && (
              <div className="metadata-item">
                <span className="label">Energy Source:</span>
                <span className="value">Wasted energy from production plan "{simulation.production_plan_name}"</span>
              </div>
            )}
          </div>

          {chartData.length > 0 && (
            <>
              {/* Temperature Chart */}
              <div className="results-summary">
                <h3>Temperature Control Over Time</h3>
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="timestamp" 
                      angle={-45}
                      textAnchor="end"
                      height={100}
                      interval={Math.floor(chartData.length / 20)}
                    />
                    <YAxis label={{ value: 'Temperature (°C)', angle: -90, position: 'insideLeft' }} />
                    <Tooltip 
                      formatter={(value, name) => {
                        if (name === 'Chiller Temperature') return [`${Number(value).toFixed(2)}°C`, name];
                        if (name === 'Max Allowed') return [`${Number(value).toFixed(0)}°C`, name];
                        if (name === 'Min Allowed') return [`${Number(value).toFixed(0)}°C`, name];
                        if (name === 'Target') return [`${Number(value).toFixed(2)}°C`, name];
                        return [value, name];
                      }}
                    />
                    <Legend />
                    <Line 
                      type="monotone" 
                      dataKey="max_temp" 
                      stroke="#e74c3c" 
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      name="Max Allowed"
                      dot={false}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="min_temp" 
                      stroke="#e74c3c" 
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      name="Min Allowed"
                      dot={false}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="target_temp" 
                      stroke="#27ae60" 
                      strokeWidth={2}
                      strokeDasharray="3 3"
                      name="Target"
                      dot={false}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="temperature" 
                      stroke="#3498db" 
                      strokeWidth={3}
                      name="Chiller Temperature"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Outside Temperature Chart */}
              {chartData[0]?.outside_temperature !== null && (
                <div className="results-summary">
                  <h3>Temperature Comparison (Inside vs Outside)</h3>
                  <ResponsiveContainer width="100%" height={400}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="timestamp" 
                        angle={-45}
                        textAnchor="end"
                        height={100}
                        interval={Math.floor(chartData.length / 20)}
                      />
                      <YAxis label={{ value: 'Temperature (°C)', angle: -90, position: 'insideLeft' }} />
                      <Tooltip 
                        formatter={(value, name) => [`${Number(value).toFixed(2)}°C`, name]}
                      />
                      <Legend />
                      <Line 
                        type="monotone" 
                        dataKey="outside_temperature" 
                        stroke="#e67e22" 
                        strokeWidth={2}
                        name="Outside Temperature"
                        dot={false}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="temperature" 
                        stroke="#3498db" 
                        strokeWidth={2}
                        name="Chiller Temperature"
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Combined Power and Energy Sources Chart */}
              <div className="results-summary">
                <h3>Cooling Power Sources and Delivery</h3>
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="timestamp" 
                      angle={-45}
                      textAnchor="end"
                      height={100}
                      interval={Math.floor(chartData.length / 20)}
                    />
                    <YAxis label={{ value: 'Power (kW)', angle: -90, position: 'insideLeft' }} />
                    <Tooltip 
                      formatter={(value, name) => [`${Number(value).toFixed(2)} kW`, name]}
                    />
                    <Legend />
                    <Area 
                      type="monotone" 
                      dataKey="generated_energy_used" 
                      stackId="1"
                      stroke="#27ae60" 
                      fill="#27ae60"
                      fillOpacity={0.7}
                      strokeOpacity={0.0}
                      name="Generated Energy Used"
                    />
                    <Area 
                      type="monotone" 
                      dataKey="grid_consumption" 
                      stackId="1"
                      stroke="#e74c3c" 
                      fill="#e74c3c"
                      fillOpacity={0.8}
                      strokeOpacity={0.0}
                      name="Grid Consumption"
                    />
                    {/*<Line 
                      type="monotone" 
                      dataKey="power_delivery" 
                      stroke="#9b59b6" 
                      strokeWidth={3}
                      name="Total Cooling Power"
                      dot={false}
                    />*/}
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default ChillerResultsView;
