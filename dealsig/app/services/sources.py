from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urljoin

import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:  # A minimal runtime can still run; live HTML parsing requires the pinned dependency.
    BeautifulSoup = None  # type: ignore[assignment,misc]

from app.config import get_settings


@dataclass(frozen=True)
class SourceDefinition:
    slug: str
    name: str
    url: str
    source_type: str
    interval_minutes: int
    acquisition_note: str


SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        "treasury",
        "U.S. Treasury Real Property",
        "https://www.treasury.gov/auctions/treasury/rp/realprop.shtml",
        "listing_feed",
        15,
        "Public auction. Register with the auction contractor and follow that property's terms.",
    ),
    SourceDefinition(
        "gsa",
        "GSA Real Estate Sales",
        "https://realestatesales.gov/our-listing/",
        "listing_feed",
        15,
        "Register through Login.gov and the official GSA bidder workflow before placing a bid.",
    ),
    SourceDefinition(
        "govdeals",
        "GovDeals Real Estate",
        "https://prod-seo.govdeals.com/en/single-family-property-residential?ps=120",
        "listing_feed",
        15,
        "Open the official lot page, register, and verify buyer premium and payment terms.",
    ),
    SourceDefinition(
        "fdic",
        "FDIC Real Estate & Property Sales",
        "https://www.fdic.gov/asset-sales/real-estate-and-property-sales",
        "calendar_monitor",
        60,
        "Contact the broker or FDIC contractor on the property listing and submit the required offer package.",
    ),
    SourceDefinition(
        "us_marshals",
        "U.S. Marshals Asset Forfeiture",
        "https://www.usmarshals.gov/what-we-do/asset-forfeiture",
        "calendar_monitor",
        60,
        "Follow the named auction vendor and sale-specific terms; do not send funds from an aggregator.",
    ),
    SourceDefinition(
        "cook_county",
        "Cook County Tax Sale",
        "https://www.cookcountytreasurer.com/taxsalegeneralinformation.aspx",
        "calendar_monitor",
        180,
        "Register as a tax buyer and review the current rules. You bid on a tax lien, not the property.",
    ),
    SourceDefinition(
        "will_county",
        "Will County Tax Sale",
        "https://willcounty.gov/County-Offices/Budget-Finance/Treasurer-Office/Tax-Sale-Information",
        "calendar_monitor",
        180,
        "Complete county tax-buyer registration and funding requirements. The sale is for unpaid taxes.",
    ),
    SourceDefinition(
        "kane_county",
        "Kane County Tax Sale",
        # /Pages/Tax-Sale.aspx began returning 404; the Treasurer home page
        # links the current tax-sale documents. Re-verify if this ever 404s —
        # the monitor now reports degraded instead of silently hashing an
        # error page.
        "https://treasurer.kanecountyil.gov/",
        "calendar_monitor",
        180,
        "Register with the Treasurer and follow the annual tax-sale packet and statutory redemption process.",
    ),
    SourceDefinition(
        "lake_county",
        "Lake County Tax Sale",
        "https://www.lakecountyil.gov/552/Tax-Sale-Information",
        "calendar_monitor",
        180,
        "Purchase and use the delinquent list only as allowed by county rules; attend and fund as instructed.",
    ),
    SourceDefinition(
        "dupage_county",
        "DuPage County Tax Sale",
        # Replaces .../property_tax_information/tax_sale.php, which now 404s.
        "https://www.dupagecounty.gov/elected_officials/treasurer/tax_sale_information.php",
        "calendar_monitor",
        180,
        "Verify the current Treasurer instructions and understand that an annual tax sale conveys a lien.",
    ),
    SourceDefinition(
        "mchenry_county",
        "McHenry County Tax Sale",
        "https://www.mchenrycountyil.gov/departments/treasurer/your-property-taxes/tax-sale",
        "calendar_monitor",
        180,
        "Register with the Treasurer, fund as instructed, and attend the RAMS tax-lien sale in person.",
    ),
    SourceDefinition(
        "kendall_county",
        "Kendall County Tax Sale",
        "https://www.kendallcountyil.gov/offices/treasurer/annual-tax-sale",
        "calendar_monitor",
        180,
        "Review the annual sale and single-bidder rules and confirm registration directly with the Treasurer.",
    ),
)

