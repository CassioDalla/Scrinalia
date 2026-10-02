from domains.archive.worker_stamp import NER, WorkerStamp, cleaning_rule_stamp


def test_stamp_applies_to_only_when_key_is_absent() -> None:
    assert NER.applies_to(None) is True
    assert NER.applies_to({}) is True
    assert NER.applies_to({"other": "DONE"}) is True
    assert NER.applies_to({NER.key: "DONE"}) is False


def test_mark_returns_new_dict_without_mutating_input() -> None:
    original = {"existing": "DONE"}
    marked = NER.mark(original)

    assert marked == {"existing": "DONE", NER.key: "DONE"}
    assert original == {"existing": "DONE"}  # original untouched


def test_mark_can_override_status() -> None:
    assert NER.mark(None, status="ERROR")[NER.key] == "ERROR"


def test_mark_handles_none_log() -> None:
    assert NER.mark(None) == {NER.key: "DONE"}


def test_cleaning_rule_stamp_is_per_rule() -> None:
    assert cleaning_rule_stamp(7).key == "cleaning_rule_7"
    assert cleaning_rule_stamp(7) != cleaning_rule_stamp(8)
    assert isinstance(cleaning_rule_stamp(1), WorkerStamp)
