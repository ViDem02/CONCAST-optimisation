import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import ShiftsGantt from './ShiftsGantt';
import '../styles/OptimizationResultsView.css';

function OptimizationResultsView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [optimization, setOptimization] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchOptimization();
  }, [id]);

  const fetchOptimization = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/optimizer/optimizations/${id}/`);
      setOptimization(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load optimization: ' + err.message);
    } finally {
      setLoading(false);
    }
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
    return <div className="results-loading">Loading optimization results...</div>;
  }

  if (error) {
    return (
      <div className="results-error">
        <p>{error}</p>
        <button onClick={() => navigate('/optimizations')}>Back to List</button>
      </div>
    );
  }

  if (!optimization) {
    return null;
  }

  const optimizationData = optimization.optimization_data || {};
  const shiftChanges = optimizationData.shift_changes || [];

  // Prepare data for shift changes chart
  const chartData = shiftChanges.map(change => ({
    name: change.phase_name || `${change.process_name} Run ${change.run_number}`,
    shift_minutes: change.shift_minutes,
    process: change.process_name
  }));

  return (
    <div className="optimization-results-view">
      <div className="results-header">
        <button className="back-button" onClick={() => navigate('/optimizations')}>
          ← Back to Optimizations
        </button>
        <h2>{optimization.name}</h2>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card">
          <div className="card-label">Reference Week</div>
          <div className="card-value">
            {formatDate(optimization.reference_week_start)} - {formatDate(optimization.reference_week_end)}
          </div>
        </div>

        <div className="summary-card">
          <div className="card-label">Initial Cost</div>
          <div className="card-value">€{optimization.initial_cost_euros?.toFixed(2) || 'N/A'}</div>
        </div>

        <div className="summary-card">
          <div className="card-label">Optimized Cost</div>
          <div className="card-value optimized">€{optimization.optimized_cost_euros?.toFixed(2) || 'N/A'}</div>
        </div>

        <div className="summary-card highlight">
          <div className="card-label">Cost Savings</div>
          <div className="card-value savings">
            €{optimization.cost_savings_euros?.toFixed(2) || 'N/A'}
            <span className="percentage">({optimization.cost_savings_percent?.toFixed(2) || 'N/A'}%)</span>
          </div>
        </div>
      </div>

      {/* Optimization Details */}
      {optimization.is_completed && optimizationData && (
        <div className="optimization-details">
          <h3>Optimization Details</h3>
          
          <div className="details-grid">
            <div className="detail-item">
              <span className="detail-label">Algorithm Iterations (LSQR):</span>
              <span className="detail-value">{optimizationData.lsqr_iterations || 'N/A'}</span>
            </div>
            
            <div className="detail-item">
              <span className="detail-label">Coordinate Descent Iterations:</span>
              <span className="detail-value">{optimizationData.coordinate_descent_iterations || 'N/A'}</span>
            </div>
            
            <div className="detail-item">
              <span className="detail-label">Number of Timesteps:</span>
              <span className="detail-value">{optimizationData.num_timesteps || 'N/A'}</span>
            </div>
            
            <div className="detail-item">
              <span className="detail-label">Runs Optimized:</span>
              <span className="detail-value">{optimizationData.num_runs_optimized || 'N/A'}</span>
            </div>
            
            <div className="detail-item">
              <span className="detail-label">Initial Cost After LSQR:</span>
              <span className="detail-value">€{optimizationData.initial_cost_after_lsqr?.toFixed(2) || 'N/A'}</span>
            </div>
            
            <div className="detail-item">
              <span className="detail-label">Total Wasted Energy:</span>
              <span className="detail-value">{optimizationData.total_wasted_energy?.toFixed(2) || 'N/A'} kWh</span>
            </div>
          </div>

          {/* Cost Breakdown Chart */}
          <div className="cost-breakdown-section">
            <h4>Cost Comparison</h4>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={[
                  { name: 'Baseline', cost: optimizationData.baseline_cost },
                  { name: 'After LSQR', cost: optimizationData.initial_cost_after_lsqr },
                  { name: 'Final', cost: optimizationData.final_cost }
                ]}
                margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis label={{ value: 'Cost (€)', angle: -90, position: 'insideLeft' }} />
                <Tooltip formatter={(value) => `€${value?.toFixed(2)}`} />
                <Bar dataKey="cost" fill="#3498db" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Shift Changes */}
          {shiftChanges.length > 0 && (
            <div className="shift-changes-section">
              <h4>Shift Changes ({shiftChanges.length} shifts optimized)</h4>
              
              {/* Shift Changes Chart */}
              <div className="chart-container">
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart
                    data={chartData}
                    margin={{ top: 20, right: 30, left: 20, bottom: 100 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="name" 
                      angle={-45} 
                      textAnchor="end" 
                      height={120}
                      interval={0}
                    />
                    <YAxis label={{ value: 'Shift (minutes)', angle: -90, position: 'insideLeft' }} />
                    <Tooltip 
                      formatter={(value) => `${value} minutes (${(value/60).toFixed(2)} hours)`}
                    />
                    <Legend />
                    <Bar 
                      dataKey="shift_minutes" 
                      fill="#2ecc71" 
                      name="Time Shift"
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Shift Changes Table */}
              <div className="shift-changes-table">
                <table>
                  <thead>
                    <tr>
                      <th>Phase/Run</th>
                      <th>Process</th>
                      <th>Shift (minutes)</th>
                      <th>Shift (hours)</th>
                      <th>Direction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shiftChanges.map((change, index) => (
                      <tr key={index}>
                        <td>{change.phase_name || `Run ${change.run_number}`}</td>
                        <td>{change.process_name}</td>
                        <td className={change.shift_minutes > 0 ? 'positive' : change.shift_minutes < 0 ? 'negative' : ''}>
                          {change.shift_minutes}
                        </td>
                        <td>{(change.shift_minutes / 60).toFixed(2)}</td>
                        <td>
                          {change.shift_minutes > 0 ? (
                            <span className="direction forward">→ Forward</span>
                          ) : change.shift_minutes < 0 ? (
                            <span className="direction backward">← Backward</span>
                          ) : (
                            <span className="direction none">− No change</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Production Plans Comparison */}
      {optimization.optimized_production_plan && (
        <div className="production-plans-section">
          <h3>Production Plans Comparison</h3>
          
          <div className="plans-comparison">
            <div className="plan-gantt">
              <h4>Reference Plan: {optimization.reference_production_plan_name}</h4>
              <ShiftsGantt productionPlanId={optimization.reference_production_plan} />
            </div>
            
            <div className="plan-gantt">
              <h4>Optimized Plan: {optimization.optimized_production_plan_name}</h4>
              <ShiftsGantt productionPlanId={optimization.optimized_production_plan} />
            </div>
          </div>
        </div>
      )}

      {/* Notes */}
      {optimization.notes && (
        <div className="notes-section">
          <h4>Notes</h4>
          <p>{optimization.notes}</p>
        </div>
      )}

      {/* Metadata */}
      <div className="metadata-section">
        <div className="metadata-item">
          <span className="metadata-label">Created:</span>
          <span className="metadata-value">{formatDateTime(optimization.created_at)}</span>
        </div>
        {optimization.completed_at && (
          <div className="metadata-item">
            <span className="metadata-label">Completed:</span>
            <span className="metadata-value">{formatDateTime(optimization.completed_at)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default OptimizationResultsView;
