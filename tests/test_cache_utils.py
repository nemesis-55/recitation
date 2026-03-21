from app.utils.cache_utils import read_cache_bytes, write_cache_bytes


def test_cache_bytes_roundtrip():
    key = "unit_test_bytes_key"
    payload = b"hello-cache"
    write_cache_bytes("unit_test_cache", key, payload)
    assert read_cache_bytes("unit_test_cache", key) == payload