SOURCE_BY_SLUG = {source.slug: source for source in SOURCES}


@dataclass
class ParsedListing:
    external_id: str
    title: str
    source_url: str
    display_title: str = ""
    image_url: str = ""
    description: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    county: str = ""
    property_type: str = "unknown"
    instrument_type: str = "direct_sale"
    status: str = "open"
    auction_start: datetime | None = None
    auction_end: datetime | None = None
    current_bid: Decimal | None = None
    starting_bid: Decimal | None = None
    deposit_amount: Decimal | None = None
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    how_to_buy: list[str] = field(default_factory=list)
    due_diligence: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


@dataclass
class FetchResult:
    records: list[ParsedListing]
    content_hash: str
    etag: str = ""
    # True when the source answered 304. Distinguishes "nothing changed" from
    # "fetched fine but produced nothing", which are opposite health signals.
    not_modified: bool = False


ADDRESS_RE = re.compile(
    r"(?P<address>\d{1,6}\s+[^\n,]{3,80}),\s*(?P<city>[A-Za-z .'-]{2,50}),\s*"
    r"(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)"
)
MONEY_RE = re.compile(r"(?:Current|Starting) Bid\s*\$?([\d,]+(?:\.\d{2})?)", re.I)

# "SINGLE FAMILY HOME: 5645 Whitner Drive, Atlanta, Georgia 30327 ONLINE AUCTION
# DATE: Thursday, August 20, 2026"
TREASURY_HEADER_RE = re.compile(
    r"^(?P<ptype>[^:]+):\s*(?P<addr>.*?)\s*ONLINE AUCTION DATE:\s*(?P<date>.*)$", re.I
)

# Anchored at the END on purpose. The street portion may itself contain a comma
# ("914 N. Fulton Avenue, Unit A"), so a left-to-right split misplaces the city.
US_ADDRESS_RE = re.compile(
    r"^(?P<address>.+?),\s*(?P<city>[^,]+),\s*"
    r"(?P<state>[A-Za-z][A-Za-z .]*?)\s+(?P<zip>\d{5}(?:-\d{4})?)$"
)

# Treasury spells states out in full ("Atlanta, Georgia 30327"), and Listing.state
# is String(2) — writing "Georgia" would overflow the column on Postgres.
STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "puerto rico": "PR", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "virgin islands": "VI", "guam": "GU",
}


def _state_code(value: str) -> str:
    """Normalise to a 2-letter code, or "" — never a value the column cannot hold."""
    cleaned = _clean(value).strip(" .,")
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper()
    return STATE_CODES.get(cleaned.lower(), "")


def _split_us_address(value: str) -> tuple[str, str, str, str]:
    """(street, city, state_code, zip) from "street, city, State 12345"."""
    match = US_ADDRESS_RE.match(_clean(value))
    if not match:
        return "", "", "", ""
    return (
        match.group("address").strip()[:500],
        match.group("city").strip()[:120],
        _state_code(match.group("state")),
        match.group("zip").strip()[:20],
    )


def _display_title(address: str, city: str, state: str, fallback: str) -> str:
    """A title an investor can scan, rather than the source's marketing sentence."""
    place = ", ".join(part for part in (city, state) if part)
    if address and place:
        return f"{address}, {place}"[:300]
    if address:
        return address[:300]
    return _clean(fallback).title()[:300]


def _clean(text: str) -> str:
    return " ".join(text.split())


def _money(text: str) -> Decimal | None:
    match = MONEY_RE.search(text)
    return Decimal(match.group(1).replace(",", "")) if match else None


def _property_type(text: str) -> str:
    lowered = text.lower()
    if "single family" in lowered or "single-family" in lowered or "home" in lowered:
        return "single_family"
    if "multi-family" in lowered or "multifamily" in lowered or "duplex" in lowered:
        return "multi_family"
    if "commercial" in lowered or "warehouse" in lowered:
        return "commercial"
    if "land" in lowered or "lot" in lowered or "acre" in lowered:
        return "land"
    return "unknown"


