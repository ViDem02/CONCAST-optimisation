import React, { useEffect, useRef, useState } from 'react';
import { errorMessage, optimizationApi } from '../services/api';

const seconds = (from, to) => Math.max(0, (new Date(to) - new Date(from)) / 1000);

/**
 * Live state of an optimisation: start() launches the calculation in the background and the
 * hook polls its progress every second while it runs (also when it was started elsewhere,
 * e.g. from the admin). onFinished(state) is called when a run ends (done or failed).
 */
export function useLiveOptimization(id, initial, onFinished) {
  const [live, setLive] = useState(initial);
  const [error, setError] = useState(null);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  useEffect(() => { if (initial) setLive(initial); }, [initial?.status, initial?.progress?.updated_at]);

  useEffect(() => {
    if (live?.status !== 'running') return undefined;
    const timer = setTimeout(async () => {
      try {
        const next = await optimizationApi.progress(id);
        setLive(next);
        if (next.status !== 'running') finished.current?.(next);
      } catch (err) {
        setError(errorMessage(err));
      }
    }, 1000);
    return () => clearTimeout(timer);
  }, [id, live]);

  const start = async () => {
    setError(null);
    try {
      const state = await optimizationApi.run(id);
      setLive(state);
      if (state.status !== 'running') finished.current?.(state);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return { live, start, error, running: live?.status === 'running' };
}

/** Progress bar, current step and elapsed time of a running optimisation (or why it failed). */
export function OptimizationProgress({ live, compact = false }) {
  const [, tick] = useState(0);
  const received = useRef(Date.now());
  useEffect(() => { received.current = Date.now(); }, [live]);
  const running = live?.status === 'running';
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => tick((n) => n + 1), 250);
    return () => clearInterval(timer);
  }, [running]);

  if (!live) return null;
  if (live.status === 'failed') {
    return <div className="opt-progress failed"><strong>The calculation failed.</strong> {live.error}</div>;
  }
  if (!running) return null;

  const p = live.progress || {};
  const steps = live.steps || [];
  const step = p.step || 0;
  const sinceReceived = (Date.now() - received.current) / 1000;
  const total = seconds(p.started_at, live.now) + sinceReceived;
  const inStep = seconds(p.step_started_at || p.started_at, live.now) + sinceReceived;
  const fraction = p.time_limit ? Math.min(inStep / p.time_limit, 0.95) : 0.5;
  const width = Math.max(4, (100 * (Math.max(step - 1, 0) + fraction)) / (steps.length || 4));

  return (
    <div className="opt-progress" role="status" aria-live="polite" onClick={(e) => e.stopPropagation()}>
      <div className="opt-progress-bar"><span style={{ width: `${width}%` }} /></div>
      <div className="opt-progress-text">
        <strong>{step ? `Step ${step} of ${steps.length}: ${p.label}` : 'Starting…'}</strong>
        {!compact && p.detail && <span> · {p.detail}</span>}
        <span className="note"> · {Math.round(total)} s{p.time_limit ? ` (the search stops after at most ${p.time_limit} s)` : ''}</span>
      </div>
      {!compact && (
        <ol className="opt-progress-steps">
          {steps.map((label, index) => (
            <li key={label} className={index + 1 < step ? 'done' : index + 1 === step ? 'current' : ''}>{label}</li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** "Optimise now" button that shows the live progress below it while the calculation runs. */
export function OptimizeButton({ id, live: initial, onDone, label = 'Optimise now', className = 'btn btn-primary', compact }) {
  const { live, start, error, running } = useLiveOptimization(id, initial, onDone);
  return (
    <div className="optimize-button" onClick={(e) => e.stopPropagation()}>
      {!running && (
        <button className={className} onClick={(e) => { e.preventDefault(); start(); }}>{label}</button>
      )}
      <OptimizationProgress live={live} compact={compact} />
      {error && <div className="run-error">{error}</div>}
    </div>
  );
}
