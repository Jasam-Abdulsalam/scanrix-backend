import asyncio

import cloudinary.exceptions

from app.services import product_image_mirror as mirror

OFF = "https://images.openbeautyfacts.org/images/products/871/716/399/7345/front_en.20.400.jpg"
CDN = "https://res.cloudinary.com/demo/image/upload/v1/product_images/8717163997345.jpg"


def _configure(monkeypatch, on=True):
    for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        monkeypatch.setattr(mirror.settings, key, "x" if on else None)


def _fake_save(monkeypatch, result=True):
    saved = []

    async def save(barcode, source, url):
        saved.append((barcode, source, url))
        return result

    monkeypatch.setattr(mirror.crud_product, "set_mirrored_image", save)
    return saved


def test_which_urls_get_copied():
    assert mirror.needs_mirror(OFF)
    assert not mirror.needs_mirror(CDN)  # already ours
    assert not mirror.needs_mirror("http://images.example/x.jpg")  # iOS blocks http anyway
    assert not mirror.needs_mirror(None)


def test_public_id_keeps_only_safe_characters():
    assert mirror.public_id_for("8717163997345") == "8717163997345"
    assert mirror.public_id_for("../a b?") == "___a_b_"
    assert mirror.public_id_for("") == "unknown"


def test_copy_saves_the_cloudinary_url_and_keeps_the_original(monkeypatch):
    _configure(monkeypatch)
    saved = _fake_save(monkeypatch)
    monkeypatch.setattr(mirror, "_upload", lambda src, barcode: CDN)
    assert asyncio.run(mirror.mirror_product_image("8717163997345", OFF)) == CDN
    assert saved == [("8717163997345", OFF, CDN)]


def test_failed_copy_keeps_the_original(monkeypatch):
    _configure(monkeypatch)
    saved = _fake_save(monkeypatch)

    def fail(src, barcode):
        raise cloudinary.exceptions.Error("Resource not found")

    monkeypatch.setattr(mirror, "_upload", fail)
    assert asyncio.run(mirror.mirror_product_image("1", OFF)) is None
    assert saved == []


def test_skipped_without_keys_or_when_already_copied(monkeypatch):
    calls = []
    monkeypatch.setattr(mirror, "_upload", lambda src, barcode: calls.append(src) or CDN)
    saved = _fake_save(monkeypatch)
    _configure(monkeypatch, on=False)
    assert asyncio.run(mirror.mirror_product_image("1", OFF)) is None
    _configure(monkeypatch)
    assert asyncio.run(mirror.mirror_product_image("1", CDN)) is None
    assert calls == [] and saved == []


def test_photo_changed_meanwhile_is_not_overwritten(monkeypatch):
    _configure(monkeypatch)
    _fake_save(monkeypatch, result=False)  # the filter on the old image_url matched nothing
    monkeypatch.setattr(mirror, "_upload", lambda src, barcode: CDN)
    assert asyncio.run(mirror.mirror_product_image("1", OFF)) is None
