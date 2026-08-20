from app.services.sources import parse_treasury

# Two cards carrying the SAME Sale #, in the page's real structure: p.style1
# inside a <td>, with the auction-date label split across <b>/<strong>.
DUPLICATE_SALE_HTML = """
<table>
<tr><td>
  <p class="style1"><b>SINGLE FAMILY HOME</b>: 123 Main Street, Joliet, Illinois 60431
  <b>ONLINE AUCTION DAT</b><strong>E: </strong>Thursday, August 20, 2026</p>
  <span class="style11">First appearance. Sale # 26-66-100.</span>
</td>
<td><img src="images/123main1.gif" alt="123 Main Street, Joliet, Illinois 60431"></td>
<tr><td>
  <p class="style1"><b>SINGLE FAMILY HOME</b>: 123 Main Street, Joliet, Illinois 60431
  <b>ONLINE AUCTION DAT</b><strong>E: </strong>Thursday, August 20, 2026</p>
  <span class="style11">Repeated further down the page. Sale # 26-66-100.</span>
</td>
<td><img src="images/123main1.gif" alt="123 Main Street, Joliet, Illinois 60431"></td>
</table>
"""


def test_treasury_parser_deduplicates_sale_numbers():
    records = parse_treasury(DUPLICATE_SALE_HTML, "https://www.treasury.gov/auctions/example")
    assert len(records) == 1
    assert records[0].external_id == "26-66-100"
    assert records[0].instrument_type == "direct_sale"


def test_treasury_parser_ignores_markup_that_is_not_a_listing_card():
    """A bare "Sale #" mention outside a p.style1 card must not become a listing."""
    stray = '<div><p>Questions about Sale # 26-66-100 should go to the contractor.</p></div>'
    assert parse_treasury(stray, "https://www.treasury.gov/auctions/example") == []
