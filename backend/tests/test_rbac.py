"""RBAC capability tests (Module 3)."""

from __future__ import annotations

from app.core.rbac import (
    can_approve,
    can_edit_content,
    can_manage_integrations,
    can_send_email,
    role_at_least,
    role_rank,
)
from app.models.user import Role


def test_role_ordering():
    assert role_rank(Role.owner) > role_rank(Role.admin) > role_rank(Role.editor) > role_rank(Role.viewer)
    assert role_at_least(Role.admin, Role.editor)
    assert not role_at_least(Role.editor, Role.admin)


def test_editor_can_edit_not_send():
    assert can_edit_content(Role.editor)
    assert not can_send_email(Role.editor)
    assert not can_approve(Role.editor)


def test_admin_can_send_and_approve_not_integrations():
    assert can_send_email(Role.admin)
    assert can_approve(Role.admin)
    assert not can_manage_integrations(Role.admin)


def test_owner_can_everything():
    assert can_manage_integrations(Role.owner)
    assert can_approve(Role.owner)
    assert can_send_email(Role.owner)
    assert can_edit_content(Role.owner)


def test_viewer_is_read_only():
    assert not can_edit_content(Role.viewer)
    assert not can_send_email(Role.viewer)
    assert not can_approve(Role.viewer)
