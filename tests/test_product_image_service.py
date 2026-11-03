import asyncio

from app.services import product_image_service as img


def test_title_must_contain_brand_and_most_of_the_name():
    assert img.title_matches("Amazon.com: Minimalist Salicylic Acid Face Wash 100ml", "Salicylic Acid Face Wash", "Minimalist")
    assert not img.title_matches("Salicylic Acid Face Wash", "Salicylic Acid Face Wash", "Minimalist")  # no brand
    assert not img.title_matches("Minimalist Vitamin C Serum", "Salicylic Acid Face Wash", "Minimalist")  # other product
    assert not img.title_matches("anything", "Wash", "")  # no brand to check against


def test_only_https_and_no_pinterest():
    assert img.usable_url("https://m.media-amazon.com/x.jpg")
    assert img.usable_url("http://shop.example/x.jpg") is None
    assert img.usable_url("https://i.pinimg.com/originals/x.jpg") is None
    assert img.usable_url("https://" + "a" * 2000) is None
    assert img.usable_url(None) is None


def test_best_searxng_image_skips_listicles_and_takes_the_first_match():
    results = [
        {"title": "7 Best Salicylic Acid Face Washes In India", "img_src": "https://blog.example/list.jpg"},
        {"title": "Minimalist Salicylic Acid Face Wash", "img_src": "http://insecure.example/x.jpg"},
        {"title": "Minimalist 2% Salicylic Acid Face Wash", "img_src": "https://shop.example/good.jpg"},
        {"title": "Minimalist Salicylic Acid Face Wash", "img_src": "https://shop.example/second.jpg"},
    ]
    assert img.best_searxng_image(results, "Salicylic Acid Face Wash", "Minimalist") == "https://shop.example/good.jpg"


def test_open_facts_first_searxng_only_as_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(img.settings, "SEARXNG_URL", "http://searxng:8080")
    monkeypatch.setattr(img, "_from_open_facts", lambda n, b, c: calls.append("off") or None)
    monkeypatch.setattr(img, "_from_searxng", lambda n, b, s: calls.append("sx") or "https://sx.example/a.jpg")
    assert asyncio.run(img.find_image("Wash", "Acme")) == "https://sx.example/a.jpg" and calls == ["off", "sx"]

    calls.clear()
    monkeypatch.setattr(img, "_from_open_facts", lambda n, b, c: calls.append("off") or "https://off.example/a.jpg")
    assert asyncio.run(img.find_image("Wash", "Acme")) == "https://off.example/a.jpg" and calls == ["off"]


def test_failures_mean_no_image_never_an_error(monkeypatch):
    def boom(*_):
        raise TimeoutError()

    monkeypatch.setattr(img.settings, "SEARXNG_URL", "http://searxng:8080")
    monkeypatch.setattr(img, "_from_open_facts", boom)
    monkeypatch.setattr(img, "_from_searxng", boom)
    assert asyncio.run(img.find_image("Wash", "Acme")) is None


def test_no_searxng_configured_means_open_facts_only(monkeypatch):
    calls = []
    monkeypatch.setattr(img.settings, "SEARXNG_URL", None)
    monkeypatch.setattr(img, "_from_open_facts", lambda n, b, c: calls.append("off") or None)
    monkeypatch.setattr(img, "_from_searxng", lambda n, b, s: calls.append("sx") or "x")
    assert asyncio.run(img.find_image("Wash", "Acme")) is None and calls == ["off"]
