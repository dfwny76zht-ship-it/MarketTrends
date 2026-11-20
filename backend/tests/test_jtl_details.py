from app.adapters import jtl_details

PAGE = """<html><body><div class="ribbon ribbon-2 productbox-ribbon"> Sale 20% </div>
<h1>Hoya Kanyakumariana</h1><span itemprop="sku">BJ3485</span>
<div class="delivery-status"><span class="status">Sofort verfügbar</span></div>
<span>Lieferzeit:</span> <span>3 - 5 Werktage</span>
<p>Growlight 60cm im Shop. Herkunft: Südindien Größe: Bewurzelte Pflanze im 5cm Topf. Licht: hell</p>
<h2>Kunden kauften dazu folgende Artikel:</h2>
<div class="productbox"><div class="productbox-title"><a href="x">Hoya imbricata</a></div>
<meta itemprop="price" content="7.45"><input type="hidden" name="a" value="11902"></div>
</body></html>"""


def test_details():
    d = jtl_details.parse_details(PAGE)
    assert d["sku"] == "BJ3485"
    assert d["pot_size"] == "5 cm"          # from the size line, not the 60 cm lamp
    assert d["delivery"] == "3 - 5 Werktage"
    assert d["availability_text"] == "Sofort verfügbar"
    assert d["discount_pct"] == 20
    assert d["also_bought"] == ["11902"]
