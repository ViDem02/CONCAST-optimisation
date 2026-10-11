import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { simulationApi } from '../services/api';
import '../styles/SimulationList.css';

function SimulationList() {
  const [simulations, setSimulations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSimulations();
  }, []);

  const fetchSimulations = async () => {
    try {
      setLoading(true);
      const response = await simulationApi.listSimulations();
      setSimulations(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load simulations: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Are you sure you want to delete simulation "${name}"?`)) {
      return;
    }

    try {
      await simulationApi.deleteSimulation(id);
      setSimulations(simulations.filter(sim => sim.id !== id));
    } catch (err) {
      alert('Failed to delete simulation: ' + err.message);
    }
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

  return (
    <div className="simulation-list">
      <div className="list-header">
        <h2>Simulations</h2>
        <Link to="/create" className="btn btn-primary">
          Create New Simulation
        </Link>
      </div>

      {simulations.length === 0 ? (
        <div className="empty-state">
          <p>No simulations found.</p>
          <Link to="/create" className="btn btn-primary">
            Create your first simulation
          </Link>
        </div>
      ) : (
        <div className="simulations-grid">
          {simulations.map((simulation) => (
            <div key={simulation.id} className="simulation-card">
              <div className="card-header">
                <h3>{simulation.name}</h3>
                <div className="card-actions">
                  <Link
                    to={`/simulation/${simulation.id}`}
                    className="btn btn-small btn-primary"
                  >
                    View
                  </Link>
                  <button
                    onClick={() => handleDelete(simulation.id, simulation.name)}
                    className="btn btn-small btn-danger"
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="card-body">
                <div className="info-row">
                  <span className="label">Production Plan:</span>
                  <span className="value">
                    {simulation.reference_production_plan_name}
                  </span>
                </div>
                <div className="info-row">
                  <span className="label">Period:</span>
                  <span className="value">
                    {new Date(simulation.start_date).toLocaleDateString()} -{' '}
                    {new Date(simulation.end_date).toLocaleDateString()}
                  </span>
                </div>
                {simulation.notes && (
                  <div className="info-row">
                    <span className="label">Notes:</span>
                    <span className="value">{simulation.notes}</span>
                  </div>
                )}
                <div className="info-row">
                  <span className="label">Created:</span>
                  <span className="value">
                    {new Date(simulation.created_at).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default SimulationList;
