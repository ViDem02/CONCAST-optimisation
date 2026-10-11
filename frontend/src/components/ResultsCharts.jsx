import React, { useState } from 'react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import '../styles/ResultsCharts.css';

function ResultsCharts({ timestepData }) {
  const [chartType, setChartType] = useState('electricity');
  const [dataResolution, setDataResolution] = useState('all'); // 'all', 'hourly', 'daily'

  // Process data based on resolution
  const processData = () => {
    let data = timestepData;

    if (dataResolution === 'hourly') {
      // Aggregate by hour
      const hourlyData = {};
      data.forEach((point) => {
        const hourKey = point.timestamp.substring(0, 13) + ':00:00'; // Round to hour
        if (!hourlyData[hourKey]) {
          hourlyData[hourKey] = {
            timestamp: hourKey,
            total_demand_kWh: 0,
            solar_generation_kWh: 0,
            cogen_generation_kWh: 0,
            grid_electricity_kWh: 0,
            wasted_energy_kWh: 0,
            grid_cost_euros: 0,
            count: 0,
          };
        }
        hourlyData[hourKey].total_demand_kWh += point.total_demand_kWh || 0;
        hourlyData[hourKey].solar_generation_kWh += point.solar_generation_kWh || 0;
        hourlyData[hourKey].cogen_generation_kWh += point.cogen_generation_kWh || 0;
        hourlyData[hourKey].grid_electricity_kWh += point.grid_electricity_kWh || 0;
        hourlyData[hourKey].wasted_energy_kWh += point.wasted_energy_kWh || 0;
        hourlyData[hourKey].grid_cost_euros += point.grid_cost_euros || 0;
        hourlyData[hourKey].count += 1;
      });
      data = Object.values(hourlyData);
    } else if (dataResolution === 'daily') {
      // Aggregate by day
      const dailyData = {};
      data.forEach((point) => {
        const dayKey = point.timestamp.substring(0, 10); // Date only
        if (!dailyData[dayKey]) {
          dailyData[dayKey] = {
            timestamp: dayKey,
            total_demand_kWh: 0,
            solar_generation_kWh: 0,
            cogen_generation_kWh: 0,
            grid_electricity_kWh: 0,
            wasted_energy_kWh: 0,
            grid_cost_euros: 0,
            count: 0,
          };
        }
        dailyData[dayKey].total_demand_kWh += point.total_demand_kWh || 0;
        dailyData[dayKey].solar_generation_kWh += point.solar_generation_kWh || 0;
        dailyData[dayKey].cogen_generation_kWh += point.cogen_generation_kWh || 0;
        dailyData[dayKey].grid_electricity_kWh += point.grid_electricity_kWh || 0;
        dailyData[dayKey].wasted_energy_kWh += point.wasted_energy_kWh || 0;
        dailyData[dayKey].grid_cost_euros += point.grid_cost_euros || 0;
        dailyData[dayKey].count += 1;
      });
      data = Object.values(dailyData);
    }

    // Limit data points for performance
    if (data.length > 1000 && dataResolution === 'all') {
      // Sample every nth point
      const step = Math.ceil(data.length / 1000);
      data = data.filter((_, index) => index % step === 0);
    }

    return data;
  };

  const chartData = processData();

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    if (dataResolution === 'daily') {
      return date.toLocaleDateString();
    } else if (dataResolution === 'hourly') {
      return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
      });
    }
    return date.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="custom-tooltip">
          <p className="tooltip-label">{formatTimestamp(label)}</p>
          {payload.map((entry, index) => (
            <p key={index} style={{ color: entry.color }}>
              {entry.name}: {Number(entry.value).toFixed(2)} {entry.unit || 'kWh'}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const renderElectricityChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <AreaChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTimestamp}
          angle={-45}
          textAnchor="end"
          height={80}
        />
        <YAxis label={{ value: 'Energy (kWh)', angle: -90, position: 'insideLeft' }} />
        <Tooltip content={<CustomTooltip />} />
        <Legend />
        <Area
          type="monotone"
          dataKey="total_demand_kWh"
          stackId="1"
          stroke="#ff7300"
          fill="#ff7300"
          name="Total Demand"
        />
        <Area
          type="monotone"
          dataKey="solar_generation_kWh"
          stackId="2"
          stroke="#ffc658"
          fill="#ffc658"
          name="Solar Generation"
        />
        <Area
          type="monotone"
          dataKey="cogen_generation_kWh"
          stackId="2"
          stroke="#82ca9d"
          fill="#82ca9d"
          name="Cogen Generation"
        />
        <Area
          type="monotone"
          dataKey="grid_electricity_kWh"
          stackId="2"
          stroke="#8884d8"
          fill="#8884d8"
          name="Grid Electricity"
        />
      </AreaChart>
    </ResponsiveContainer>
  );

  const renderGenerationChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTimestamp}
          angle={-45}
          textAnchor="end"
          height={80}
        />
        <YAxis label={{ value: 'Energy (kWh)', angle: -90, position: 'insideLeft' }} />
        <Tooltip content={<CustomTooltip />} />
        <Legend />
        <Line
          type="monotone"
          dataKey="solar_generation_kWh"
          stroke="#ffc658"
          name="Solar Generation"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="cogen_generation_kWh"
          stroke="#82ca9d"
          name="Cogen Generation"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="total_generation_kWh"
          stroke="#8884d8"
          name="Total Generation"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );

  const renderCostChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTimestamp}
          angle={-45}
          textAnchor="end"
          height={80}
        />
        <YAxis label={{ value: 'Cost (€)', angle: -90, position: 'insideLeft' }} />
        <Tooltip content={<CustomTooltip />} />
        <Legend />
        <Bar dataKey="grid_cost_euros" fill="#8884d8" name="Grid Cost" />
      </BarChart>
    </ResponsiveContainer>
  );

  const renderWasteChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <AreaChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTimestamp}
          angle={-45}
          textAnchor="end"
          height={80}
        />
        <YAxis label={{ value: 'Energy (kWh)', angle: -90, position: 'insideLeft' }} />
        <Tooltip content={<CustomTooltip />} />
        <Legend />
        <Area
          type="monotone"
          dataKey="wasted_energy_kWh"
          stroke="#ff0000"
          fill="#ff000066"
          name="Wasted Energy"
        />
      </AreaChart>
    </ResponsiveContainer>
  );

  return (
    <div className="results-charts">
      <div className="charts-controls">
        <div className="control-group">
          <label>Chart Type:</label>
          <select value={chartType} onChange={(e) => setChartType(e.target.value)}>
            <option value="electricity">Electricity Flow</option>
            <option value="generation">Generation Sources</option>
            <option value="cost">Grid Costs</option>
            <option value="waste">Wasted Energy</option>
          </select>
        </div>

        <div className="control-group">
          <label>Time Resolution:</label>
          <select value={dataResolution} onChange={(e) => setDataResolution(e.target.value)}>
            <option value="all">All Timesteps</option>
            <option value="hourly">Hourly Average</option>
            <option value="daily">Daily Total</option>
          </select>
        </div>

        <div className="data-info">
          Showing {chartData.length} data points
        </div>
      </div>

      <div className="chart-container">
        <h3>
          {chartType === 'electricity' && 'Electricity Demand and Supply'}
          {chartType === 'generation' && 'Electricity Generation by Source'}
          {chartType === 'cost' && 'Grid Electricity Costs Over Time'}
          {chartType === 'waste' && 'Wasted Energy Over Time'}
        </h3>
        {chartType === 'electricity' && renderElectricityChart()}
        {chartType === 'generation' && renderGenerationChart()}
        {chartType === 'cost' && renderCostChart()}
        {chartType === 'waste' && renderWasteChart()}
      </div>
    </div>
  );
}

export default ResultsCharts;
