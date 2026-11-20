from datetime import datetime, timezone

from app.adapters import jtl_archive

AT = datetime(2021, 9, 26, tzinfo=timezone.utc)

EVO = """<div id="result-wrapper_buy_form_12046" class="product-cell"><div class="caption">
<h4 class="title" itemprop="name"><a href="Hoya-albomarginata-variegata-M">Hoya albomarginata variegata M</a></h4>
<div class="price_wrapper"><strong class="price text-nowrap"> <span>5,90 &#8364;</span></strong></div></div>
<div class="delivery-status"><div class="signal_image status-2"><small>sofort verf\xfcgbar</small></div></div>
<input type="hidden" name="a" value="12046"></div>
<div id="result-wrapper_buy_form_11366" class="product-cell"><h4 class="title"><a href="x">Hoya carnosa L</a></h4>
<strong class="price"><span>14,90 &#8364;</span></strong><div class="signal_image status-0"></div></div>
<div id="result-wrapper_buy_form_9" class="product-cell"><h4 class="title"><a href="y">Dischidia major</a></h4>
<strong class="price"><span>9,90 &#8364;</span></strong></div>"""

PRODUCT = """<h1 class="fn product-title">Hoya carnosa wayetti green</h1>
<input type="hidden" id="AktuellerkArtikel" class="current_article" name="a" value="11922">
<span itemprop="sku">BJ1944</span><meta itemprop="price" content="14.9">
<div class="signal_image status-0"><small>item not available</small></div><p>Bewurzelt im 12cm Topf</p>"""


def test_evo_category():
    offers = jtl_archive.parse_archived(EVO, "https://bens-jungle.com/Hoya_1", "category", AT)
    assert [(o["item_key"], o["price"], o["availability"]) for o in offers] == [
        ("12046", 5.9, "available"), ("11366", 14.9, "sold_out")]


def test_product_page():
    [o] = jtl_archive.parse_archived(PRODUCT, "https://bens-jungle.com/Hoya-carnosa-wayetti-green", "product", AT)
    assert (o["item_key"], o["name"], o["price"], o["availability"], o["pot"], o["sku"]) == (
        "11922", "Hoya carnosa wayetti green", 14.9, "sold_out", "12 cm", "BJ1944")
