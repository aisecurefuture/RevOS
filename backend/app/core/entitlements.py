"""Plan limits and entitlement helpers (Phase 2 M3).

All limit values live here — change the dataclass fields to adjust what each
tier gets.  The *config* for display prices is in settings; these are the
*access* rules that the API enforces.

Pricing tiers (as of 2026-07-04):
  Pro    $149/mo | $119/mo annual  — solo operators, small business
  Agency $449/mo | $359/mo annual  — agencies, growing teams
  Enterprise custom                — franchises, large orgs

Trial gives Agency-level access for 14 days, then requires upgrade.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.billing import PlanName, Subscription, SubscriptionStatus
from app.models.base import utcnow


@dataclass(frozen=True)
class PlanLimits:
    # None means unlimited.
    seats: int | None
    brands: int | None
    contacts: int | None
    emails_per_month: int | None
    social_connections: int | None
    ai_drafts_per_month: int | None
    landing_pages: int | None
    # Feature flags (boolean gates).
    api_access: bool
    client_workspaces: bool   # invite external collaborators / client accounts
    white_label: bool


PLAN_LIMITS: dict[PlanName, PlanLimits] = {
    # Trial inherits Agency limits while active.
    PlanName.trial: PlanLimits(
        seats=3, brands=None, contacts=None,
        emails_per_month=None, social_connections=None,
        ai_drafts_per_month=None, landing_pages=None,
        api_access=True, client_workspaces=True, white_label=False,
    ),
    PlanName.pro: PlanLimits(
        seats=3, brands=2, contacts=10_000,
        emails_per_month=10_000, social_connections=5,
        ai_drafts_per_month=200, landing_pages=5,
        api_access=False, client_workspaces=False, white_label=False,
    ),
    PlanName.agency: PlanLimits(
        seats=15, brands=None, contacts=100_000,
        emails_per_month=100_000, social_connections=None,
        ai_drafts_per_month=None, landing_pages=None,
        api_access=True, client_workspaces=True, white_label=False,
    ),
    PlanName.enterprise: PlanLimits(
        seats=None, brands=None, contacts=None,
        emails_per_month=None, social_connections=None,
        ai_drafts_per_month=None, landing_pages=None,
        api_access=True, client_workspaces=True, white_label=True,
    ),
}


def get_effective_plan(sub: Subscription | None) -> PlanName | None:
    """Return the plan whose limits apply right now, or None if trial expired/canceled.

    None → the account is locked (expired trial or canceled subscription);
           requests should be gated behind a payment wall.
    """
    if sub is None:
        return None
    if sub.status == SubscriptionStatus.trialing:
        if sub.trial_ends_at and utcnow() > sub.trial_ends_at:
            return None  # trial expired — account locked until upgrade
        return PlanName.trial  # trial active → agency-level access
    if sub.status in (SubscriptionStatus.active, SubscriptionStatus.past_due):
        return sub.plan  # past_due still has access during Stripe grace period
    return None  # canceled / incomplete → locked


def get_plan_limits(sub: Subscription | None) -> PlanLimits:
    """Return the PlanLimits for the subscription's effective plan.

    Falls back to Pro limits when the effective plan is None (expired/canceled)
    so callers always get a usable dataclass — the caller should still block
    the user with a 402 if `get_effective_plan` returned None.
    """
    plan = get_effective_plan(sub)
    return PLAN_LIMITS.get(plan or PlanName.pro, PLAN_LIMITS[PlanName.pro])


def is_trial_expired(sub: Subscription | None) -> bool:
    if sub is None:
        return True
    if sub.status != SubscriptionStatus.trialing:
        return False
    return sub.trial_ends_at is None or utcnow() > sub.trial_ends_at
