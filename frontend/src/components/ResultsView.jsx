import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { resultsApi, simulationApi } from '../services/api';
import ResultsCharts from './ResultsCharts';
import ShiftsGantt from './ShiftsGantt';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import '../styles/ResultsView.css';

function ResultsView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [results, setResults] = useState(null);
  const [simulation, setSimulation] = useState(null);
  const [allResults, setAllResults] = useState([]);
  const [selectedResultId, setSelectedResultId] = useState(id || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exportingCsv, setExportingCsv] = useState(false);

  useEffect(() => {
    if (selectedResultId) {
      fetchResult(selectedResultId);
    } else {
      fetchAllResults();
    }
  }, [selectedResultId]);

  const fetchAllResults = async () => {
    try {
      setLoading(true);
      const response = await resultsApi.listResults();
      setAllResults(response.data);
      
      if (response.data.length > 0 && !selectedResultId) {
        setSelectedResultId(response.data[0].id);
      }
      
      setError(null);
    } catch (err) {
      setError('Failed to load results: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchResult = async (resultId) => {
    try {
      setLoading(true);
      const response = await resultsApi.getResultWithTimesteps(resultId);
      setResults(response.data);
      
      // Fetch simulation details to get production plan reference
      if (response.data.simulation) {
        const simResponse = await simulationApi.getSimulation(response.data.simulation);
        setSimulation(simResponse.data);
      }
      
      setError(null);
    } catch (err) {
      setError('Failed to load result details: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleResultChange = (e) => {
    const newId = e.target.value;
    setSelectedResultId(newId);
    navigate(`/results/${newId}`);
  };

  const handleExportCsv = async () => {
    if (!results) return;

    try {
      setExportingCsv(true);
      const response = await resultsApi.exportCsv(results.id);
      
      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `simulation_results_${results.id}.csv`);
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

  if (loading) {
    return <div className="loading">Loading results...</div>;
  }

  if (error) {
    return (
      <div className="error-container">
        <p className="error">{error}</p>
        <button onClick={selectedResultId ? () => fetchResult(selectedResultId) : fetchAllResults}>
          Retry
        </button>
      </div>
    );
  }

  if (!results && allResults.length === 0) {
    return (
      <div className="empty-state">
        <h3>No Results Available</h3>
        <p>No simulation results have been calculated yet.</p>
        <p>Run simulations using the Django admin or management commands to see results here.</p>
      </div>
    );
  }

  return (
    <div className="results-view">
      <div className="results-header">
        <div>
          <h2>Simulation Results</h2>
        </div>
        <div className="header-actions">
          {allResults.length > 0 && (
            <select
              value={selectedResultId || ''}
              onChange={handleResultChange}
              className="result-selector"
            >
              {allResults.map((result) => (
                <option key={result.id} value={result.id}>
                  {result.simulation_name} - {new Date(result.calculated_at).toLocaleString()}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={handleExportCsv}
            disabled={exportingCsv || !results}
            className="btn btn-secondary"
          >
            {exportingCsv ? 'Exporting...' : 'Export to CSV'}
          </button>
        </div>
      </div>

      {results && (
        <>
          <div className="results-summary">
            <h3>Summary</h3>
            <div className="summary-grid">
              <div className="summary-card">
                <div className="card-icon">⚡</div>
                <div className="card-content">
                  <div className="card-label">Total Electricity Used</div>
                  <div className="card-value">
                    {formatNumber(results.total_electricity_used_kWh)} kWh
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">🔌</div>
                <div className="card-content">
                  <div className="card-label">Grid Electricity Purchased</div>
                  <div className="card-value">
                    {formatNumber(results.grid_electricity_purchased_kWh)} kWh
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">☀️</div>
                <div className="card-content">
                  <div className="card-label">Solar Generated</div>
                  <div className="card-value">
                    {formatNumber(results.solar_generated_kWh)} kWh
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">🏭</div>
                <div className="card-content">
                  <div className="card-label">Cogenerator Generated</div>
                  <div className="card-value">
                    {formatNumber(results.cogen_generated_kWh)} kWh
                  </div>
                </div>
              </div>

              <div className="summary-card highlight">
                <div className="card-icon">💰</div>
                <div className="card-content">
                  <div className="card-label">Total Cost</div>
                  <div className="card-value">
                    €{formatNumber(results.total_cost_euros)}
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">♻️</div>
                <div className="card-content">
                  <div className="card-label">Wasted Energy</div>
                  <div className="card-value">
                    {formatNumber(results.wasted_energy_kWh)} kWh
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">🌍</div>
                <div className="card-content">
                  <div className="card-label">CO₂ Emissions</div>
                  <div className="card-value">
                    {formatNumber(results.total_co2_kg)} kg
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <div className="card-icon">⏱️</div>
                <div className="card-content">
                  <div className="card-label">Timesteps</div>
                  <div className="card-value">
                    {formatNumber(results.num_timesteps, 0)} × {results.timestep_minutes} min
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="results-metadata">
            <div className="metadata-item">
              <span className="label">Simulation:</span>
              <span className="value">{results.simulation_name}</span>
            </div>
            <div className="metadata-item">
              <span className="label">Calculated at:</span>
              <span className="value">{new Date(results.calculated_at).toLocaleString()}</span>
            </div>
          </div>

          {results.timestep_data && results.timestep_data.timestamps && results.timestep_data.timestamps.length > 0 && (
            <>
              {/* Production Shifts Gantt Chart */}
              {simulation && simulation.reference_production_plan && (
                <ShiftsGantt productionPlanId={simulation.reference_production_plan} />
              )}

              {/* Electricity Prices Chart */}
              <div className="results-summary">
                <h3>Electricity Prices During Simulation</h3>
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={results.timestep_data.timestamps.map((timestamp, index) => ({
                    timestamp: new Date(timestamp).toLocaleString('en-GB', { 
                      month: 'short', 
                      day: 'numeric', 
                      hour: '2-digit', 
                      minute: '2-digit' 
                    }),
                    electricity_price: results.timestep_data.electricity_price[index]
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="timestamp" 
                      angle={-45}
                      textAnchor="end"
                      height={100}
                      interval={Math.floor(results.timestep_data.timestamps.length / 20)}
                    />
                    <YAxis label={{ value: 'Price (€/kWh)', angle: -90, position: 'insideLeft' }} />
                    <Tooltip 
                      formatter={(value) => [`€${Number(value).toFixed(4)}/kWh`, 'Electricity Price']}
                    />
                    <Legend />
                    <Line 
                      type="monotone" 
                      dataKey="electricity_price" 
                      stroke="#f39c12" 
                      strokeWidth={2}
                      name="Electricity Price"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              
              <ResultsCharts timestepData={results.timestep_data.timestamps.map((timestamp, index) => ({
                timestamp,
                total_demand_kWh: results.timestep_data.total_demand_kWh[index],
                solar_generation_kWh: results.timestep_data.solar_generation_kWh[index],
                cogen_generation_kWh: results.timestep_data.cogen_generation_kWh[index],
                total_generation_kWh: results.timestep_data.total_generation_kWh[index],
                grid_electricity_kWh: results.timestep_data.grid_electricity_kWh[index],
                wasted_energy_kWh: results.timestep_data.wasted_energy_kWh[index],
                electricity_price: results.timestep_data.electricity_price[index],
                grid_cost_euros: results.timestep_data.grid_cost_euros[index]
              }))} />
            </>
          )}
        </>
      )}
    </div>
  );
}

export default ResultsView;
