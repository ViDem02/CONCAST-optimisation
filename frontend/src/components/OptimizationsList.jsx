import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import '../styles/OptimizationsList.css';

function OptimizationsList() {
  const [optimizations, setOptimizations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchOptimizations();
  }, []);

  const fetchOptimizations = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/api/optimizer/optimizations/');
      // Handle both paginated and non-paginated responses
      const data = response.data.results || response.data;
      setOptimizations(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err) {
      setError('Failed to load optimizations: ' + err.message);
      console.error('Error fetching optimizations:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleOptimizationClick = (optimizationId) => {
    navigate(`/optimization-results/${optimizationId}`);
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const formatDateTime = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return <div className="optimizations-loading">Loading optimizations...</div>;
  }

  if (error) {
    return <div className="optimizations-error">{error}</div>;
  }

  return (
    <div className="optimizations-list">
      <div className="list-header">
        <h2>Production Plan Optimizations</h2>
        <p className="subtitle">View optimization results and cost savings</p>
      </div>

      {optimizations.length === 0 ? (
        <div className="no-optimizations">
          <p>No optimizations found.</p>
        </div>
      ) : (
        <div className="optimizations-grid">
          {optimizations.map((optimization) => (
            <div
              key={optimization.id}
              className="optimization-card"
              onClick={() => handleOptimizationClick(optimization.id)}
            >
              <div className="card-header">
                <h3>{optimization.name}</h3>
                {optimization.is_completed ? (
                  <span className="status-badge completed">Completed</span>
                ) : (
                  <span className="status-badge pending">Pending</span>
                )}
              </div>

              <div className="card-content">
                <div className="info-row">
                  <span className="label">Reference Plan:</span>
                  <span className="value">{optimization.reference_production_plan_name}</span>
                </div>

                {optimization.optimized_production_plan_name && (
                  <div className="info-row">
                    <span className="label">Optimized Plan:</span>
                    <span className="value">{optimization.optimized_production_plan_name}</span>
                  </div>
                )}

                <div className="info-row">
                  <span className="label">Reference Week:</span>
                  <span className="value">
                    {formatDate(optimization.reference_week_start)} - {formatDate(optimization.reference_week_end)}
                  </span>
                </div>

                {optimization.is_completed && (
                  <>
                    <div className="divider"></div>
                    
                    <div className="cost-summary">
                      <div className="cost-row">
                        <span className="label">Initial Cost:</span>
                        <span className="value">€{optimization.initial_cost_euros?.toFixed(2) || 'N/A'}</span>
                      </div>
                      <div className="cost-row">
                        <span className="label">Optimized Cost:</span>
                        <span className="value optimized">€{optimization.optimized_cost_euros?.toFixed(2) || 'N/A'}</span>
                      </div>
                      <div className="cost-row savings">
                        <span className="label">Savings:</span>
                        <span className="value">
                          €{optimization.cost_savings_euros?.toFixed(2) || 'N/A'} 
                          ({optimization.cost_savings_percent?.toFixed(2) || 'N/A'}%)
                        </span>
                      </div>
                    </div>
                  </>
                )}
              </div>

              <div className="card-footer">
                <span className="timestamp">
                  {optimization.is_completed 
                    ? `Completed: ${formatDateTime(optimization.completed_at)}`
                    : `Created: ${formatDateTime(optimization.created_at)}`
                  }
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default OptimizationsList;
