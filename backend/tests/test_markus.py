"""Edited texts for the investor page are cleaned before Markus sees them."""


def test_clean_keeps_inline_and_drops_the_rest():
    from app.markus import clean

    assert clean('Bei <strong>88 %</strong> der <em>Pflanzen</em>') == "Bei <strong>88 %</strong> der <em>Pflanzen</em>"
    assert clean('<span class="big">90 %</span>der') == '<span class="big">90 %</span>der'
    assert clean('a<script>alert(1)</script>b') == "ab"
    assert clean('<a href="javascript:alert(1)">x</a>') == "<a>x</a>"
    assert clean('<a href="https://example.org/x">x</a>') == '<a href="https://example.org/x" rel="noopener noreferrer">x</a>'
    assert clean('<img src=x onerror=alert(1)>Text') == "Text"
    assert clean("Zeile 1<div>Zeile 2</div>") == "Zeile 1<br>Zeile 2"
    assert clean("a & b < c") == "a &amp; b &lt; c"


def test_save_and_reset(tmp_path, monkeypatch):
    from app import markus

    monkeypatch.setattr(markus, "TEXTS", tmp_path / "texts" / "texts.json")
    assert markus.save_texts(markus.TextsIn(texts={"lead": "Neu <b>fett</b>"})) == {"lead": "Neu <b>fett</b>"}
    assert markus.save_texts(markus.TextsIn(texts={"lead": None, "title": "T"})) == {"title": "T"}
