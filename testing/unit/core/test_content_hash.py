from scrinalia.core.content_hash import ContentHash


def test_is_a_64_char_hex_string() -> None:
    digest = ContentHash.of({"title": "Ofício"})

    assert isinstance(digest, str)
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)


def test_is_independent_of_key_order() -> None:
    assert ContentHash.of({"b": 2, "a": 1}) == ContentHash.of({"a": 1, "b": 2})


def test_changes_when_payload_changes() -> None:
    assert ContentHash.of({"title": "A"}) != ContentHash.of({"title": "B"})
