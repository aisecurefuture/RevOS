"""Thin httpx adapters for low-cost, per-account integrations (Phase 3).

Each module wraps one provider's REST API with no SDK dependency. Credentials
are passed in by the caller (read from OpenBao by
``integration_credentials_service``) — these modules never touch storage.
"""
