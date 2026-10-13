import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminUrl, errorMessage, simulationApi } from '../services/api';
import { ErrorBox, euro, formatDate, Loading, PageHeader, RunButton, StatusBadge } from './common';

function SimulationsList() {
  const navigate = useNavigate();
  const [simulations, setSimulations] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setError(null);
      setSimulations(await simulationApi.list());
    } catch (err) {
      setError('Could not load the simulations: ' + errorMessage(err));
    }
  };

  useEffect(() => { load(); }, []);

  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!simulations) return <Loading what="cost simulations" />;

  return (
    <div>
      <PageHeader
        title="Cost simulations"
        subtitle="Grid electricity cost of a production plan over a period, optionally compared with a second plan (usually an optimised one)."
      >
        <a className="btn btn-primary" href={adminUrl('PlanningApp/simulation/add/')}>+ New cost simulation</a>
      </PageHeader>

      {simulations.length === 0 ? (
        <div className="empty-state">
          <h3>No cost simulations yet</h3>
          <p>Create one with “New cost simulation”: choose the plans, the dates and the data to use.</p>
        </div>
      ) : (
        <div className="card-list">
          {simulations.map((s) => {
            const r = s.results;
            return (
              <div key={s.id} className="item-card" onClick={() => navigate(`/simulations/${s.id}`)}>
                <div className="card-title">
                  <h3>{s.name}</h3>
                  <StatusBadge done={!!r} />
                </div>
                <dl>
                  <dt>Period</dt><dd>{formatDate(s.start_date)} – {formatDate(s.end_date)}</dd>
                  <dt>Current plan</dt><dd>{s.original_production_plan_name}</dd>
                  {s.optimized_production_plan_name && <><dt>Compared with</dt><dd>{s.optimized_production_plan_name}</dd></>}
                  {r && <><dt>Cost, current plan</dt><dd>{euro(r.original_cost_euros)}</dd></>}
                  {r && r.savings_euros !== null && <>
                    <dt>Cost, compared plan</dt><dd>{euro(r.optimized_cost_euros)}</dd>
                    <dt>Saving</dt>
                    <dd className={r.savings_euros >= 0 ? 'saving' : 'loss'}>
                      {euro(r.savings_euros)} ({r.savings_percent?.toFixed(1)}%)
                    </dd>
                  </>}
                </dl>
                {!r && <RunButton run={() => simulationApi.run(s.id)} onDone={load} />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default SimulationsList;
