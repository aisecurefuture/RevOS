import logging
import signal
import time

from app.database import SessionLocal, init_db
from app.services.refresh import refresh_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("dealsig.worker")
running = True


def stop(*_args) -> None:
    global running
    running = False


def main() -> None:
    init_db()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Sweep once per minute; each source's own cadence determines whether it is due.
    interval_seconds = 60
    while running:
        started = time.monotonic()
        with SessionLocal() as db:
            runs = refresh_all(db, only_due=True)
            succeeded = sum(run.status == "succeeded" for run in runs)
            logger.info("refresh completed: %s/%s sources succeeded", succeeded, len(runs))
        elapsed = time.monotonic() - started
        deadline = max(5, interval_seconds - int(elapsed))
        for _ in range(deadline):
            if not running:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
