import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminUrl, chillerApi, errorMessage } from '../services/api';
import { ErrorBox, formatDate, Loading, PageHeader, RunButton, StatusBadge } from './common';

function ChillerSimulationsList() {
  const navigate = useNavigate();
  const [simulations, setSimulations] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setError(null);
      setSimulations(await chillerApi.list());
    } catch (err) {
      setError('Could not load the cold-room simulations: ' + errorMessage(err));
    }
  };

  useEffect(() => { load(); }, []);

  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!simulations) return <Loading what="cold-room simulations" />;

  return (
    <div>
      <PageHeader
        title="Cold rooms"
        subtitle="Simulates a cold room kept within its temperature range, cooling first with solar and cogeneration and pre-cooling when there is surplus."
      >
        <a className="btn btn-secondary" href={adminUrl('ChillersApp/chiller/')}>Cold rooms</a>
        <a className="btn btn-primary" href={adminUrl('ChillersApp/chillersimulation/add/')}>+ New cold-room simulation</a>
      </PageHeader>

      {simulations.length === 0 ? (
        <div className="empty-state">
          <h3>No cold-room simulations yet</h3>
          <p>First describe a cold room (size, insulation, refrigeration unit), then create a simulation for it.</p>
        </div>
      ) : (
        <div className="card-list">
          {simulations.map((s) => (
            <div key={s.id} className="item-card" onClick={() => navigate(`/cold-rooms/${s.id}`)}>
              <div className="card-title">
                <h3>{s.name}</h3>
                <StatusBadge done={s.has_results} />
              </div>
              <dl>
                <dt>Cold room</dt><dd>{s.chiller_name}</dd>
                <dt>Period</dt><dd>{formatDate(s.start_date)} – {formatDate(s.end_date)}</dd>
                <dt>Allowed temperature</dt><dd>{s.min_temperature} to {s.max_temperature} °C</dd>
                {s.production_plan_name && <><dt>Uses the surplus of</dt><dd>{s.production_plan_name}</dd></>}
              </dl>
              {!s.has_results && <RunButton run={() => chillerApi.run(s.id)} onDone={load} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ChillerSimulationsList;
