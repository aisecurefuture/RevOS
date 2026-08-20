# DealSig AI — upgrade brief (handoff to a new session)

Paste this whole file as your opening prompt. It carries context that is
expensive to rediscover, including several claims in the feedback that are
wrong about *where* the problem is.

---

## 0. Orientation

- Code: `~/RevOS/dealsig` (a self-contained FastAPI app inside the RevOS repo).
- Runs in production on a Hetzner box via `docker-compose.prod.yml` as
  `dealsig-web` / `dealsig-worker` / `dealsig-db`, behind Caddy at `dealsig.ai`.
- One FastAPI service serves BOTH the marketing site (`/`) and the app
  (`/app`, `/deals`, `/billing`). Templates in `app/templates`, one stylesheet
  `app/static/app.css`, one script `app/static/app.js`.
- Test + lint: `.venv/bin/python -m pytest -q` and `.venv/bin/python -m ruff check app tests`.
  61 tests pass today. Keep them passing.
- No Alembic. `init_db()` runs `create_all()` plus `database._sync_columns()`,
  which adds declared-but-missing columns to existing tables. **If you add a
  NOT NULL column, give it a `server_default`** or it cannot be added to the
  populated production database.

## 1. Read this before you plan anything

**Almost every item of feedback below is a symptom of one root cause: the
listing records are nearly empty.** Only 3 of 12 sources have parsers
(`treasury`, `gsa`, `govdeals` — see `PARSERS` in `app/services/sources.py`),
and those three parsers extract very little reliably. Fixing the UI without
fixing extraction produces a prettier empty table.

Specifically, before you touch a template, confirm which of these is true for
the field you are about to "add":

| Feedback says | Actual cause |
|---|---|
| "show city on snippets" | City **is already rendered** in `deals.html`. `listing.city` is empty because `ADDRESS_RE` in `sources.py` only matches a full `123 Main St, City, ST 12345` string, which most Treasury/GSA text does not contain. This is a parser fix, not a template fix. |
| "missing prices / deadlines" | `MONEY_RE` only matches `Current Bid $X` / `Starting Bid $X`. `auction_end` is never populated by any parser — no parser sets it at all. |
| "missing profit estimates and scores" | Every score is 0 by design. `_score_listing()` in `refresh.py` short-circuits to `deal_score=0, confidence="unscored"` when `estimated_market_value` is None, and the only thing that sets that value is a third-party AVM behind `MARKET_DATA_API_KEY`, which is unset. **Do not fake this.** |
| "photos" | There is **no image field on the `Listing` model at all**. The thumbnails are CSS gradients cycling `house-one/two/three` by row index. This needs a schema change, parser work, and a hosting decision (see §4). |

## 2. Confirmed bugs — fix these

1. **Treasury deep links go to the index page.** `app/services/sources.py:225`:
   `source_url=urljoin(base_url, parent_link["href"]) if parent_link else base_url`.
   When no anchor is found in the container it falls back to the listing index,
   which is exactly what Goran reported. Worse, `parent_link` is just the first
   `<a>` in the container and may be a nav link rather than the deal link.
   Select the anchor that actually points at a property detail page, and if
   none exists, prefer leaving the record out over linking to the index.

2. **Titles are raw scraped text.** e.g. `2,623 ± sq. ft. home with 3 bedroo…`.
   Build a display title from structured fields (address + city, falling back to
   property type + key stat) and keep the raw text in `description`. Consider a
   `display_title` column rather than overwriting `title`.

3. **Mobile layout drops the numbers.** `app.css:466` collapses the 7-column
   grid to 6 and hides the header row; at phone width the value/profit/deadline
   cells are unreadable (see the user's screenshot). Design the mobile card
   deliberately instead of letting the desktop grid degrade.

## 3. Requested features — safe to build now

- **Filters.** `/deals` already supports `q`, `county`, `source`, `instrument`,
  `sort` (`app/main.py`, `deals()` route). Missing and straightforward:
  `property_type` (the column exists and is populated), and a price range over
  `current_bid`/`starting_bid`. Ryan's "separate homes / land / commercial /
  auctions / tax-sale" is `property_type` + `instrument_type` — mostly a UI
  grouping over filters that already exist.
- **Freshness / verification.** `Listing` already has `first_seen_at`,
  `last_seen_at`, `source_changed_at`. Surface them. `SourceStatus` now also has
  `last_change_at` and health states `healthy` / `monitoring` / `degraded`.
- **Explain the score.** `score_factors` is a JSON column already populated by
  `analyze_deal()` with the model name and its assumptions (8% transaction and
  carry, 15% repair contingency). Render it. Note the honest caveat: repairs
  default to 0 unless the user types them, and on distressed property repairs
  *are* the deal — a score that assumes zero repairs ranks the worst houses
  highest. Say so in the UI.
- **First-run walkthrough.** No blocker.

## 4. Needs a decision before building

- **Photos.** Requires a new field, per-source extraction, and a choice:
  hotlink the source's images (cheap, brittle, may breach source terms) vs.
  cache them (bandwidth, storage, and a clearer licensing question). Check each
  source's terms first — this project has a written policy (README ~line 125)
  against scraping restricted or purpose-limited material, and it has been
  enforced source by source.
- **Maps.** Needs geocoding, which needs a real address, which is currently
  missing for most records. Sequence it after extraction.

## 5. The positioning conflict — surface this, do not resolve it yourself

The feedback contains three incompatible product definitions:

- **Mohammad:** "another listing platform, similar to the MLS… helps buyers,
  sellers, and real estate agents… detailed property and agent information…
  marketing tools."
- **Alan:** a Kayak/Expedia-style aggregator, funded to buy paid data feeds.
- **Ryan / Goran:** an investor tool — comps, profit ranking, auction deadlines.

What is actually built is the third: a government-auction and Illinois
tax-sale aggregator for investors. An MLS-style platform with agent profiles
and seller marketing tools is a different product with different data sources
(IDX/MLS licensing), a different buyer, and different compliance obligations.
**Ask which one is being built before implementing anything that only makes
sense for one of them.**

Two related inconsistencies to raise with the team:

- The pitch one-pager advertises **$99/month**; commit `b7ddc96` lowered
  DealSig Pro to **$19.99/month**. One of them is wrong.
- The one-pager shows comps, cap rates, rent-growth charts, market scores, and
  underwriting playbooks. None of that exists. If it goes on the landing page
  as-is it is marketing ahead of the product by a wide margin.

## 6. Standing constraints

- **No scraping bypass.** No login, CAPTCHA, paywall, or WAF circumvention; no
  headless browser; no proxy rotation. Sources that block the bot are excluded,
  not routed around. This is written policy (README, SECURITY.md) and has been
  applied consistently — five candidate sources were rejected on these grounds.
- The fetcher is `httpx` + BeautifulSoup with no JavaScript execution. A
  client-rendered page yields nothing; do not add a parser that assumes otherwise.
- CSP is `script-src 'self'` with no inline script. Keep it that way — adding a
  third-party map or captcha means relaxing it and updating the privacy notice.
- Never invent a number. If a value is unknown, render it as unknown. The
  product's credibility with these reviewers is already the open question.

## 7. Suggested order

1. Extraction first — address/city, bid, deadline, and a real deep link for the
   3 live parsers. Everything else is downstream.
2. Then titles, mobile layout, filters, freshness display, score explanation.
3. Then photos/maps, once §4 is decided.
4. Scores stay 0 until an AVM or a comps source is connected. Treat "make the
   score real" as its own project, and see the note about county assessor open
   data as a cheaper alternative to a purchased AVM.
