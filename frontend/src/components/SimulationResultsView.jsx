import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { adminUrl, download, errorMessage, simulationApi } from '../services/api';
import ResultsCharts from './ResultsCharts';
import ShiftsGantt from './ShiftsGantt';
import { ErrorBox, euro, formatDate, formatDateTime, Loading, number, PageHeader, RunButton } from './common';
import '../styles/OptimizationResultsView.css';

function SimulationResultsView() {
  const { id } = useParams();
  const [simulation, setSimulation] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setError(null);
      const sim = await simulationApi.get(id);
      setSimulation(sim);
      setResults(sim.results ? await simulationApi.resultsWithTimesteps(sim.results.id) : null);
    } catch (err) {
      setError('Could not load the simulation: ' + errorMessage(err));
    }
  };

  useEffect(() => { load(); }, [id]);

  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!simulation) return <Loading what="the simulation" />;

  const s = simulation;
  const compared = results && results.optimized_cost_euros !== null;
  const exportCsv = async () => {
    try {
      download(await simulationApi.exportCsv(results.id), `${s.name}.csv`);
    } catch (err) {
      alert('The download failed: ' + errorMessage(err));
    }
  };

  return (
    <div className="optimization-results-view">
      <Link className="back-link" to="/simulations">← All cost simulations</Link>
      <PageHeader
        title={s.name}
        subtitle={`${formatDate(s.start_date)} – ${formatDate(s.end_date)} · generation “${s.generation_dataset_name}” · prices “${s.prices_dataset_name}”`}
      >
        <RunButton label={results ? 'Calculate again' : 'Calculate now'} className="btn btn-secondary"
                   run={() => simulationApi.run(s.id)} onDone={load} />
        <a className="btn btn-secondary" href={adminUrl(`PlanningApp/simulation/${s.id}/change/`)}>Edit settings</a>
        {results && <button className="btn btn-secondary" onClick={exportCsv}>Download CSV</button>}
      </PageHeader>

      {!results ? (
        <div className="panel"><p>This simulation has not been calculated yet. Press “Calculate now”.</p></div>
      ) : (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <div className="kpi-label">Grid electricity cost, current plan</div>
              <div className="kpi-value">{euro(results.original_cost_euros)}</div>
              <div className="kpi-note">{s.original_production_plan_name}</div>
            </div>
            {compared && <>
              <div className="kpi">
                <div className="kpi-label">Grid electricity cost, compared plan</div>
                <div className="kpi-value">{euro(results.optimized_cost_euros)}</div>
                <div className="kpi-note">{s.optimized_production_plan_name}</div>
              </div>
              <div className={`kpi ${results.savings_euros >= 0 ? 'good' : 'bad'}`}>
                <div className="kpi-label">{results.savings_euros >= 0 ? 'Saving' : 'Extra cost'}</div>
                <div className="kpi-value">{euro(Math.abs(results.savings_euros))}</div>
                <div className="kpi-note">{Math.abs(results.savings_percent ?? 0).toFixed(1)}% of the cost of the current plan</div>
              </div>
            </>}
          </div>

          <div className="kpi-grid">
            <div className="kpi">
              <div className="kpi-label">Electricity used by production</div>
              <div className="kpi-value">{number(results.total_electricity_used_kWh)} kWh</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Bought from the grid</div>
              <div className="kpi-value">{number(results.grid_electricity_purchased_kWh)} kWh</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Produced on site</div>
              <div className="kpi-value">{number(results.solar_generated_kWh + results.cogen_generated_kWh)} kWh</div>
              <div className="kpi-note">solar {number(results.solar_generated_kWh)} · cogeneration {number(results.cogen_generated_kWh)}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Production left unused</div>
              <div className="kpi-value">{number(results.wasted_energy_kWh)} kWh</div>
              <div className="kpi-note">not credited in the cost</div>
            </div>
          </div>
          <p className="note" style={{ marginBottom: '1.5rem' }}>
            {compared ? 'Energy figures are those of the compared plan. ' : ''}
            Calculated {formatDateTime(results.calculated_at)}.
          </p>

          <ResultsCharts timestepData={results.timestep_data} />

          <div className="production-plans-section">
            <h3>Weekly plans</h3>
            <div className="plans-comparison">
              <div className="plan-gantt"><ShiftsGantt productionPlanId={s.original_production_plan} title="Current plan" /></div>
              {s.optimized_production_plan && (
                <div className="plan-gantt"><ShiftsGantt productionPlanId={s.optimized_production_plan} title="Compared plan" /></div>
              )}
            </div>
          </div>
        </>
      )}

      {s.notes && <div className="panel"><h3>Notes</h3><p>{s.notes}</p></div>}
    </div>
  );
}

export default SimulationResultsView;
