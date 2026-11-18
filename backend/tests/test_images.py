"""Offer photos: storing, thumbnails, which listings are due."""

import io

from PIL import Image


def _png(color=(30, 120, 60), size=(800, 600)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_store_and_due(db, tmp_path, monkeypatch):
    from app import config, images

    monkeypatch.setattr(config, "SNAPSHOT_DIR", str(tmp_path))
    with db.connection() as conn:
        shop = conn.execute(
            "INSERT INTO shops (name, url, host) VALUES ('Pics', 'https://p.example/', 'p.example') RETURNING id"
        ).fetchone()["id"]
        lid = conn.execute(
            "INSERT INTO listings (shop_id, item_key, name, image_url, first_seen, last_seen)"
            " VALUES (%s, 'a', 'Hoya x', 'https://p.example/a.png', now(), now()) RETURNING id",
            (shop,),
        ).fetchone()["id"]
        assert [r["id"] for r in conn.execute(images.DUE_SQL, (shop, 3, 10))] == [lid]

    info = images.store(shop, _png())
    assert (tmp_path / info["path"]).is_file()
    thumb = Image.open(tmp_path / info["thumb_path"])
    assert thumb.format == "WEBP" and max(thumb.size) <= 240
    assert (info["width"], info["height"]) == (800, 600)
    images._record(lid, "https://p.example/a.png", "ok", **info)
    with db.connection() as conn:
        assert not conn.execute(images.DUE_SQL, (shop, 3, 10)).fetchall()
        # A new photo address makes it due again.
        conn.execute("UPDATE listings SET image_url = 'https://p.example/b.png' WHERE id = %s", (lid,))
        assert conn.execute(images.DUE_SQL, (shop, 3, 10)).fetchall()

    try:
        images.store(shop, b"<html>not a picture</html>")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
