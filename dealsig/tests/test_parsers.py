"""Parser tests built from the real DOM shapes of each source.

Fixtures mirror the live markup exactly where it matters, including the parts
that broke the previous parsers: Treasury's unclosed <tr> tags and its label
split across <b>/<strong>, and GovDeals putting values in title attributes.
"""

from datetime import timezone
from decimal import Decimal

from app.services.sources import parse_govdeals, parse_treasury

# Note the missing </tr>, the split "ONLINE AUCTION DAT|E:" label, the full
# state name, and the stale copy-paste anchor — all present on the live page.
TREASURY_HTML = """
<table>
<tr><td>
  <p class="style1"><b>SINGLE FAMILY HOME</b>: 5645 Whitner Drive, Atlanta, Georgia 30327
  <b>ONLINE AUCTION DAT</b><strong>E: </strong>Thursday, August 20, 2026</p>
  <span class="style11">7,012 sq ft home with 4 bedrooms. Sale # 26-66-885.</span>
  <a href="112bruni.shtml">stale link to a different property</a>
</td>
<td><a href="5645whitner.shtml"><img src="images/5645whitner1.gif" alt="5645 Whitner Drive, Atlanta, Georgia 30327"></a></td>
<tr><td>
  <p class="style1"><b>RURAL LAND</b>: 48 Tumbleweed Trail, Penrose, Colorado 81240
  <b>ONLINE AUCTION DAT</b><strong>E: </strong>COMING SOON</p>
  <span class="style11">2.64 acres of rural land. Sale # 26-66-878.</span>
  <a href="112bruni.shtml">stale link again</a>
</td>
<td><img src="images/266moore1.gif" alt="48 Tumbleweed Trail, Penrose, Colorado 81240"></td>
</table>
"""

GOVDEALS_HTML = """
<h1>Single Family Property - Residential</h1>
<div id="asset-25752-190">
  <p class="card-title"><a name="lnkAssetDetails" href="/en/asset/190/25752"
     title="Affordable 2-Bed Fixer in Harrisburg IL">Affordable 2-Bed Fixer...</a></p>
  <p name="pAssetLocation" title="Harrisburg, Illinois">Harrisburg, Illinois</p>
  <p name="pAssetCurrentBid" title="17888">USD 17,888.00</p>
  <app-ux-timer>2d 4h (September 8, 2026 4:41 PM UTC)</app-ux-timer>
</div>
<div id="asset-99001-190">
  <p class="card-title"><a name="lnkAssetDetails" href="/en/asset/190/99001"
     title="Beach lot">Beach lot</a></p>
  <p name="pAssetLocation" title="Punta Cana, La Altagracia">Punta Cana, La Altagracia</p>
  <p name="pAssetCurrentBid" title="">USD 0.00</p>
  <app-ux-timer>counting down</app-ux-timer>
</div>
"""

BASE = "https://www.treasury.gov/auctions/treasury/rp/realprop.shtml"


def treasury_records():
    return {r.external_id: r for r in parse_treasury(TREASURY_HTML, BASE)}


def test_treasury_finds_records_despite_unclosed_tr_tags():
    assert set(treasury_records()) == {"26-66-885", "26-66-878"}


def test_treasury_extracts_address_with_a_full_state_name():
    """The old ADDRESS_RE required "GA"; Treasury writes "Georgia", so it got 0/21."""
    r = treasury_records()["26-66-885"]
    assert r.address == "5645 Whitner Drive"
    assert r.city == "Atlanta"
    assert r.state == "GA", "must be the 2-letter code — Listing.state is String(2)"
    assert r.postal_code == "30327"


def test_treasury_parses_the_auction_date():
    r = treasury_records()["26-66-885"]
    assert r.auction_end is not None
    assert (r.auction_end.year, r.auction_end.month, r.auction_end.day) == (2026, 8, 20)
    assert r.auction_end.tzinfo is timezone.utc


def test_treasury_tolerates_coming_soon_instead_of_a_date():
    assert treasury_records()["26-66-878"].auction_end is None


def test_treasury_links_to_the_property_not_the_index():
    r = treasury_records()["26-66-885"]
    assert r.source_url.endswith("/5645whitner.shtml")
    assert r.source_url != BASE


def test_treasury_rejects_a_stale_anchor_rather_than_linking_the_wrong_property():
    """Both cards carry a 112bruni.shtml anchor. Guessing sends users to the
    wrong house, which is worse than sending them nowhere."""
    r = treasury_records()["26-66-878"]
    assert r.source_url == ""
    assert "bruni" not in r.source_url


def test_treasury_never_falls_back_to_the_index_url():
    assert all(r.source_url != BASE for r in treasury_records().values())


def test_treasury_extracts_image_and_readable_title():
    r = treasury_records()["26-66-885"]
    assert r.image_url.endswith("/images/5645whitner1.gif")
    assert r.display_title == "5645 Whitner Drive, Atlanta, GA"
    assert r.property_type == "single_family"


def govdeals_records():
    return {r.external_id: r for r in parse_govdeals(GOVDEALS_HTML, "https://prod-seo.govdeals.com/")}


def test_govdeals_returns_records_at_all():
    """The shipped parser searched for a "Lot#:" text node and found zero."""
    assert set(govdeals_records()) == {"25752-190", "99001-190"}


def test_govdeals_reads_values_from_title_attributes():
    r = govdeals_records()["25752-190"]
    assert r.title == "Affordable 2-Bed Fixer in Harrisburg IL"
    assert r.city == "Harrisburg"
    assert r.state == "IL"
    assert r.current_bid == Decimal("17888")


def test_govdeals_parses_the_absolute_close_time_not_the_countdown():
    r = govdeals_records()["25752-190"]
    assert r.auction_end is not None
    assert (r.auction_end.year, r.auction_end.month, r.auction_end.day) == (2026, 9, 8)
    assert r.auction_end.hour == 16


def test_govdeals_links_to_the_public_lot_page():
    assert govdeals_records()["25752-190"].source_url == "https://www.govdeals.com/en/asset/190/25752"


def test_govdeals_leaves_state_empty_for_a_non_us_lot():
    """"La Altagracia" is a Dominican province, not a US state."""
    r = govdeals_records()["99001-190"]
    assert r.city == "Punta Cana"
    assert r.state == ""


def test_govdeals_handles_missing_bid_and_unparseable_timer():
    r = govdeals_records()["99001-190"]
    assert r.current_bid is None
    assert r.auction_end is None


def test_govdeals_uses_the_page_category_for_property_type():
    assert govdeals_records()["25752-190"].property_type == "single_family"
