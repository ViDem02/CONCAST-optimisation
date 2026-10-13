import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { adminUrl, datasetApi, errorMessage, optimizationApi, planApi, simulationApi } from '../services/api';
import { ErrorBox, euro, formatDate, Loading } from './common';

function Step({ number, title, children, status, actions }) {
  return (
    <div className="step">
      <div className="step-number">{number}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      <div className="step-status">{status}</div>
      <div className="step-actions">{actions}</div>
    </div>
  );
}

function Home() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setError(null);
      const [generation, prices, plans, optimizations, simulations] = await Promise.all([
        datasetApi.generation(), datasetApi.prices(), planApi.list(), optimizationApi.list(), simulationApi.list(),
      ]);
      setData({ generation, prices, plans, optimizations, simulations });
    } catch (err) {
      setError('Could not load the data: ' + errorMessage(err));
    }
  };

  useEffect(() => { load(); }, []);

  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!data) return <Loading what="the overview" />;

  const { generation, prices, plans, optimizations, simulations } = data;
  const lastOptimization = optimizations.find((o) => o.is_completed);
  const currentPlans = plans.filter((p) => !p.is_optimized);
  const coverage = (datasets) => {
    const withData = datasets.filter((d) => d.record_count > 0);
    if (!withData.length) return 'none yet';
    const first = withData.map((d) => d.first_timestamp).sort()[0];
    const last = withData.map((d) => d.last_timestamp).sort().slice(-1)[0];
    return `${formatDate(first)} – ${formatDate(last)}`;
  };

  return (
    <div className="home">
      <div className="panel">
        <h3>What SPARC does</h3>
        <p>
          SPARC moves the flexible production shifts within the time each shift is allowed to move, so that more of
          the electricity they need comes from the solar panels and the cogenerator, or is bought when it is cheaper.
          It then shows how much the change saves over any period.
        </p>
        <p className="note">
          Enter and calculate things in <a href={adminUrl()}>Manage data</a>; look at the results on this website.
        </p>
      </div>

      {lastOptimization && (
        <div className="kpi-grid">
          <div className="kpi good">
            <div className="kpi-label">Latest optimisation: saving on its reference week</div>
            <div className="kpi-value">{euro(lastOptimization.cost_savings_euros)}</div>
            <div className="kpi-note">
              {lastOptimization.cost_savings_percent?.toFixed(1)}% of the grid electricity cost ·{' '}
              <Link to={`/optimizations/${lastOptimization.id}`}>{lastOptimization.name}</Link>
            </div>
          </div>
        </div>
      )}

      <div className="steps">
        <Step
          number={1}
          title="Input data"
          status={`Generation: ${coverage(generation)} · Prices: ${coverage(prices)}`}
          actions={<a className="btn btn-secondary btn-small" href={adminUrl('DatasetApp/')}>Upload or check data</a>}
        >
          Hourly solar and cogeneration production, electricity prices and outside temperature, as CSV files.
        </Step>
        <Step
          number={2}
          title="Production plan"
          status={`${currentPlans.length} plan${currentPlans.length === 1 ? '' : 's'} entered`}
          actions={<>
            <Link className="btn btn-secondary btn-small" to="/plans">See the plans</Link>
            <a className="btn btn-secondary btn-small" href={adminUrl('PlanningApp/weeklyproductionplan/import/')}>Import a plan</a>
          </>}
        >
          The shifts of a typical week, with how many minutes each shift may start earlier or later.
        </Step>
        <Step
          number={3}
          title="Optimise the shifts"
          status={`${optimizations.filter((o) => o.is_completed).length} optimisation(s) calculated`}
          actions={<>
            <Link className="btn btn-secondary btn-small" to="/optimizations">See results</Link>
            <a className="btn btn-primary btn-small" href={adminUrl('OptimizerApp/optimization/add/')}>New optimisation</a>
          </>}
        >
          Choose a plan and a reference week: SPARC finds the cheapest start time of every flexible shift and saves it
          as a new plan.
        </Step>
        <Step
          number={4}
          title="Check the savings"
          status={`${simulations.filter((s) => s.results).length} cost simulation(s) calculated`}
          actions={<>
            <Link className="btn btn-secondary btn-small" to="/simulations">See results</Link>
            <a className="btn btn-primary btn-small" href={adminUrl('PlanningApp/simulation/add/')}>New simulation</a>
          </>}
        >
          Compare the current and the optimised plan over a month or a season, with the real generation and prices.
        </Step>
      </div>
    </div>
  );
}

export default Home;
