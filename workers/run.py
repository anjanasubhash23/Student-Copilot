"""Run the job worker: `uv run python -m workers.run`.

Not needed when the API runs with RUN_WORKER=true (the default), which starts the same loop in a thread.
Several workers can run at once; each job is claimed by exactly one.
"""

import logging
import threading
from contextlib import closing
from datetime import timedelta

from neo4j import Driver

from app.settings import Settings, get_settings
from core.graph.client import create_driver
from core.llm import model_label, track_usage
from core.storage import sqlite
from core.storage.jobs import SqliteJobQueue
from workers.tasks import Context, JobError, run_job

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)  # no progress for this long: the worker died


def work(settings: Settings, stop: threading.Event, driver: Driver | None = None) -> None:
    own_driver = driver is None
    driver = driver or create_driver(settings)
    try:
        with closing(sqlite.connect(settings.sqlite_path)) as conn:
            sqlite.migrate(conn)
            queue = SqliteJobQueue(conn)
            if requeued := queue.requeue_stale(STALE_AFTER):
                log.warning("requeued %d stale jobs", requeued)
            ctx = Context(settings=settings, conn=conn, driver=driver)
            while not stop.is_set():
                if not run_one(ctx, queue):
                    stop.wait(settings.worker_poll_seconds)
    finally:
        if own_driver:
            driver.close()


def run_one(ctx: Context, queue: SqliteJobQueue) -> bool:
    """Run the next queued job, if any. Returns whether there was one."""
    job = queue.claim()
    if job is None:
        return False
    log.info("job %d: %s (space %s)", job.id, job.kind, job.space_id)
    with track_usage() as usage:
        try:
            run_job(ctx, job)
        except JobError as exc:
            log.warning("job %d failed: %s", job.id, exc)
            queue.fail(job.id, str(exc))
        except Exception as exc:
            log.exception("job %d crashed", job.id)
            queue.fail(job.id, f"{type(exc).__name__}: {exc}")
        else:
            queue.finish(job.id)
        finally:
            queue.record_usage(job.id, usage, model_label())
    if usage.calls or usage.cached:
        log.info(
            "job %d: %d LLM calls (%d cached), %d+%d tokens, %.1fs waiting on the model",
            job.id,
            usage.calls,
            usage.cached,
            usage.input_tokens,
            usage.output_tokens,
            usage.seconds,
        )
    return True


def start_in_thread(settings: Settings, driver: Driver) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    thread = threading.Thread(target=work, args=(settings, stop, driver), name="job-worker", daemon=True)
    thread.start()
    return thread, stop


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()
    log.info("worker started; Ctrl-C to stop")
    try:
        work(settings, stop)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