TREASURY_HOW_TO_BUY = [
    "Open the official property detail and read the complete Terms of Sale.",
    "Create an account with the named Treasury auction contractor.",
    "Register for the specific sale and fund the required deposit exactly as instructed.",
    "Inspect the property and complete title, lien, occupancy, and repair diligence before bidding.",
]


def parse_treasury(html: str, base_url: str) -> list[ParsedListing]:
    """Parse the Treasury seized-property index.

    The page is legacy table markup with unclosed <tr> tags, so every <tr>
    nests inside the previous one and a <tr>-keyed search finds nothing. The
    stable anchor is the p.style1 header and its enclosing <td>.
    """
    if BeautifulSoup is None:
        return _fallback_treasury(html, base_url)
    soup = BeautifulSoup(html, "html.parser")
    records: list[ParsedListing] = []
    seen: set[str] = set()

    for header in soup.select("p.style1"):
        container = header.find_parent("td")
        if container is None:
            continue
        # The separator MUST be "" — the source splits the label across tags as
        # <b>ONLINE AUCTION DAT</b><strong>E: </strong>, so joining on " "
        # yields "ONLINE AUCTION DAT E:" and every date regex misses.
        header_text = _clean(header.get_text("", strip=True))
        head = TREASURY_HEADER_RE.match(header_text)
        if not head:
            continue

        body = container.get_text(" ", strip=True)
        sale_match = re.search(r"Sale\s*#\s*([\w-]+)", body, re.I)
        if not sale_match or sale_match.group(1) in seen:
            continue
        sale_id = sale_match.group(1)
        seen.add(sale_id)

        photo_cell = container.find_next_sibling("td")
        address, city, state, postal = _split_us_address(head.group("addr").strip())
        blurb = container.find("span", class_="style11")

        records.append(
            ParsedListing(
                external_id=sale_id,
                title=_clean(f"{head.group('ptype').strip()}: {head.group('addr').strip()}")[:300],
                display_title=_display_title(address, city, state, head.group("ptype").strip()),
                description=_clean(blurb.get_text(" ", strip=True))[:4000] if blurb else "",
                source_url=_treasury_detail_url(container, photo_cell, base_url),
                address=address,
                city=city,
                state=state,
                postal_code=postal,
                property_type=_property_type(head.group("ptype")),
                auction_end=_treasury_auction_date(head.group("date")),
                image_url=_treasury_image(photo_cell, base_url),
                how_to_buy=TREASURY_HOW_TO_BUY,
                due_diligence=STANDARD_DUE_DILIGENCE,
                raw_data={"parser": "treasury_html_v2"},
            )
        )
    return records


def _treasury_detail_url(container, photo_cell, base_url: str) -> str:
    """Return the property's own page, or "" — never the index.

    The page carries stale copy-paste anchors: one dead property's href appears
    in 19 of 21 cells, another in 8. Taking the first <a> would send records to
    the WRONG property, which is worse than sending them nowhere. So an anchor
    is accepted only when its filename matches the slug of the record's own
    photo. Records with no published detail page correctly get "".
    """
    img = photo_cell.find("img") if photo_cell else None
    src = img.get("src", "") if img else ""
    if not src:
        return ""
    slug = re.sub(r"\d*\.gif$", "", src.split("/")[-1], flags=re.I)
    if not slug:
        return ""
    anchors = list(container.find_all("a", href=True))
    if photo_cell:
        anchors += list(photo_cell.find_all("a", href=True))
    for anchor in anchors:
        href = anchor["href"]
        if href.lower().endswith(".shtml") and re.sub(r"\.shtml$", "", href.split("/")[-1], flags=re.I) == slug:
            return urljoin(base_url, href)
    return ""


def _treasury_image(photo_cell, base_url: str) -> str:
    img = photo_cell.find("img") if photo_cell else None
    src = img.get("src", "") if img else ""
    return urljoin(base_url, src) if src else ""


