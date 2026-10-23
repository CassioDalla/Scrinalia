"""The stamp as a ledger slot: presence, a status or a short value, and the erase.

The identity-keyed half of the vocabulary — what a slot that names its producer accepts, and what it
refuses — lives in ``test_worker_stamp_identity.py``, next to the producer fingerprint itself.
"""

from scrinalia.domains.archive.worker_stamp import (
    THUMBNAIL_FAILED,
    WorkerStamp,
    cleaning_rule_stamp,
)


def test_stamp_applies_to_only_when_key_is_absent() -> None:
    assert THUMBNAIL_FAILED.applies_to(None) is True
    assert THUMBNAIL_FAILED.applies_to({}) is True
    assert THUMBNAIL_FAILED.applies_to({"other": "DONE"}) is True
    assert THUMBNAIL_FAILED.applies_to({THUMBNAIL_FAILED.key: "ERROR"}) is False


def test_mark_returns_new_dict_without_mutating_input() -> None:
    original = {"existing": "DONE"}
    marked = THUMBNAIL_FAILED.mark(original)

    assert marked == {"existing": "DONE", THUMBNAIL_FAILED.key: "ERROR"}
    assert original == {"existing": "DONE"}  # original untouched


def test_mark_can_override_status() -> None:
    """The default is ``ERROR``; an explicit ``DONE`` proves the override is not ignored."""
    assert THUMBNAIL_FAILED.mark(None, status="DONE")[THUMBNAIL_FAILED.key] == "DONE"


def test_mark_handles_none_log() -> None:
    assert THUMBNAIL_FAILED.mark(None) == {THUMBNAIL_FAILED.key: "ERROR"}


def test_a_status_stamp_can_write_free_text_and_erase_it() -> None:
    """``mark_value`` stays on the status stamp for the ledgers that hold a short free text."""
    marked = THUMBNAIL_FAILED.mark_value(None, "quem-quando")

    assert marked == {THUMBNAIL_FAILED.key: "quem-quando"}
    assert THUMBNAIL_FAILED.clear(marked) == {}


def test_cleaning_rule_stamp_is_per_rule() -> None:
    assert cleaning_rule_stamp(7).key == "cleaning_rule_7"
    assert cleaning_rule_stamp(7) != cleaning_rule_stamp(8)
    assert isinstance(cleaning_rule_stamp(1), WorkerStamp)
