import React, { useMemo, useState } from 'react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import '../styles/ResultsCharts.css';

// Energies and costs are added up over the chosen period; the price is averaged
const SUMMED = ['total_demand_kWh', 'original_demand_kWh', 'solar_generation_kWh', 'cogen_generation_kWh',
                'total_generation_kWh', 'grid_electricity_kWh', 'original_grid_electricity_kWh',
                'wasted_energy_kWh', 'original_cost_euros', 'optimized_cost_euros', 'grid_cost_euros'];
const AVERAGED = ['electricity_price'];

const RESOLUTIONS = {
  all: { label: '5 minutes', unit: 'per 5 min', key: (t) => t },
  hourly: { label: 'Hourly', unit: 'per hour', key: (t) => t.substring(0, 13) },
  daily: { label: 'Daily', unit: 'per day', key: (t) => t.substring(0, 10) },
};

/** Default resolution: about a few hundred to a thousand points whatever the period. */
const defaultResolution = (steps) => (steps <= 3 * 288 ? 'all' : steps <= 45 * 288 ? 'hourly' : 'daily');

function aggregate(data, resolution) {
  const timestamps = data.timestamps;
  const keys = [...SUMMED, ...AVERAGED].filter((k) => Array.isArray(data[k]));
  const groups = new Map();
  timestamps.forEach((timestamp, i) => {
    const groupKey = RESOLUTIONS[resolution].key(timestamp);
    let group = groups.get(groupKey);
    if (!group) {
      group = { timestamp, count: 0 };
      keys.forEach((k) => { group[k] = 0; });
      groups.set(groupKey, group);
    }
    group.count += 1;
    keys.forEach((k) => { group[k] += data[k][i] || 0; });
  });
  return [...groups.values()].map((group) => {
    AVERAGED.forEach((k) => { if (k in group) group[k] /= group.count; });
    return group;
  });
}

function ResultsCharts({ timestepData }) {
  const compared = Array.isArray(timestepData.original_demand_kWh);
  const [chart, setChart] = useState(compared ? 'comparison' : 'electricity');
  const [resolution, setResolution] = useState(defaultResolution(timestepData.timestamps.length));
  const points = useMemo(() => aggregate(timestepData, resolution), [timestepData, resolution]);
  const unit = RESOLUTIONS[resolution].unit;

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    if (resolution === 'daily') return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    return date.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  };
  const axis = (
    <XAxis dataKey="timestamp" tickFormatter={formatTime} angle={-35} textAnchor="end" height={70} minTickGap={20} />
  );
  const tooltip = (suffix, decimals = 1) => (
    <Tooltip labelFormatter={formatTime} formatter={(value, name) => [`${Number(value).toFixed(decimals)} ${suffix}`, name]} />
  );

  const charts = {
    comparison: {
      title: 'Production demand of the two plans against on-site generation',
      note: 'Where the compared plan follows the generation more closely, less electricity is bought from the grid.',
      render: () => (
        <LineChart data={points}>
          <CartesianGrid strokeDasharray="3 3" />
          {axis}
          <YAxis label={{ value: `kWh ${unit}`, angle: -90, position: 'insideLeft' }} />
          {tooltip('kWh')}
          <Legend />
          <Line type="stepAfter" dataKey="total_generation_kWh" stroke="#16a34a" strokeWidth={2} dot={false} name="On-site generation" />
          <Line type="stepAfter" dataKey="original_demand_kWh" stroke="#94a3b8" strokeWidth={2} dot={false} name="Demand, current plan" />
          <Line type="stepAfter" dataKey="total_demand_kWh" stroke="#2563eb" strokeWidth={2} dot={false} name="Demand, compared plan" />
        </LineChart>
      ),
    },
    electricity: {
      title: compared ? 'Electricity demand and supply (compared plan)' : 'Electricity demand and supply',
      note: 'Demand is covered first by solar and cogeneration; the rest is bought from the grid.',
      render: () => (
        <AreaChart data={points}>
          <CartesianGrid strokeDasharray="3 3" />
          {axis}
          <YAxis label={{ value: `kWh ${unit}`, angle: -90, position: 'insideLeft' }} />
          {tooltip('kWh')}
          <Legend />
          <Area type="stepAfter" dataKey="cogen_generation_kWh" stackId="supply" stroke="#16a34a" fill="#86efac" name="Cogeneration" />
          <Area type="stepAfter" dataKey="solar_generation_kWh" stackId="supply" stroke="#ca8a04" fill="#fde68a" name="Solar" />
          <Area type="stepAfter" dataKey="grid_electricity_kWh" stroke="#7c3aed" fill="#c4b5fd" name="Bought from the grid" />
          <Area type="stepAfter" dataKey="total_demand_kWh" stroke="#0f172a" fill="none" strokeWidth={2} name="Demand" />
        </AreaChart>
      ),
    },
    cost: {
      title: 'Cost of the electricity bought from the grid',
      render: () => (
        <BarChart data={points}>
          <CartesianGrid strokeDasharray="3 3" />
          {axis}
          <YAxis label={{ value: `€ ${unit}`, angle: -90, position: 'insideLeft' }} />
          {tooltip('€', 2)}
          <Legend />
          {compared ? <>
            <Bar dataKey="original_cost_euros" fill="#94a3b8" name="Current plan" />
            <Bar dataKey="optimized_cost_euros" fill="#2563eb" name="Compared plan" />
          </> : <Bar dataKey="grid_cost_euros" fill="#2563eb" name="Grid cost" />}
        </BarChart>
      ),
    },
    price: {
      title: 'Grid electricity price',
      render: () => (
        <LineChart data={points}>
          <CartesianGrid strokeDasharray="3 3" />
          {axis}
          <YAxis label={{ value: '€/kWh', angle: -90, position: 'insideLeft' }} />
          {tooltip('€/kWh', 4)}
          <Line type="stepAfter" dataKey="electricity_price" stroke="#ea580c" strokeWidth={2} dot={false} name="Price" />
        </LineChart>
      ),
    },
    waste: {
      title: 'On-site production left unused',
      note: 'Electricity produced on site when production does not need it. It is not credited in the cost.',
      render: () => (
        <AreaChart data={points}>
          <CartesianGrid strokeDasharray="3 3" />
          {axis}
          <YAxis label={{ value: `kWh ${unit}`, angle: -90, position: 'insideLeft' }} />
          {tooltip('kWh')}
          <Area type="stepAfter" dataKey="wasted_energy_kWh" stroke="#dc2626" fill="#fecaca" name="Unused production" />
        </AreaChart>
      ),
    },
  };
  if (!compared) delete charts.comparison;
  const current = charts[chart];

  return (
    <div className="results-charts">
      <div className="chart-controls">
        <div>
          <label htmlFor="chart-type">Chart</label>
          <select id="chart-type" value={chart} onChange={(e) => setChart(e.target.value)}>
            {compared && <option value="comparison">Plans compared</option>}
            <option value="electricity">Demand and supply</option>
            <option value="cost">Grid cost</option>
            <option value="price">Electricity price</option>
            <option value="waste">Unused production</option>
          </select>
        </div>
        <div>
          <label htmlFor="resolution">Resolution</label>
          <select id="resolution" value={resolution} onChange={(e) => setResolution(e.target.value)}>
            {Object.entries(RESOLUTIONS).map(([value, { label }]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
      </div>
      <div className="chart-container">
        <h3>{current.title}</h3>
        {current.note && <p className="note">{current.note}</p>}
        <ResponsiveContainer width="100%" height={420}>{current.render()}</ResponsiveContainer>
      </div>
    </div>
  );
}

export default ResultsCharts;
