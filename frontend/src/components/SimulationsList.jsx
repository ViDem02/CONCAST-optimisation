import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { resultsApi } from '../services/api';
import '../styles/SimulationsList.css';

function SimulationsList() {
  const navigate = useNavigate();
  const [simulations, setSimulations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSimulations();
  }, []);

  const fetchSimulations = async () => {
    try {
      setLoading(true);
      const response = await resultsApi.listResults();
      // API returns paginated response with 'results' array
      setSimulations(response.data.results || response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load simulations: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSimulationClick = (id) => {
    navigate(`/results/${id}`);
  };

  if (loading) {
    return <div className="loading">Loading simulations...</div>;
  }

  if (error) {
    return (
      <div className="error-container">
        <p className="error">{error}</p>
        <button onClick={fetchSimulations}>Retry</button>
      </div>
    );
  }

  if (simulations.length === 0) {
    return (
      <div className="empty-state">
        <h3>No Simulations Available</h3>
        <p>No simulation results have been calculated yet.</p>
        <p>Run simulations using the Django admin or management commands to see results here.</p>
      </div>
    );
  }

  return (
    <div className="simulations-list">
      <h2>Simulation Results</h2>
      <p className="subtitle">Select a simulation to view detailed results and charts</p>
      
      <div className="simulations-grid">
        {simulations.map((simulation) => (
          <button
            key={simulation.id}
            className="simulation-card"
            onClick={() => handleSimulationClick(simulation.id)}
          >
            <div className="card-header">
              <h3>{simulation.simulation_name}</h3>
              <span className="simulation-id">ID: {simulation.id}</span>
            </div>
            <div className="card-body">
              <div className="info-row">
                <span className="label">Calculated:</span>
                <span className="value">{new Date(simulation.calculated_at).toLocaleString()}</span>
              </div>
              <div className="info-row">
                <span className="label">Total Cost:</span>
                <span className="value highlight">€{Number(simulation.total_cost_euros).toFixed(2)}</span>
              </div>
              <div className="info-row">
                <span className="label">Total Electricity:</span>
                <span className="value">{Number(simulation.total_electricity_used_kWh).toFixed(2)} kWh</span>
              </div>
            </div>
            <div className="card-footer">
              <span className="view-link">View Details →</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default SimulationsList;
