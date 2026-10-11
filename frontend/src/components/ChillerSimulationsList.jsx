import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { chillerApi } from '../services/api';
import '../styles/SimulationsList.css';

function ChillerSimulationsList() {
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
      const response = await chillerApi.listSimulations();
      // API returns paginated response with 'results' array
      setSimulations(response.data.results || response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load chiller simulations: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSimulationClick = (id) => {
    navigate(`/chiller-results/${id}`);
  };

  if (loading) {
    return <div className="loading">Loading chiller simulations...</div>;
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
        <h3>No Chiller Simulations Available</h3>
        <p>No chiller simulation results have been calculated yet.</p>
        <p>Run chiller simulations using the Django admin or management commands to see results here.</p>
      </div>
    );
  }

  return (
    <div className="simulations-list">
      <h2>Chiller Simulation Results</h2>
      <p className="subtitle">Select a simulation to view temperature control and power consumption</p>
      
      <div className="simulations-grid">
        {simulations.map((simulation) => (
          <button
            key={simulation.id}
            className="simulation-card"
            onClick={() => handleSimulationClick(simulation.id)}
          >
            <div className="card-header">
              <h3>{simulation.name}</h3>
              <span className="simulation-id">ID: {simulation.id}</span>
            </div>
            <div className="card-body">
              <div className="info-row">
                <span className="label">Chiller:</span>
                <span className="value">{simulation.chiller_name}</span>
              </div>
              <div className="info-row">
                <span className="label">Period:</span>
                <span className="value">{simulation.start_date} to {simulation.end_date}</span>
              </div>
              <div className="info-row">
                <span className="label">Temperature Range:</span>
                <span className="value">{simulation.min_temperature}°C - {simulation.max_temperature}°C</span>
              </div>
              <div className="info-row">
                <span className="label">Status:</span>
                <span className={`value ${simulation.has_results ? 'highlight' : ''}`}>
                  {simulation.has_results ? '✓ Has Results' : '✗ No Results'}
                </span>
              </div>
            </div>
            <div className="card-footer">
              <span className="view-link">
                {simulation.has_results ? 'View Details →' : 'Run Simulation First'}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default ChillerSimulationsList;
