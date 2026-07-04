"""Celery Beat periodic schedule (plain dict; consumed by celery_app)."""

from __future__ import annotations

# Kept import-free so celery_app can load it without a circular import.
BEAT_SCHEDULE: dict = {
    # Flush any queued transactional emails every minute.
    "dispatch-queued-emails": {
        "task": "revos.dispatch_queued_emails",
        "schedule": 60.0,
    },
    # Advance due sequence enrollments every 5 minutes.
    "tick-sequences": {
        "task": "revos.tick_sequences",
        "schedule": 300.0,
    },
    # Detect expired trials and notify owners (hourly).
    "expire-trials": {
        "task": "revos.expire_trials",
        "schedule": 3600.0,
    },
    # Auto-approve autopilot: execute pending approvals for hands-off accounts.
    "auto-approve-sweep": {
        "task": "revos.auto_approve_sweep",
        "schedule": 60.0,
    },
}
