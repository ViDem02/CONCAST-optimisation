import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { adminUrl, errorMessage, optimizationApi } from '../services/api';
import ShiftsGantt from './ShiftsGantt';
import { describeMove, ErrorBox, euro, formatDate, formatDateTime, Loading, PageHeader } from './common';
import { OptimizationProgress, useLiveOptimization } from './OptimizationProgress';
import '../styles/OptimizationResultsView.css';

function solutionQuality(data) {
  const status = data.solver_status || '';
  if (status.includes('Optimal')) return 'Best possible schedule (proven optimal)';
  if (data.mip_gap !== undefined) {
    return `Time limit reached: the cost is at most ${(100 * data.mip_gap).toFixed(1)}% above the best possible`;
  }
  return status || null;
}

function OptimizationResultsView() {
  const { id } = useParams();
  const [optimization, setOptimization] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setError(null);
      setOptimization(await optimizationApi.get(id));
    } catch (err) {
      setError('Could not load the optimisation: ' + errorMessage(err));
    }
  };

  useEffect(() => { load(); }, [id]);

  // Live progress of a calculation started here or elsewhere; reload the results when it ends
  const run = useLiveOptimization(id, optimization?.live, load);

  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!optimization) return <Loading what="the optimisation" />;

  const o = optimization;
  const data = o.optimization_data || {};
  const changes = data.shift_changes || [];
  const moved = changes.filter((c) => c.shift_minutes !== 0);
  const quality = solutionQuality(data);
  const checkUrl = adminUrl('PlanningApp/simulation/add/') + '?' + new URLSearchParams({
    name: `Check of ${o.name}`,
    original_production_plan: o.reference_production_plan,
    optimized_production_plan: o.optimized_production_plan || '',
    generation_dataset: o.generation_dataset || '',
    prices_dataset: o.prices_dataset || '',
  });

  return (
    <div className="optimization-results-view">
      <Link className="back-link" to="/optimizations">← All optimisations</Link>
      <PageHeader
        title={o.name}
        subtitle={`Plan “${o.reference_production_plan_name}”, reference week ${formatDate(o.reference_week_start)} – ${formatDate(o.reference_week_end)}`}
      >
        <button className="btn btn-secondary" disabled={run.running} onClick={run.start}>
          {run.running ? 'Calculating…' : o.is_completed ? 'Optimise again' : 'Optimise now'}
        </button>
        <a className="btn btn-secondary" href={adminUrl(`OptimizerApp/optimization/${o.id}/change/`)}>Edit settings</a>
        {o.is_completed && <a className="btn btn-primary" href={checkUrl}>Check over a longer period</a>}
      </PageHeader>

      {(run.running || run.live?.status === 'failed' || run.error) && (
        <div className="panel">
          <OptimizationProgress live={run.live} />
          {run.error && <p className="run-error">{run.error}</p>}
        </div>
      )}

      {!o.is_completed ? (
        !run.running && <div className="panel"><p>This optimisation has not been calculated yet. Press “Optimise now”.</p></div>
      ) : (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <div className="kpi-label">Grid electricity cost, current plan</div>
              <div className="kpi-value">{euro(o.initial_cost_euros)}</div>
              <div className="kpi-note">on the reference week</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Grid electricity cost, optimised plan</div>
              <div className="kpi-value">{euro(o.optimized_cost_euros)}</div>
              <div className="kpi-note">on the reference week</div>
            </div>
            <div className="kpi good">
              <div className="kpi-label">Saving</div>
              <div className="kpi-value">{euro(o.cost_savings_euros)}</div>
              <div className="kpi-note">{o.cost_savings_percent?.toFixed(1)}% of the cost</div>
            </div>
          </div>

          <div className="panel">
            <h3>{moved.length} of {changes.length} shifts moved</h3>
            {quality && <p className="note">Quality of the solution: {quality}. Calculated {formatDateTime(o.completed_at)}.</p>}
            <p className="note">
              The new plan “{o.optimized_production_plan_name}” is the result: the savings are exact for the reference week.
              Use “Check over a longer period” to see how the same plan performs on other weeks.
            </p>
            {moved.length > 0 && (
              <>
                <ResponsiveContainer width="100%" height={Math.max(220, moved.length * 24 + 40)}>
                  <BarChart data={moved.map((c) => ({ name: `${c.process_name} · run ${c.run_number}`, minutes: c.shift_minutes }))}
                            layout="vertical" margin={{ left: 40, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" unit=" min" />
                    <YAxis type="category" dataKey="name" width={140} interval={0} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(value) => [describeMove(value), 'Moved']} />
                    <Bar dataKey="minutes">
                      {moved.map((c, i) => <Cell key={i} fill={c.shift_minutes > 0 ? '#2563eb' : '#f59e0b'} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p className="note">Blue: the shift starts later. Orange: the shift starts earlier.</p>
              </>
            )}
          </div>

          <div className="production-plans-section">
            <h3>Week before and after</h3>
            <div className="plans-comparison">
              <div className="plan-gantt"><ShiftsGantt productionPlanId={o.reference_production_plan} title="Current plan" /></div>
              {o.optimized_production_plan && (
                <div className="plan-gantt"><ShiftsGantt productionPlanId={o.optimized_production_plan} title="Optimised plan" /></div>
              )}
            </div>
          </div>
        </>
      )}

      {o.notes && <div className="panel"><h3>Notes</h3><p>{o.notes}</p></div>}
    </div>
  );
}

export default OptimizationResultsView;
