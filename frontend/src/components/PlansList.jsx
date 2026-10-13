import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { adminUrl, errorMessage, planApi } from '../services/api';
import ShiftsGantt from './ShiftsGantt';
import { ErrorBox, formatDate, Loading, PageHeader } from './common';

/** Production plans; with an id in the address, the week of that plan. */
function PlansList() {
  const { id } = useParams();
  const [plans, setPlans] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setError(null);
      setPlans(await planApi.list());
    } catch (err) {
      setError('Could not load the production plans: ' + errorMessage(err));
    }
  };

  useEffect(() => { load(); }, []);

  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!plans) return <Loading what="production plans" />;

  const selected = id ? plans.find((p) => String(p.id) === id) : null;

  if (selected) {
    const shifts = selected.processes.reduce((n, p) => n + p.shifts.length, 0);
    return (
      <div>
        <Link className="back-link" to="/plans">← All production plans</Link>
        <PageHeader
          title={selected.name}
          subtitle={`${selected.processes.length} processes, ${shifts} shifts · ${selected.is_optimized ? 'created by an optimisation' : 'imported or entered'}`}
        >
          <a className="btn btn-secondary" href={adminUrl(`PlanningApp/weeklyproductionplan/${selected.id}/change/`)}>Edit</a>
        </PageHeader>
        <ShiftsGantt productionPlanId={selected.id} />
        <p className="note">Click a shift to see its times and how far it may move.</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Production plans" subtitle="Weekly plans: which process runs when, every week.">
        <a className="btn btn-primary" href={adminUrl('PlanningApp/weeklyproductionplan/import/')}>+ Import a plan</a>
      </PageHeader>
      {plans.length === 0 ? (
        <div className="empty-state"><h3>No production plans yet</h3><p>Import one from a CSV timetable and a YAML file.</p></div>
      ) : (
        <div className="card-list">
          {plans.map((p) => (
            <Link key={p.id} className="item-card" to={`/plans/${p.id}`}>
              <div className="card-title">
                <h3>{p.name}</h3>
                {p.is_optimized && <span className="status-badge completed">Optimised</span>}
              </div>
              <dl>
                <dt>Processes</dt><dd>{p.processes.length}</dd>
                <dt>Shifts</dt><dd>{p.processes.reduce((n, process) => n + process.shifts.length, 0)}</dd>
                <dt>Created</dt><dd>{formatDate(p.created_at)}</dd>
              </dl>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default PlansList;