def _treasury_auction_date(raw: str) -> datetime | None:
    """Header dates read "Thursday, August 20, 2026". Some read "COMING SOON"."""
    cleaned = _clean(raw)
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_gsa(html: str, base_url: str) -> list[ParsedListing]:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    records: list[ParsedListing] = []
    seen: set[str] = set()
    candidates = soup.select("article, .property-item, .listing-item, .views-row, li")
    for container in candidates:
        text = _clean(container.get_text(" ", strip=True))
        if not any(term in text.lower() for term in ("current bid", "starting bid", "now bidding")):
            continue
        link = container.find("a", href=True)
        url = urljoin(base_url, link["href"]) if link else base_url
        address_match = ADDRESS_RE.search(text)
        external_id = hashlib.sha256(url.encode()).hexdigest()[:20]
        if external_id in seen:
            continue
        seen.add(external_id)
        title = _clean(link.get_text(" ", strip=True)) if link else text[:180]
        records.append(
            ParsedListing(
                external_id=external_id,
                title=title[:300],
                description=text[:4000],
                source_url=url,
                address=address_match.group("address") if address_match else "",
                city=address_match.group("city") if address_match else "",
                state=address_match.group("state") if address_match else "",
                postal_code=address_match.group("zip") if address_match else "",
                property_type=_property_type(text),
                current_bid=_money(text),
                contact_name="GSA Realty Specialist (see official listing)",
                how_to_buy=[
                    "Open the official GSA listing and review Invitation for Bids and sale documents.",
                    "Sign in or register using Login.gov.",
                    "Register for the specific property and submit the required bid deposit.",
                    "Place the bid only in the GSA Real Estate Sales system.",
                ],
                due_diligence=STANDARD_DUE_DILIGENCE,
                raw_data={"parser": "gsa_html_v1"},
            )
        )
    return records


GOVDEALS_HOW_TO_BUY = [
    "Open the official GovDeals lot and read seller instructions and all attachments.",
    "Register and complete bidder verification on GovDeals.",
    "Confirm buyer premium, payment deadline, deed type, and closing procedure.",
    "Pay only through the methods specified on the authenticated lot page.",
]

# "Closes: 2d 4h (September 8, 2026 4:41 PM UTC)" — the absolute time in the
# parenthetical is stable; the countdown beside it changes every few seconds.
GOVDEALS_CLOSE_RE = re.compile(
    r"\(([A-Za-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)\s*UTC\)", re.I
)


def parse_govdeals(html: str, base_url: str) -> list[ParsedListing]:
    """Parse the GovDeals SEO listing grid.

    Values live in title="" attributes rather than element text, because the
    visible text is formatted for display ("USD 17,888.00") or is a live
    countdown. The previous implementation searched for a "Lot#:" text node,
    which never matches — the label and the value sit in sibling spans — so
    this source produced zero records.
    """
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    records: list[ParsedListing] = []
    seen: set[str] = set()

    # Category is a page-level heading, not a per-card field.
    heading = soup.find("h1")
    category = _clean(heading.get_text(" ", strip=True)) if heading else ""

    for card in soup.select('div[id^="asset-"]'):
        lot_id = card.get("id", "").removeprefix("asset-")
        if not lot_id or lot_id in seen:
            continue
        link = card.select_one('p.card-title a[name="lnkAssetDetails"]')
        if link is None or not link.get("href"):
            continue
        seen.add(lot_id)

        city, state = _govdeals_location(card)
        records.append(
            ParsedListing(
                external_id=lot_id,
                title=_clean(link.get("title") or link.get_text(" ", strip=True))[:300],
                display_title=_display_title("", city, state, category or "Property"),
                source_url=urljoin("https://www.govdeals.com/", link["href"].lstrip("/")),
                city=city,
                state=state,
                property_type=_property_type(category),
                current_bid=_govdeals_bid(card),
                auction_end=_govdeals_close(card),
                how_to_buy=GOVDEALS_HOW_TO_BUY,
                due_diligence=STANDARD_DUE_DILIGENCE,
                raw_data={"parser": "govdeals_html_v2", "category": category},
            )
        )
    return records


