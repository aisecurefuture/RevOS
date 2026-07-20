"""Celery application.

Task modules (email sends, sequence ticks, re-engagement sweeps) are added in
later modules and registered here via `include`. Beat schedules live in
`beat_schedule.py`. Broker and result backend come from Redis.
"""

from __future__ import annotations

from celery import Celery

from app.config import settings
from app.workers.beat_schedule import BEAT_SCHEDULE

celery_app = Celery(
    "revos",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks",
        "app.workers.avatar_tasks",
        "app.workers.pitch_video_tasks",
        "app.workers.listing_video_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                 # redelivery on worker crash
    worker_prefetch_multiplier=1,        # fair dispatch for long email jobs
    task_reject_on_worker_lost=True,
    result_expires=60 * 60 * 24,         # keep results 24h
    beat_schedule=BEAT_SCHEDULE,
    # Avatar generation is minutes-to-hours and runs on a dedicated worker/queue
    # so it never blocks the fast email/social workers. Pitch Video Studio's
    # audio stage reuses that SAME queue/worker (it's the same XTTS backend);
    # only its render stage gets its own queue/worker (Node + Remotion).
    task_routes={
        "avatar.generate": {"queue": "avatar"},
        "pitch_video.generate_audio": {"queue": "avatar"},
        "pitch_video.list_speakers": {"queue": "avatar"},
        "pitch_video.render": {"queue": "pitch_video"},
        # Listing Video Studio reuses the same two workers.
        "listing_video.generate_audio": {"queue": "avatar"},
        "listing_video.render": {"queue": "pitch_video"},
    },
    # A generation can exceed the default 1h visibility timeout; extend it so the
    # broker doesn't redeliver a job that's legitimately still running.
    broker_transport_options={"visibility_timeout": 4 * 60 * 60},
)


@celery_app.task(name="revos.ping")
def ping() -> str:
    """Liveness task used by tests and ops to confirm the worker is wired up."""
    return "pong"
