import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { adminUrl, chillerApi, download, errorMessage } from '../services/api';
import { ErrorBox, formatDate, Loading, number, PageHeader, RunButton } from './common';

/** One point per 5 minutes, or hourly averages for periods longer than a week. */
function chartPoints(simulation) {
  const temperature = simulation.calculated_temperature;
  const power = simulation.chiller_power_delivery;
  const hourly = temperature.timestamps.length > 7 * 288;
  const groups = new Map();
  temperature.timestamps.forEach((timestamp, i) => {
    const key = hourly ? timestamp.substring(0, 13) : timestamp;
    let g = groups.get(key);
    if (!g) {
      g = { timestamp, n: 0, temperature: 0, outside: 0, generation: 0, grid: 0 };
      groups.set(key, g);
    }
    g.n += 1;
    g.temperature += temperature.temperature_C[i];
    g.outside += temperature.outside_temperature_C ? temperature.outside_temperature_C[i] : 0;
    g.generation += power.power_kW[i] - power.grid_consumption_kW[i];
    g.grid += power.grid_consumption_kW[i];
  });
  return [...groups.values()].map((g) => ({
    timestamp: g.timestamp,
    temperature: g.temperature / g.n,
    outside: temperature.outside_temperature_C ? g.outside / g.n : null,
    generation: g.generation / g.n,
    grid: g.grid / g.n,
  }));
}

const formatTime = (timestamp) =>
  new Date(timestamp).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

function ChillerResultsView() {
  const { id } = useParams();
  const [simulation, setSimulation] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      setError(null);
      setSimulation(await chillerApi.get(id));
    } catch (err) {
      setError('Could not load the cold-room simulation: ' + errorMessage(err));
    }
  };

  useEffect(() => { load(); }, [id]);

  const hasResults = !!(simulation?.calculated_temperature && simulation?.chiller_power_delivery);
  const points = useMemo(() => (hasResults ? chartPoints(simulation) : []), [simulation, hasResults]);

  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!simulation) return <Loading what="the cold-room simulation" />;

  const s = simulation;
  const temperature = s.calculated_temperature;
  const power = s.chiller_power_delivery;
  const axis = <XAxis dataKey="timestamp" tickFormatter={formatTime} angle={-35} textAnchor="end" height={70} minTickGap={20} />;
  const exportCsv = async () => {
    try {
      download(await chillerApi.exportCsv(s.id), `${s.name}.csv`);
    } catch (err) {
      alert('The download failed: ' + errorMessage(err));
    }
  };

  return (
    <div>
      <Link className="back-link" to="/cold-rooms">← All cold-room simulations</Link>
      <PageHeader title={s.name} subtitle={`Cold room “${s.chiller_name}”, ${formatDate(s.start_date)} – ${formatDate(s.end_date)}`}>
        <RunButton label={hasResults ? 'Calculate again' : 'Calculate now'} className="btn btn-secondary"
                   run={() => chillerApi.run(s.id)} onDone={load} />
        <a className="btn btn-secondary" href={adminUrl(`ChillersApp/chillersimulation/${s.id}/change/`)}>Edit settings</a>
        {hasResults && <button className="btn btn-secondary" onClick={exportCsv}>Download CSV</button>}
      </PageHeader>

      {!hasResults ? (
        <div className="panel"><p>This simulation has not been calculated yet. Press “Calculate now”.</p></div>
      ) : (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <div className="kpi-label">Room temperature (min / average / max)</div>
              <div className="kpi-value">{number(temperature.min_temp, 1)} / {number(temperature.avg_temp, 1)} / {number(temperature.max_temp, 1)} °C</div>
              <div className="kpi-note">allowed {s.min_temperature} to {s.max_temperature} °C</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Electricity used by the cold room</div>
              <div className="kpi-value">{number(power.total_cooling_kWh)} kWh</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">of which bought from the grid</div>
              <div className="kpi-value">{number(power.total_grid_consumption_kWh)} kWh</div>
              <div className="kpi-note">{s.allow_grid_power ? 'grid allowed when generation is not enough' : 'grid not allowed'}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">On-site production still unused</div>
              <div className="kpi-value">{number(power.total_wasted_kWh)} kWh</div>
              <div className="kpi-note">{s.production_plan_name ? `surplus left by “${s.production_plan_name}”` : 'of the whole on-site generation'}</div>
            </div>
          </div>

          <div className="panel">
            <h3>Room temperature</h3>
            <ResponsiveContainer width="100%" height={380}>
              <LineChart data={points}>
                <CartesianGrid strokeDasharray="3 3" />
                {axis}
                <YAxis label={{ value: '°C', angle: -90, position: 'insideLeft' }} />
                <Tooltip labelFormatter={formatTime} formatter={(v, name) => [`${Number(v).toFixed(1)} °C`, name]} />
                <Legend />
                <Line type="monotone" dataKey={() => s.max_temperature} stroke="#dc2626" strokeDasharray="5 5" dot={false} name="Maximum allowed" />
                <Line type="monotone" dataKey={() => s.min_temperature} stroke="#dc2626" strokeDasharray="5 5" dot={false} name="Minimum allowed" />
                <Line type="monotone" dataKey="temperature" stroke="#2563eb" strokeWidth={2} dot={false} name="Room" />
                {temperature.outside_temperature_C && (
                  <Line type="monotone" dataKey="outside" stroke="#ea580c" dot={false} name="Outside" />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="panel">
            <h3>Where the cold room's electricity comes from</h3>
            <ResponsiveContainer width="100%" height={380}>
              <AreaChart data={points}>
                <CartesianGrid strokeDasharray="3 3" />
                {axis}
                <YAxis label={{ value: 'kW', angle: -90, position: 'insideLeft' }} />
                <Tooltip labelFormatter={formatTime} formatter={(v, name) => [`${Number(v).toFixed(1)} kW`, name]} />
                <Legend />
                <Area type="monotone" dataKey="generation" stackId="1" stroke="#16a34a" fill="#86efac" name="On-site generation" />
                <Area type="monotone" dataKey="grid" stackId="1" stroke="#dc2626" fill="#fecaca" name="Grid" />
              </AreaChart>
            </ResponsiveContainer>
            {points.length < temperature.timestamps.length && <p className="note">Hourly averages.</p>}
          </div>

          <p className="note">
            Controller settings: proportional gain {s.proportional_gain}, derivative gain {s.derivative_gain},
            minimum runtime {s.minimum_runtime_minutes} min, start-up period {s.initial_window_hours} h.
            Room: {s.chiller_details.surface_area} m², U = {s.chiller_details.insulation_u_value} W/m²K,
            unit {s.chiller_details.nominal_capacity_kW} kW.
          </p>
        </>
      )}
    </div>
  );
}

export default ChillerResultsView;
