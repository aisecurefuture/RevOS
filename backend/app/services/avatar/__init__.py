"""Avatar video generation (Phase 3 M3).

``inference`` holds the provider-agnostic backend interface + implementations
(local CPU subprocess pipeline, a stub for tests/demo). Everything else in RevOS
talks to a backend through ``get_backend()`` so the hardware/model can be
swapped (CPU now, a GPU box or remote HTTP service later) without touching the
orchestration or the API.
"""
