"""Exclusive phase durations; instrumentation never changes execution inputs."""
from contextlib import contextmanager
from functools import wraps
import time


class PhaseClock:
    def __init__(self):
        self.totals = {}
        self.active = None
        self.at = time.perf_counter()

    def flush(self):
        now = time.perf_counter()
        if self.active:
            self.totals[self.active] = self.totals.get(self.active, 0.) + now - self.at
        self.at = now

    @contextmanager
    def phase(self, name):
        self.flush()
        previous, self.active = self.active, name
        try:
            yield
        finally:
            self.flush()
            self.active = previous

    def wrap(self, fn, phase):
        @wraps(fn)
        def measured(*args, **kwargs):
            with self.phase(phase):
                return fn(*args, **kwargs)
        return measured

    def attach(self, engine):
        for name, phase in [('prepare', 'calculation'), ('reconcile_session', 'calculation'),
                            ('_verify_run', 'validation'), ('_check_accounts', 'validation'),
                            ('validate_tables', 'validation'), ('save_checkpoint', 'local_save')]:
            setattr(engine, name, self.wrap(getattr(engine, name), phase))

    def snapshot(self):
        self.flush()
        return dict(self.totals)

    def row(self, day, completed, started, prior):
        totals = self.snapshot()
        phases = {name: totals.get(name, 0.) - prior.get(name, 0.)
                  for name in ['calculation', 'validation', 'local_save', 'remote_save']}
        wall = time.perf_counter() - started
        return dict(day=day, completed=completed, wall_seconds=wall, **phases,
                    other_seconds=max(0., wall - sum(phases.values())),
                    artifact_upload_seconds=None)
