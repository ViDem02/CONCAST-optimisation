"""
Optimisations run in the background, with live progress.

start() marks the optimisation as running and calculates it in a thread, so the
web request returns at once; the pages then poll progress_of() (through the API
/api/optimizer/optimizations/<id>/progress/) and show which step is running.

The progress is stored in Optimization.progress:

    {"step": 3, "steps": 4, "label": "Searching for the cheapest timetable",
     "detail": "30 runs, 1,086 possible positions (MILP (HiGHS))",
     "started_at": ..., "step_started_at": ..., "updated_at": ..., "time_limit": 20}

While the solver runs, a heartbeat refreshes updated_at every few seconds. A run
whose heartbeat stopped (e.g. SPARC was restarted during the calculation) is
reported as failed instead of running forever.

The HiGHS solver releases the GIL, so the web worker stays responsive while a
calculation runs in its thread. Set OPTIMIZATION_BACKGROUND = False (tests) to
calculate in the request instead.
"""

import threading
from datetime import datetime, timedelta

from django.conf import settings
from django.db import DatabaseError, close_old_connections, connection
from django.utils import timezone

from .models import Optimization
from .optimizer_packager import STEPS, run_optimization

HEARTBEAT_SECONDS = 2
STALE_AFTER = timedelta(seconds=90)


def _now():
    return timezone.now().isoformat()


class ProgressRecorder:
    """The progress callback of run_optimization: writes each step to the database."""

    def __init__(self, optimization_id, echo=None):
        self.optimization_id = optimization_id
        self.echo = echo  # Optional function receiving a line of text (management command)
        self.progress = {'step': 0, 'steps': len(STEPS), 'label': 'Starting', 'detail': '',
                         'started_at': _now(), 'step_started_at': _now(), 'updated_at': _now(), 'time_limit': None}
        self._heartbeat = None
        self._stop = threading.Event()

    def _save(self):
        self.progress['updated_at'] = _now()
        Optimization.objects.filter(pk=self.optimization_id).update(progress=dict(self.progress))

    def __call__(self, step, detail='', time_limit=None):
        self.stop_heartbeat()
        self.progress.update(step=step, label=STEPS[step - 1], detail=detail, time_limit=time_limit,
                             step_started_at=_now())
        self._save()
        if self.echo:
            self.echo(f'[{step}/{len(STEPS)}] {STEPS[step - 1]}' + (f': {detail}' if detail else ''))
        if time_limit:  # The solver step can last up to the time limit: keep the progress fresh
            self._stop.clear()
            self._heartbeat = threading.Thread(target=self._beat, daemon=True)
            self._heartbeat.start()

    def _beat(self):
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                self._save()
            except DatabaseError:
                pass  # A missed heartbeat only delays the news; the next one retries
        close_old_connections()
        connection.close()

    def stop_heartbeat(self):
        if self._heartbeat:
            self._stop.set()
            self._heartbeat.join()
            self._heartbeat = None


def run_now(optimization_id, echo=None):
    """Calculate in the current thread, recording progress and the final status. Re-raises errors."""
    recorder = ProgressRecorder(optimization_id, echo)
    Optimization.objects.filter(pk=optimization_id).update(status='running', error='', progress=recorder.progress)
    try:
        result = run_optimization(optimization_id, progress=recorder)
    except Exception as e:
        recorder.stop_heartbeat()
        Optimization.objects.filter(pk=optimization_id).update(
            status='failed', error=str(e) or e.__class__.__name__, progress=dict(recorder.progress, updated_at=_now()))
        raise
    recorder.stop_heartbeat()
    recorder.progress.update(step=len(STEPS), label='Done', detail='', time_limit=None)
    Optimization.objects.filter(pk=optimization_id).update(status='done', progress=dict(recorder.progress, updated_at=_now()))
    return result


def _run_in_thread(optimization_id):
    try:
        run_now(optimization_id)
    except Exception:
        pass  # Recorded as status "failed" with its message
    finally:
        connection.close()


def is_running(optimization):
    """Running and still sending news (a run without heartbeat for STALE_AFTER is considered dead)."""
    if optimization.status != 'running':
        return False
    updated = (optimization.progress or {}).get('updated_at')
    return bool(updated) and timezone.now() - datetime.fromisoformat(updated) < STALE_AFTER


def start(optimization_id):
    """
    Start calculating an optimisation. Returns the thread (None when calculated in the request),
    or raises AlreadyRunning.
    """
    optimization = Optimization.objects.get(pk=optimization_id)
    if is_running(optimization):
        raise AlreadyRunning(f'"{optimization.name}" is already being calculated.')
    recorder_state = ProgressRecorder(optimization_id).progress
    Optimization.objects.filter(pk=optimization_id).update(status='running', error='', progress=recorder_state)
    if not getattr(settings, 'OPTIMIZATION_BACKGROUND', True):
        try:
            run_now(optimization_id)
        except Exception:
            pass  # Recorded as status "failed"
        return None
    thread = threading.Thread(target=_run_in_thread, args=(optimization_id,), daemon=True,
                              name=f'optimization-{optimization_id}')
    thread.start()
    return thread


class AlreadyRunning(Exception):
    pass


def progress_of(optimization):
    """Status, progress and result summary of an optimisation, for the pages that poll it."""
    status, error = optimization.status, optimization.error
    if status == 'running' and not is_running(optimization):
        status, error = 'failed', 'The calculation stopped without finishing (was SPARC restarted?). Start it again.'
    if status == 'new' and optimization.is_completed():
        status = 'done'  # Calculated before progress was recorded
    return {
        'id': optimization.pk,
        'status': status,
        'steps': STEPS,
        'progress': optimization.progress,
        'error': error,
        'is_completed': optimization.is_completed(),
        'now': _now(),
    }


def interrupt_running():
    """Mark the calculations interrupted by a restart as failed (called on start-up)."""
    return Optimization.objects.filter(status='running').update(
        status='failed', error='The calculation was interrupted because SPARC was restarted. Start it again.')
