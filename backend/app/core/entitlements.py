"""Plan limits and entitlement helpers (Phase 2 M3).

All limit values live here — change the dataclass fields to adjust what each
tier gets.  The *config* for display prices is in settings; these are the
*access* rules that the API enforces.

Pricing tiers (as of 2026-07-14):
  Pro      $1,999.99/mo | $19,200/yr  — 1 seat,  4 social, 100 contacts
  Pro Max  $3,999.99/mo | $38,400/yr  — 3 seats, 18 social, 500 contacts
  Premium  $5,999.99/mo | $57,600/yr  — 5 seats, 30 social, 1000 contacts

`agency` / `enterprise` are legacy tiers kept only so pre-2026-07-14
subscriptions keep resolving; they are not offered at checkout.

Trial gives Premium-level access for 14 days, then requires upgrade.
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
    # Trial inherits Premium-level limits while active (full evaluation).
    PlanName.trial: PlanLimits(
        seats=5, brands=None, contacts=None,
        emails_per_month=None, social_connections=None,
        ai_drafts_per_month=None, landing_pages=None,
        api_access=True, client_workspaces=True, white_label=False,
    ),
    # --- Current tiers (spec: seats / social / contacts are fixed by pricing;
    #     the remaining caps ladder up sensibly). -----------------------------
    PlanName.pro: PlanLimits(
        seats=1, brands=1, contacts=100,
        emails_per_month=5_000, social_connections=4,
        ai_drafts_per_month=100, landing_pages=3,
        api_access=False, client_workspaces=False, white_label=False,
    ),
    PlanName.pro_max: PlanLimits(
        seats=3, brands=3, contacts=500,
        emails_per_month=25_000, social_connections=18,
        ai_drafts_per_month=500, landing_pages=15,
        api_access=True, client_workspaces=True, white_label=False,
    ),
    PlanName.premium: PlanLimits(
        seats=5, brands=10, contacts=1_000,
        emails_per_month=100_000, social_connections=30,
        ai_drafts_per_month=2_000, landing_pages=50,
        api_access=True, client_workspaces=True, white_label=True,
    ),
    # --- Legacy tiers (retained so old subscriptions resolve). --------------
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
