import React, { useState, useEffect } from 'react';
import axios from 'axios';
import '../styles/ShiftsGantt.css';

function ShiftsGantt({ productionPlanId }) {
  const [productionPlan, setProductionPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedShift, setSelectedShift] = useState(null);
  const [showTwoWeeks, setShowTwoWeeks] = useState(true);

  const DAYS_ONE_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const DAYS_TWO_WEEKS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const DAYS = showTwoWeeks ? DAYS_TWO_WEEKS : DAYS_ONE_WEEK;
  const NUM_DAYS = showTwoWeeks ? 14 : 7;
  const HOURS_IN_DAY = 24;
  const TOTAL_MINUTES = NUM_DAYS * 24 * 60;

  useEffect(() => {
    if (productionPlanId) {
      fetchProductionPlan();
    }
  }, [productionPlanId]);

  const fetchProductionPlan = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/planning/production-plans/${productionPlanId}/`);
      setProductionPlan(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load production plan: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const calculatePosition = (startDay, startHour, startMinutes, endDay, endHour, endMinutes) => {
    let startTotalMinutes = startDay * 24 * 60 + startHour * 60 + startMinutes;
    let endTotalMinutes = endDay * 24 * 60 + endHour * 60 + endMinutes;
    
    // If shift wraps around the week (end < start), add 7 days to end
    if (endTotalMinutes <= startTotalMinutes) {
      endTotalMinutes += 7 * 24 * 60;
    }
    
    const left = (startTotalMinutes / TOTAL_MINUTES) * 100;
    const width = ((endTotalMinutes - startTotalMinutes) / TOTAL_MINUTES) * 100;
    
    return { left: `${left}%`, width: `${width}%` };
  };

  const toggleWeekView = () => {
    setShowTwoWeeks(!showTwoWeeks);
  };

  const getShiftColor = (processIndex) => {
    const colors = [
      '#4a90e2', '#e74c3c', '#2ecc71', '#f39c12', 
      '#9b59b6', '#1abc9c', '#e67e22', '#3498db',
      '#c0392b', '#16a085', '#d35400', '#8e44ad'
    ];
    return colors[processIndex % colors.length];
  };

  const handleShiftClick = (shift, processName, processColor) => {
    setSelectedShift({
      ...shift,
      processName,
      processColor
    });
  };

  const closeModal = () => {
    setSelectedShift(null);
  };

  const formatTime = (hour, minutes) => {
    return `${String(hour).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
  };

  if (loading) {
    return <div className="gantt-loading">Loading production plan...</div>;
  }

  if (error) {
    return <div className="gantt-error">{error}</div>;
  }

  if (!productionPlan) {
    return null;
  }

  return (
    <div className="shifts-gantt">
      <div className="gantt-header">
        <h3>Production Shifts Schedule - {productionPlan.name}</h3>
        <button className="week-toggle-btn" onClick={toggleWeekView}>
          {showTwoWeeks ? 'Show 1 Week' : 'Show 2 Weeks'}
        </button>
      </div>
      
      <div className="gantt-container" style={{ '--num-days': NUM_DAYS }}>
        {/* Timeline header */}
        <div className="gantt-timeline">
          {DAYS.map((day, dayIndex) => (
            <div key={dayIndex} className="gantt-day">
              <div className="gantt-day-label">{day}</div>
            </div>
          ))}
        </div>

        {/* Processes and shifts */}
        <div className="gantt-processes">
          {productionPlan.processes.map((process, processIndex) => (
            <div key={process.id} className="gantt-process">
              <div className="gantt-process-header">
                <div className="process-name">{process.name}</div>
                <div className="process-power">{process.electricity_consumption_kWh} kWh</div>
              </div>
              
              <div className="gantt-shifts-row">
                {process.shifts.map((shift) => {
                  const position = calculatePosition(
                    shift.start_day,
                    shift.start_hour,
                    shift.start_minutes,
                    shift.end_day,
                    shift.end_hour,
                    shift.end_minutes
                  );
                  
                  return (
                    <div
                      key={shift.id}
                      className="gantt-shift"
                      style={{
                        ...position,
                        backgroundColor: getShiftColor(processIndex),
                      }}
                      onClick={() => handleShiftClick(shift, process.name, getShiftColor(processIndex))}
                    >
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="gantt-legend">
        <h4>Processes</h4>
        <div className="legend-items">
          {productionPlan.processes.map((process, index) => (
            <div key={process.id} className="legend-item">
              <div 
                className="legend-color" 
                style={{ backgroundColor: getShiftColor(index) }}
              ></div>
              <span>{process.name} ({process.electricity_consumption_kWh} kWh)</span>
            </div>
          ))}
        </div>
      </div>

      {/* Shift Details Modal */}
      {selectedShift && (
        <div className="shift-modal-overlay" onClick={closeModal}>
          <div className="shift-modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={closeModal}>×</button>
            <h3>Shift Details</h3>
            
            <div className="modal-content">
              <div className="modal-row">
                <span className="modal-label">Shift Name:</span>
                <span className="modal-value">{selectedShift.name}</span>
              </div>
              
              <div className="modal-row">
                <span className="modal-label">Process:</span>
                <span className="modal-value">
                  <div 
                    className="modal-color-indicator" 
                    style={{ backgroundColor: selectedShift.processColor }}
                  ></div>
                  {selectedShift.processName}
                </span>
              </div>
              
              <div className="modal-divider"></div>
              
              <div className="modal-row">
                <span className="modal-label">Start Time:</span>
                <span className="modal-value modal-highlight">
                  {selectedShift.start_day_display} at {formatTime(selectedShift.start_hour, selectedShift.start_minutes)}
                </span>
              </div>
              
              <div className="modal-row">
                <span className="modal-label">End Time:</span>
                <span className="modal-value modal-highlight">
                  {selectedShift.end_day_display} at {formatTime(selectedShift.end_hour, selectedShift.end_minutes)}
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
