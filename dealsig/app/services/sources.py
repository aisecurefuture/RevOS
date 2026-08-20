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
        "https://prod-seo.govdeals.com/en/single-family-property-residential",
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


def parse_treasury(html: str, base_url: str) -> list[ParsedListing]:
    if BeautifulSoup is None:
        return _fallback_treasury(html, base_url)
    soup = BeautifulSoup(html, "html.parser")
    records: list[ParsedListing] = []
    seen: set[str] = set()
    for node in soup.find_all(string=re.compile(r"Sale\s*#\s*[\w-]+", re.I)):
        sale_match = re.search(r"Sale\s*#\s*([\w-]+)", str(node), re.I)
        if not sale_match or sale_match.group(1) in seen:
            continue
        sale_id = sale_match.group(1)
        seen.add(sale_id)
        container = node.find_parent(["tr", "article", "div", "p"]) or node.parent
        text = _clean(container.get_text(" ", strip=True)) if container else _clean(str(node))
        parent_link = container.find("a", href=True) if container else None
        address_match = ADDRESS_RE.search(text)
        title = text.split("Sale #", 1)[0].strip(" -:")[:300] or f"Treasury sale {sale_id}"
        records.append(
            ParsedListing(
                external_id=sale_id,
                title=title,
                description=text[:4000],
                source_url=urljoin(base_url, parent_link["href"]) if parent_link else base_url,
                address=address_match.group("address") if address_match else "",
                city=address_match.group("city") if address_match else "",
                state=address_match.group("state") if address_match else "",
                postal_code=address_match.group("zip") if address_match else "",
                property_type=_property_type(text),
                how_to_buy=[
                    "Open the official property detail and read the complete Terms of Sale.",
                    "Create an account with the named Treasury auction contractor.",
                    "Register for the specific sale and fund the required deposit exactly as instructed.",
                    "Inspect the property and complete title, lien, occupancy, and repair diligence before bidding.",
                ],
                due_diligence=STANDARD_DUE_DILIGENCE,
                raw_data={"parser": "treasury_html_v1"},
            )
        )
    return records


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


def parse_govdeals(html: str, base_url: str) -> list[ParsedListing]:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    records: list[ParsedListing] = []
    seen: set[str] = set()
    for node in soup.find_all(string=re.compile(r"Lot\s*#?\s*:\s*[\w-]+", re.I)):
        lot_match = re.search(r"Lot\s*#?\s*:\s*([\w-]+)", str(node), re.I)
        if not lot_match or lot_match.group(1) in seen:
            continue
        lot_id = lot_match.group(1)
        seen.add(lot_id)
        container = node.find_parent(["article", "li", "div"]) or node.parent
        text = _clean(container.get_text(" ", strip=True)) if container else _clean(str(node))
        link = container.find("a", href=True) if container else None
        url = urljoin(base_url, link["href"]) if link else base_url
        address_match = ADDRESS_RE.search(text)
        title_node = container.find(["h2", "h3", "h4"]) if container else None
        title = _clean(title_node.get_text(" ", strip=True)) if title_node else text[:200]
        records.append(
            ParsedListing(
                external_id=lot_id,
                title=title[:300],
                description=text[:4000],
                source_url=url,
                address=address_match.group("address") if address_match else "",
                city=address_match.group("city") if address_match else "",
                state=address_match.group("state") if address_match else "",
                postal_code=address_match.group("zip") if address_match else "",
                property_type=_property_type(text),
                current_bid=_money(text),
                how_to_buy=[
                    "Open the official GovDeals lot and read seller instructions and all attachments.",
                    "Register and complete bidder verification on GovDeals.",
                    "Confirm buyer premium, payment deadline, deed type, and closing procedure.",
                    "Pay only through the methods specified on the authenticated lot page.",
                ],
                due_diligence=STANDARD_DUE_DILIGENCE,
                raw_data={"parser": "govdeals_html_v1"},
            )
        )
    return records


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
