"""CRM-lite + LinkedIn import tests (Module 9)."""

from __future__ import annotations

import pytest
from app.models.user import Role

# A LinkedIn export with the real preamble + header (parser must skip preamble).
LINKEDIN_CSV = (
    'Notes:\n'
    '"When exporting your connection data, some email addresses may be missing."\n'
    '\n'
    'First Name,Last Name,URL,Email Address,Company,Position,Connected On\n'
    'Anthony,David,https://www.linkedin.com/in/anthony,,Hoody,Founder,04 May 2026\n'
    'Jane,Doe,https://www.linkedin.com/in/jane,jane@acme.com,Acme,CISO,01 Jan 2024\n'
)


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_contact_crud_and_lead_score(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    senior = await api.post("/api/contacts", headers=h, json={
        "first_name": "Carla", "email": "carla@x.com", "title": "CISO",
        "linkedin_url": "https://linkedin.com/in/carla"})
    junior = await api.post("/api/contacts", headers=h, json={
        "first_name": "Joe", "email": "joe@x.com", "title": "Coordinator"})
    assert senior.status_code == 201
    # Seniority title scores much higher.
    assert senior.json()["lead_score"] > junior.json()["lead_score"]

    listed = await api.get("/api/contacts")
    assert len(listed.json()) == 2


@pytest.mark.asyncio
async def test_linkedin_import_creates_contacts_not_leads(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    resp = await api.post(
        "/api/contacts/import", headers=h,
        files={"file": ("Connections.csv", LINKEDIN_CSV, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert body["companies_created"] == 2
    assert "not mailable" in body["note"].lower()

    # COMPLIANCE: imported connections are CRM contacts, never marketing leads.
    assert (await api.get("/api/leads")).json() == []

    contacts = (await api.get("/api/contacts?source=linkedin_import")).json()
    assert len(contacts) == 2
    jane = next(c for c in contacts if c["email"] == "jane@acme.com")
    assert jane["lead_score"] >= 40  # email + CISO + company + linkedin


@pytest.mark.asyncio
async def test_linkedin_import_is_idempotent(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    files = {"file": ("Connections.csv", LINKEDIN_CSV, "text/csv")}
    first = (await api.post("/api/contacts/import", headers=h, files=files)).json()
    assert first["created"] == 2
    second = (await api.post("/api/contacts/import", headers=h,
                             files={"file": ("Connections.csv", LINKEDIN_CSV, "text/csv")})).json()
    assert second["created"] == 0 and second["updated"] == 2


@pytest.mark.asyncio
async def test_contacts_export_csv(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    await api.post("/api/contacts", headers=h,
                   json={"first_name": "X", "email": "x@e.com"})
    export = await api.get("/api/contacts/export")
    assert export.status_code == 200
    assert "x@e.com" in export.text
    assert export.headers["content-type"].startswith("text/csv")


@pytest.mark.asyncio
async def test_pipeline_seeded_and_deal_flow(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    bid = (await api.post("/api/brands", headers=h, json={"name": "Deal Brand"})).json()["id"]

    stages = (await api.get(f"/api/deals/pipeline?brand_id={bid}")).json()
    assert [s["slug"] for s in stages][:2] == ["new-lead", "engaged"]
    won_stage = next(s for s in stages if s["is_won"])

    deal = await api.post("/api/deals", headers=h, json={
        "brand_id": bid, "name": "Big Deal", "amount_cents": 500000})
    assert deal.status_code == 201
    # Defaults to the first stage.
    assert deal.json()["pipeline_stage_id"] == stages[0]["id"]

    moved = await api.post(f"/api/deals/{deal.json()['id']}/move", headers=h,
                           json={"pipeline_stage_id": won_stage["id"]})
    assert moved.json()["status"] == "won"


@pytest.mark.asyncio
async def test_notes_and_tasks(api, make_user):
    h = await _login(api, **await make_user("admin@test.com", "AdminPass123", Role.admin))
    contact = (await api.post("/api/contacts", headers=h,
                              json={"first_name": "N", "email": "n@e.com"})).json()

    note = await api.post("/api/notes", headers=h, json={
        "entity_type": "contact", "entity_id": contact["id"], "body": "Met at conference"})
    assert note.status_code == 201
    notes = await api.get(f"/api/notes?entity_type=contact&entity_id={contact['id']}")
    assert len(notes.json()) == 1

    task = await api.post("/api/tasks", headers=h, json={
        "title": "Follow up", "entity_type": "contact", "entity_id": contact["id"]})
    assert task.status_code == 201
    done = await api.post(f"/api/tasks/{task.json()['id']}/complete", headers=h)
    assert done.json()["status"] == "done"


@pytest.mark.asyncio
async def test_import_requires_editor(api, make_user):
    h = await _login(api, **await make_user("vw@test.com", "ViewerPass123", Role.viewer))
    resp = await api.post("/api/contacts/import", headers=h,
                          files={"file": ("c.csv", LINKEDIN_CSV, "text/csv")})
    assert resp.status_code == 403
