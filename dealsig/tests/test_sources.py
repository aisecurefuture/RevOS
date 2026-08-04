from app.services.sources import parse_treasury


def test_treasury_parser_deduplicates_sale_numbers():
    html = """
    <div><a href="/sale-one">SINGLE FAMILY HOME: 123 Main Street, Joliet, IL 60431</a>
    Sale # 26-66-100</div>
    <p>Sale # 26-66-100</p>
    """
    records = parse_treasury(html, "https://www.treasury.gov/auctions/example")
    assert len(records) == 1
    assert records[0].external_id == "26-66-100"
    assert records[0].instrument_type == "direct_sale"

