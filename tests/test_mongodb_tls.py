from app.db.mongodb import tls_options


def test_atlas_srv_url_gets_ca_bundle():
    assert "tlsCAFile" in tls_options("mongodb+srv://user:pw@cluster.example.mongodb.net/?appName=x")


def test_explicit_tls_flag_gets_ca_bundle():
    assert "tlsCAFile" in tls_options("mongodb://host:27017/db?tls=true")


def test_plain_local_mongo_gets_no_tls_options():
    # Regression: docker-compose uses mongodb://mongo:27017 and failed with an SSL handshake error.
    assert tls_options("mongodb://mongo:27017/scanrix") == {}
