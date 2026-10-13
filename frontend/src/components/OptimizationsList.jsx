import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminUrl, errorMessage, optimizationApi } from '../services/api';
import { ErrorBox, euro, formatDate, Loading, PageHeader, StatusBadge } from './common';
import { OptimizeButton } from './OptimizationProgress';

function OptimizationsList() {
  const navigate = useNavigate();
  const [optimizations, setOptimizations] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setError(null);
      setOptimizations(await optimizationApi.list());
    } catch (err) {
      setError('Could not load the optimisations: ' + errorMessage(err));
    }
  };

  useEffect(() => { load(); }, []);

  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!optimizations) return <Loading what="optimisations" />;

  return (
    <div>
      <PageHeader
        title="Shift optimisations"
        subtitle="Each optimisation moves the flexible shifts of a plan to the cheapest times of a reference week and saves the result as a new plan."
      >
        <a className="btn btn-primary" href={adminUrl('OptimizerApp/optimization/add/')}>+ New optimisation</a>
      </PageHeader>

      {optimizations.length === 0 ? (
        <div className="empty-state">
          <h3>No optimisations yet</h3>
          <p>Create one with “New optimisation”: choose a plan, a reference week and the data to use.</p>
        </div>
      ) : (
        <div className="card-list">
          {optimizations.map((o) => (
            <div key={o.id} className="item-card" onClick={() => navigate(`/optimizations/${o.id}`)}>
              <div className="card-title">
                <h3>{o.name}</h3>
                {o.live?.status === 'running'
                  ? <span className="status-badge running">Calculating</span>
                  : <StatusBadge done={o.is_completed} />}
              </div>
              <dl>
                <dt>Plan</dt><dd>{o.reference_production_plan_name}</dd>
                <dt>Reference week</dt><dd>{formatDate(o.reference_week_start)} – {formatDate(o.reference_week_end)}</dd>
                {o.is_completed && <>
                  <dt>Cost before → after</dt><dd>{euro(o.initial_cost_euros)} → {euro(o.optimized_cost_euros)}</dd>
                  <dt>Saving</dt>
                  <dd className="saving">{euro(o.cost_savings_euros)} ({o.cost_savings_percent?.toFixed(1)}%)</dd>
                </>}
              </dl>
              {(!o.is_completed || o.live?.status !== 'done') && (
                <OptimizeButton id={o.id} live={o.live} onDone={load} compact />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default OptimizationsList;
