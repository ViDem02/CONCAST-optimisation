import React, { useState } from 'react';
import { errorMessage } from '../services/api';
import '../styles/common.css';

export const euro = (value, decimals = 2) =>
  value === null || value === undefined
    ? '–'
    : `€${Number(value).toLocaleString('en-GB', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;

export const number = (value, decimals = 0) =>
  value === null || value === undefined
    ? '–'
    : Number(value).toLocaleString('en-GB', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

export const formatDate = (value) =>
  value ? new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '–';

export const formatDateTime = (value) =>
  value
    ? new Date(value).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '–';

/** "1 h 30 min later", "15 min earlier", "not moved". */
export const describeMove = (minutes) => {
  if (!minutes) return 'not moved';
  const hours = Math.floor(Math.abs(minutes) / 60);
  const rest = Math.abs(minutes) % 60;
  const amount = [hours ? `${hours} h` : '', rest ? `${rest} min` : ''].filter(Boolean).join(' ');
  return `${amount} ${minutes > 0 ? 'later' : 'earlier'}`;
};

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="page-header">
      <div>
        <h2>{title}</h2>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

export function Loading({ what = 'data' }) {
  return <div className="loading">Loading {what}…</div>;
}

export function ErrorBox({ message, onRetry }) {
  return (
    <div className="error-container">
      <p className="error">{message}</p>
      {onRetry && <button className="btn btn-secondary" onClick={onRetry}>Try again</button>}
    </div>
  );
}

/**
 * Button that runs a calculation on the server, shows that it is working and
 * reports the error message of the server if it fails.
 */
export function RunButton({ run, onDone, label = 'Calculate now', className = 'btn btn-primary' }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  const handleClick = async (event) => {
    event.stopPropagation();
    event.preventDefault();
    setRunning(true);
    setError(null);
    try {
      await run();
      onDone?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <span className="run-button" onClick={(e) => e.stopPropagation()}>
      <button className={className} onClick={handleClick} disabled={running}>
        {running ? 'Calculating…' : label}
      </button>
      {error && <span className="run-error">{error}</span>}
    </span>
  );
}

export function StatusBadge({ done }) {
  return <span className={`status-badge ${done ? 'completed' : 'pending'}`}>{done ? 'Calculated' : 'Not calculated'}</span>;
}
