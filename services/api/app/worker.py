"""Processing worker: python -m app.worker. Run as many as you like, claims use FOR UPDATE SKIP LOCKED."""

import logging
import signal
import threading

from .config import get_settings
from .container import Container, build_container
from .jobs import claim_next, fail_job, process_claim
from .observability import configure_logging

log = logging.getLogger("api.worker")


def run_once(c: Container) -> bool:
    """Handle at most one job. Returns whether there was one."""
    claim = claim_next(c)
    if claim is None:
        return False
    if claim.attempts > c.settings.processing_max_attempts:
        fail_job(c, claim, "Processing keeps failing on this file, giving up.")
    else:
        process_claim(c, claim)
    return True


def run_forever(c: Container, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            handle = c.queue.receive()  # long-polls on SQS, returns at once in polling mode
            found = run_once(c)  # runs even without a message: it's the backstop for lost messages and stale jobs
            if handle is not None:  # not reached if run_once raised, so the message returns and can reach the DLQ
                c.queue.ack(handle)
            if not found:
                stop.wait(c.settings.worker_poll_seconds)
        except Exception:
            log.exception("worker loop error")  # usually the database being away; keep polling
            stop.wait(c.settings.worker_poll_seconds)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    stop = threading.Event()

    def shut_down(signum: int, _: object) -> None:
        log.info("shutting down after the current job", extra={"fields": {"signal": signum}})
        stop.set()

    signal.signal(signal.SIGINT, shut_down)
    signal.signal(signal.SIGTERM, shut_down)
    log.info("worker started")
    run_forever(build_container(settings, settings.worker_database_url), stop)


if __name__ == "__main__":
    main()
