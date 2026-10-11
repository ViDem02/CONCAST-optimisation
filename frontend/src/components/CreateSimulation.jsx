import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { simulationApi, productionPlanApi } from '../services/api';
import '../styles/CreateSimulation.css';

function CreateSimulation() {
  const navigate = useNavigate();
  const [productionPlans, setProductionPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  
  const [formData, setFormData] = useState({
    name: '',
    notes: '',
    reference_production_plan: '',
    start_date: '',
    end_date: '',
  });

  useEffect(() => {
    fetchProductionPlans();
  }, []);

  const fetchProductionPlans = async () => {
    try {
      setLoading(true);
      const response = await productionPlanApi.listPlans();
      setProductionPlans(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load production plans: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validation
    if (!formData.name.trim()) {
      alert('Please enter a simulation name');
      return;
    }
    if (!formData.reference_production_plan) {
      alert('Please select a production plan');
      return;
    }
    if (!formData.start_date || !formData.end_date) {
      alert('Please select start and end dates');
      return;
    }
    if (new Date(formData.start_date) >= new Date(formData.end_date)) {
      alert('End date must be after start date');
      return;
    }

    try {
      setSubmitting(true);
      const response = await simulationApi.createSimulation(formData);
      alert('Simulation created successfully!');
      navigate(`/simulation/${response.data.id}`);
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message;
      alert('Failed to create simulation: ' + errorMsg);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  return (
    <div className="create-simulation">
      <h2>Create New Simulation</h2>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={fetchProductionPlans}>Retry</button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="simulation-form">
        <div className="form-group">
          <label htmlFor="name">Simulation Name *</label>
          <input
            type="text"
            id="name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            placeholder="e.g., Winter 2025 Analysis"
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="reference_production_plan">Production Plan *</label>
          <select
            id="reference_production_plan"
            name="reference_production_plan"
            value={formData.reference_production_plan}
            onChange={handleChange}
            required
          >
            <option value="">-- Select a production plan --</option>
            {productionPlans.map((plan) => (
              <option key={plan.id} value={plan.id}>
                {plan.name} {plan.is_optimized ? '(Optimized)' : ''}
              </option>
            ))}
          </select>
          {productionPlans.length === 0 && (
            <p className="help-text">
              No production plans available. Please create a production plan first.
            </p>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="start_date">Start Date *</label>
            <input
              type="date"
              id="start_date"
              name="start_date"
              value={formData.start_date}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="end_date">End Date *</label>
            <input
              type="date"
              id="end_date"
              name="end_date"
              value={formData.end_date}
              onChange={handleChange}
              required
            />
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="notes">Notes (Optional)</label>
          <textarea
            id="notes"
            name="notes"
            value={formData.notes}
            onChange={handleChange}
            placeholder="Add any notes or description for this simulation..."
            rows="4"
          />
        </div>

        <div className="form-info">
          <h4>What happens during simulation?</h4>
          <p>
            The simulation will calculate electricity costs and usage using 5-minute timesteps,
            considering:
          </p>
          <ul>
            <li>Production process electricity consumption</li>
            <li>Solar panel and cogenerator generation</li>
            <li>Hourly electricity and methane prices</li>
            <li>Grid electricity purchases and costs</li>
            <li>Wasted energy calculation</li>
            <li>CO₂ emissions from grid electricity</li>
          </ul>
        </div>

        <div className="form-actions">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="btn btn-secondary"
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting}
          >
            {submitting ? 'Creating...' : 'Create Simulation'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default CreateSimulation;
