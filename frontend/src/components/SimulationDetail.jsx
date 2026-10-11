import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { simulationApi, processApi } from '../services/api';
import '../styles/SimulationDetail.css';

function SimulationDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [simulation, setSimulation] = useState(null);
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [runError, setRunError] = useState(null);

  useEffect(() => {
    fetchSimulation();
  }, [id]);

  const fetchSimulation = async () => {
    try {
      setLoading(true);
      const response = await simulationApi.getSimulation(id);
      setSimulation(response.data);
      
      // Fetch processes for the production plan
      if (response.data.reference_production_plan) {
        const processesResponse = await processApi.getProcessesByPlan(
          response.data.reference_production_plan
        );
        setProcesses(processesResponse.data);
      }
      
      setError(null);
    } catch (err) {
      setError('Failed to load simulation: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRunSimulation = async () => {
    if (!window.confirm('Run this simulation? This will calculate costs and usage based on the production plan and datasets.')) {
      return;
    }

    try {
      setRunning(true);
      setRunError(null);
      const response = await simulationApi.runSimulation(id);
      
      // Navigate to results page
      if (response.data && response.data.id) {
        alert('Simulation completed successfully!');
        navigate(`/results/${response.data.id}`);
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message;
      setRunError('Failed to run simulation: ' + errorMsg);
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading simulation...</div>;
  }

  if (error) {
    return (
      <div className="error-container">
        <p className="error">{error}</p>
        <button onClick={fetchSimulation}>Retry</button>
        <Link to="/" className="btn">Back to List</Link>
      </div>
    );
  }

  if (!simulation) {
    return <div className="error">Simulation not found</div>;
  }

  return (
    <div className="simulation-detail">
      <div className="detail-header">
        <div>
          <Link to="/" className="back-link">← Back to Simulations</Link>
          <h2>{simulation.name}</h2>
        </div>
        <button
          onClick={handleRunSimulation}
          disabled={running}
          className="btn btn-primary btn-large"
        >
          {running ? 'Running Simulation...' : 'Run Simulation'}
        </button>
      </div>

      {runError && (
        <div className="error-banner">
          {runError}
        </div>
      )}

      <div className="detail-content">
        <section className="detail-section">
          <h3>Simulation Information</h3>
          <div className="info-grid">
            <div className="info-item">
              <span className="label">Name:</span>
              <span className="value">{simulation.name}</span>
            </div>
            <div className="info-item">
              <span className="label">Production Plan:</span>
              <span className="value">{simulation.reference_production_plan_name}</span>
            </div>
            <div className="info-item">
              <span className="label">Start Date:</span>
              <span className="value">
                {new Date(simulation.start_date).toLocaleDateString()}
              </span>
            </div>
            <div className="info-item">
              <span className="label">End Date:</span>
              <span className="value">
                {new Date(simulation.end_date).toLocaleDateString()}
              </span>
            </div>
            {simulation.notes && (
              <div className="info-item full-width">
                <span className="label">Notes:</span>
                <span className="value">{simulation.notes}</span>
              </div>
            )}
          </div>
        </section>

        {processes.length > 0 && (
          <section className="detail-section">
            <h3>Production Processes</h3>
            <div className="processes-table">
              <table>
                <thead>
                  <tr>
                    <th>Process Name</th>
                    <th>Electricity Consumption (kWh)</th>
                    <th>Number of Shifts</th>
                  </tr>
                </thead>
                <tbody>
                  {processes.map((process) => (
                    <tr key={process.id}>
                      <td>{process.name}</td>
                      <td>{process.electricity_consumption_kWh}</td>
                      <td>{process.shifts?.length || 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <section className="detail-section">
          <h3>Simulation Details</h3>
          <div className="info-text">
            <p>
              This simulation will calculate electricity costs and usage for the period
              from {new Date(simulation.start_date).toLocaleDateString()} to{' '}
              {new Date(simulation.end_date).toLocaleDateString()}.
            </p>
            <p>
              The calculation uses 5-minute timesteps and considers:
            </p>
            <ul>
              <li>Electricity consumption from production processes</li>
              <li>Solar panel generation</li>
              <li>Cogenerator generation</li>
              <li>Hourly electricity and methane prices</li>
              <li>Grid electricity purchases</li>
              <li>Wasted energy</li>
              <li>CO₂ emissions (0.5 kg CO₂ per kWh from grid)</li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}

export default SimulationDetail;
