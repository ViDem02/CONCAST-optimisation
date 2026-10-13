import React, { useEffect, useState } from 'react';
import { errorMessage, planApi } from '../services/api';
import { describeMove } from './common';
import '../styles/ShiftsGantt.css';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const WEEK_MINUTES = 7 * 24 * 60;
const COLORS = ['#4a90e2', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#3498db',
                '#c0392b', '#16a085', '#d35400', '#8e44ad'];

const time = (hour, minutes) => `${String(hour).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;

/** Bars of one shift; a shift that runs past Sunday midnight continues at the start of the week. */
function shiftBars(shift) {
  const start = shift.start_day * 1440 + shift.start_hour * 60 + shift.start_minutes;
  let end = shift.end_day * 1440 + shift.end_hour * 60 + shift.end_minutes;
  if (end <= start) end += WEEK_MINUTES;
  const bar = (from, to) => ({ left: `${(from / WEEK_MINUTES) * 100}%`, width: `${((to - from) / WEEK_MINUTES) * 100}%` });
  return end > WEEK_MINUTES ? [bar(start, WEEK_MINUTES), bar(0, end - WEEK_MINUTES)] : [bar(start, end)];
}

/** One week of a production plan: a row per process, a bar per shift. */
function ShiftsGantt({ productionPlanId, title }) {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    setPlan(null);
    planApi.get(productionPlanId)
      .then(setPlan)
      .catch((err) => setError('Could not load the production plan: ' + errorMessage(err)));
  }, [productionPlanId]);

  if (error) return <div className="gantt-error">{error}</div>;
  if (!plan) return <div className="gantt-loading">Loading production plan…</div>;

  return (
    <div className="shifts-gantt">
      <div className="gantt-header">
        <h3>{title ? `${title}: ` : ''}{plan.name}</h3>
      </div>

      <div className="gantt-container" style={{ '--num-days': 7 }}>
        <div className="gantt-timeline">
          {DAYS.map((day) => (
            <div key={day} className="gantt-day"><div className="gantt-day-label">{day}</div></div>
          ))}
        </div>

        <div className="gantt-processes">
          {plan.processes.map((process, index) => (
            <div key={process.id} className="gantt-process">
              <div className="gantt-process-header">
                <div className="process-name">{process.name}</div>
                <div className="process-power">{process.electricity_consumption_kWh} kW</div>
              </div>
              <div className="gantt-shifts-row">
                {process.shifts.flatMap((shift) => shiftBars(shift).map((position, part) => (
                  <div
                    key={`${shift.id}-${part}`}
                    className="gantt-shift"
                    style={{ ...position, backgroundColor: COLORS[index % COLORS.length] }}
                    title={`${process.name}: ${shift.start_day_display} ${time(shift.start_hour, shift.start_minutes)} – ${shift.end_day_display} ${time(shift.end_hour, shift.end_minutes)}`}
                    onClick={() => setSelected({ ...shift, processName: process.name, color: COLORS[index % COLORS.length] })}
                  />
                )))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {selected && (
        <div className="shift-modal-overlay" onClick={() => setSelected(null)}>
          <div className="shift-modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setSelected(null)}>×</button>
            <h3>Shift details</h3>
            <div className="modal-content">
              <div className="modal-row">
                <span className="modal-label">Process:</span>
                <span className="modal-value">
                  <div className="modal-color-indicator" style={{ backgroundColor: selected.color }} />
                  {selected.processName}
                </span>
              </div>
              <div className="modal-row">
                <span className="modal-label">Shift:</span>
                <span className="modal-value">{selected.name}</span>
              </div>
              <div className="modal-divider" />
              <div className="modal-row">
                <span className="modal-label">Starts:</span>
                <span className="modal-value modal-highlight">{selected.start_day_display} at {time(selected.start_hour, selected.start_minutes)}</span>
              </div>
              <div className="modal-row">
                <span className="modal-label">Ends:</span>
                <span className="modal-value modal-highlight">{selected.end_day_display} at {time(selected.end_hour, selected.end_minutes)}</span>
              </div>
              <div className="modal-row">
                <span className="modal-label">May move:</span>
                <span className="modal-value">
                  {selected.max_backwards_minutes || selected.max_forward_minutes
                    ? `${describeMove(-selected.max_backwards_minutes)} to ${describeMove(selected.max_forward_minutes)}`
                    : 'fixed'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ShiftsGantt;
