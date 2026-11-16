"""Run independent lookups in parallel, safely.

* Each task runs inside an app context, so caching and config work in workers.
* A failing task returns its default instead of failing the whole page (B6).
* Never pass `current_user`/`request`/`session` into these tasks (A3).
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

log = logging.getLogger(__name__)


def _wrap(app, fn):
    def runner(*args, **kwargs):
        with app.app_context():
            return fn(*args, **kwargs)
    return runner


def run_parallel(tasks, max_workers=8, timeout=45):
    """Run {name: (fn, args, default)} concurrently; returns {name: result}."""
    if not tasks:
        return {}
    app = current_app._get_current_object()
    results = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as pool:
        futures = {
            name: pool.submit(_wrap(app, spec[0]), *spec[1])
            for name, spec in tasks.items()
        }
        for name, future in futures.items():
            default = tasks[name][2] if len(tasks[name]) > 2 else None
            try:
                results[name] = future.result(timeout=timeout)
            except Exception as exc:
                log.warning("Parallel task %r failed: %s", name, exc)
                results[name] = default
    return results


def parallel_map(fn, items, max_workers=8, default=None, timeout=45):
    """[fn(item) for item in items] in parallel, keeping order; failures -> default."""
    items = list(items)
    if not items:
        return []
    app = current_app._get_current_object()
    wrapped = _wrap(app, fn)
    out = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        futures = [pool.submit(wrapped, item) for item in items]
        for item, future in zip(items, futures):
            try:
                out.append(future.result(timeout=timeout))
            except Exception as exc:
                log.warning("parallel_map(%s) failed for %r: %s", getattr(fn, "__name__", fn), item, exc)
                out.append(default)
    return out