def _govdeals_location(card) -> tuple[str, str]:
    """"Harrisburg, Illinois" -> ("Harrisburg", "IL"). Non-US lots yield no state."""
    node = card.select_one('p[name="pAssetLocation"]')
    raw = (node.get("title") if node else "") or (node.get_text(" ", strip=True) if node else "")
    parts = [part.strip() for part in _clean(raw).split(",") if part.strip()]
    if not parts:
        return "", ""
    city = parts[0][:120]
    return city, _state_code(parts[1]) if len(parts) > 1 else ""


def _govdeals_bid(card) -> Decimal | None:
    """The title attribute holds the raw number; the text is "USD 17,888.00"."""
    node = card.select_one('p[name="pAssetCurrentBid"]')
    raw = (node.get("title") if node else "") or ""
    try:
        return Decimal(raw.replace(",", "").strip()) if raw.strip() else None
    except (ArithmeticError, ValueError):
        return None


def _govdeals_close(card) -> datetime | None:
    timer = card.select_one("app-ux-timer")
    if timer is None:
        return None
    match = GOVDEALS_CLOSE_RE.search(timer.get_text(" ", strip=True))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%B %d, %Y %I:%M %p").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


STANDARD_DUE_DILIGENCE = [
    "Confirm the legal description, parcel number, and seller's interest—not only the street address.",
    "Order a title search and identify taxes, liens, easements, code cases, and redemption rights.",
    "Verify occupancy; do not enter or contact occupants without authorization.",
    "Inspect structure, utilities, environmental risk, zoning, and repair scope where access is allowed.",
    "Confirm deposit, buyer premium, funding proof, closing deadline, and accepted payment method.",
    "Have an Illinois real-estate/tax-sale attorney review any lien or deed strategy.",
]

PARSERS = {"treasury": parse_treasury, "gsa": parse_gsa, "govdeals": parse_govdeals}


def _fallback_treasury(html: str, base_url: str) -> list[ParsedListing]:
    """Conservative stdlib-only fallback used only when BeautifulSoup is unavailable."""
    plain = re.sub(r"<[^>]+>", " ", html)
    plain = _clean(plain)
    records = []
    seen: set[str] = set()
    for match in re.finditer(r"Sale\s*#\s*([\w-]+)", plain, re.I):
        sale_id = match.group(1)
        if sale_id in seen:
            continue
        seen.add(sale_id)
        start = max(0, match.start() - 450)
        end = min(len(plain), match.end() + 250)
        text = plain[start:end]
        address_match = ADDRESS_RE.search(text)
        records.append(
            ParsedListing(
                external_id=sale_id,
                title=text[:220],
                description=text,
                source_url=base_url,
                address=address_match.group("address") if address_match else "",
                city=address_match.group("city") if address_match else "",
                state=address_match.group("state") if address_match else "",
                postal_code=address_match.group("zip") if address_match else "",
                property_type=_property_type(text),
                how_to_buy=["Open the official Treasury property page and follow its Terms of Sale."],
                due_diligence=STANDARD_DUE_DILIGENCE,
                raw_data={"parser": "treasury_fallback_v1"},
            )
        )
    return records


def fetch_source(source: SourceDefinition, etag: str = "") -> FetchResult:
    settings = get_settings()
    headers = {
        "User-Agent": "DealSigBot/0.1 (+https://dealsig.ai/data-sources; public-listing monitor)",
        "Accept": "text/html,application/xhtml+xml",
    }
    if etag:
        headers["If-None-Match"] = etag
    with httpx.Client(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = client.get(source.url)
    if response.status_code == 304:
        return FetchResult(records=[], content_hash="", etag=etag, not_modified=True)
    response.raise_for_status()
    content_hash = hashlib.sha256(response.content).hexdigest()
    parser = PARSERS.get(source.slug)
    records = parser(response.text, str(response.url)) if parser else []
    return FetchResult(records=records, content_hash=content_hash, etag=response.headers.get("etag", ""))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
