"""Server-side HTML for public pages: landing pages, embeddable forms, notices.

All dynamic text is HTML-escaped; landing ``body_html`` is already sanitized on
write (Module 6 service). Pages ship a self-contained inline stylesheet and no
JavaScript, so they render safely under a strict CSP (script-src 'none').
"""

from __future__ import annotations

import html

from app.models.campaign import Form, LandingPage

_STYLE = """
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;
background:#f8fafc;color:#0f172a;line-height:1.5}
.wrap{max-width:640px;margin:0 auto;padding:40px 20px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:28px;
box-shadow:0 1px 2px rgba(0,0,0,.05)}
h1{font-size:28px;margin:0 0 8px}h2{font-size:20px}
p{color:#475569}label{display:block;font-size:13px;font-weight:600;margin:14px 0 4px}
input,textarea{width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;font-size:14px}
.consent{display:flex;gap:8px;align-items:flex-start;margin-top:14px;font-weight:400;font-size:13px}
.consent input{width:auto;margin-top:3px}
button{margin-top:18px;background:#4f46e5;color:#fff;border:0;border-radius:8px;
padding:11px 18px;font-size:15px;font-weight:600;cursor:pointer}
.hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
.muted{color:#94a3b8;font-size:12px;margin-top:18px}
.hero{width:100%;border-radius:12px;margin-bottom:20px}
.cta{display:inline-block;margin-top:16px;background:#4f46e5;color:#fff;
padding:11px 20px;border-radius:8px;text-decoration:none;font-weight:600}
"""


def _page(title: str, inner: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><div class=wrap>{inner}</div></body></html>"
    )


def _e(value: str | None) -> str:
    return html.escape(value or "")


def render_form_fields(form: Form, *, action: str, utm: dict | None = None) -> str:
    """Render just the <form> element (reused by the standalone + landing pages)."""
    fields_html = (
        '<label>Email</label><input type=email name=email required '
        'autocomplete=email placeholder="you@example.com">'
    )
    for f in form.fields or []:
        name = _e(f.get("name"))
        if name in ("email", "hp"):
            continue
        label = _e(f.get("label") or name)
        ftype = _e(f.get("type") or "text")
        req = "required" if f.get("required") else ""
        if ftype == "textarea":
            fields_html += f'<label>{label}</label><textarea name="{name}" {req}></textarea>'
        else:
            fields_html += f'<label>{label}</label><input type="{ftype}" name="{name}" {req}>'

    consent_html = ""
    if form.consent_required:
        text = _e(form.consent_text) or "I agree to receive emails and can unsubscribe anytime."
        consent_html = (
            f'<label class=consent><input type=checkbox name=consent value=true required>'
            f"<span>{text}</span></label>"
        )

    utm_hidden = "".join(
        f'<input type=hidden name="{_e(k)}" value="{_e(v)}">'
        for k, v in (utm or {}).items()
        if k.startswith("utm_")
    )
    button = _e(form.success_message and "Submit" or "Subscribe")
    return (
        f'<form method=post action="{_e(action)}">{fields_html}{consent_html}'
        f'<input class=hp type=text name=hp tabindex=-1 autocomplete=off aria-hidden=true>'
        f"{utm_hidden}<button type=submit>{button or 'Subscribe'}</button></form>"
    )


def render_form_page(form: Form, *, action: str, utm: dict | None = None) -> str:
    inner = (
        f"<div class=card><h1>{_e(form.name)}</h1>"
        f"{render_form_fields(form, action=action, utm=utm)}"
        '<p class=muted>Powered by RevOS — permission-based marketing.</p></div>'
    )
    return _page(form.name, inner)


def render_landing(page: LandingPage, form: Form | None, *, action: str, utm: dict | None = None) -> str:
    parts = ["<div class=card>"]
    if page.hero_image_url:
        parts.append(f'<img class=hero src="{_e(page.hero_image_url)}" alt="">')
    parts.append(f"<h1>{_e(page.headline or page.title)}</h1>")
    if page.subheadline:
        parts.append(f"<p>{_e(page.subheadline)}</p>")
    if page.body_html:  # already sanitized on write
        parts.append(f"<div>{page.body_html}</div>")
    if form is not None:
        parts.append(render_form_fields(form, action=action, utm=utm))
    elif page.cta_url and page.cta_label:
        parts.append(f'<a class=cta href="{_e(page.cta_url)}">{_e(page.cta_label)}</a>')
    parts.append("</div>")
    return _page(page.title, "".join(parts))


def render_notice(title: str, message: str) -> str:
    inner = f"<div class=card><h1>{_e(title)}</h1><p>{_e(message)}</p></div>"
    return _page(title, inner)
