"""An identity-keyed slot takes a producer fingerprint, and a worker cannot write a status into it.

Issue #137: ``ArchiveDocument.execution_log["worker_ner_v2"]`` held ``"DONE"`` — a legal
``StampStatus`` — in 1,650 rows, so no reader could tell an attributed document from one whose run
nobody recorded the producer of. The vocabulary is the first half of the fix
(``IdentityStamp.mark_value`` raises ``ValueError`` for a status, and there is no ``mark`` to call).
This is the second half, and it catches the path the vocabulary cannot: a worker that bypasses the
API and writes the JSONB directly, which compiles, runs, and would only show up in a report.

The scope is the worker modules, because that is where a slot is written. A fixture that sows a
legacy ``"DONE"`` on purpose (``test_text_quality_repo.py`` does) is data, not a write path.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scrinalia.domains.archive import worker_stamp
from scrinalia.domains.archive.worker_stamp import PRODUCER_UNKNOWN, STAMP_STATUS_VALUES, IdentityStamp

REPO_ROOT = Path(__file__).resolve().parents[3]

WORKERS_DIR = REPO_ROOT / "src/scrinalia/domains/archive/workers"

#: The module-level names that are an identity-keyed slot, read from the module itself: the gate does
#: not keep a second list of stamps to forget. ``test_the_gate_knows_every_identity_stamp`` pins the
#: set, so adding one is deliberate.
IDENTITY_STAMP_NAMES = frozenset(name for name, value in vars(worker_stamp).items() if isinstance(value, IdentityStamp))

#: What must never reach an identity slot. ``ERROR`` is in the set on purpose: a failure has its own
#: writer (``mark_failed``), and a status standing where an identity belongs is the defect.
FORBIDDEN_IDENTITY_VALUES = STAMP_STATUS_VALUES | {PRODUCER_UNKNOWN}

#: The identity-keyed stamps the vocabulary holds today; ``test_the_gate_knows_every_identity_stamp``
#: compares against it, so adding one is an edit here and not a slot that silently escapes the scan.
EXPECTED_IDENTITY_STAMPS = frozenset({"EMBEDDING", "MACRO_CATEGORY", "NER", "QUALITY_VALIDATOR", "TYPOLOGY"})


def _worker_files() -> list[Path]:
    """Every worker module, caches excluded."""
    return [path for path in sorted(WORKERS_DIR.glob("*.py")) if "__pycache__" not in path.parts]


def _is_identity_stamp(name: str) -> bool:
    return name in IDENTITY_STAMP_NAMES


def _stamp_of_attribute(node: ast.Attribute) -> str | None:
    """``NER`` in ``NER.mark_value(...)``, or ``None`` when the attribute is anything else."""
    if isinstance(node.value, ast.Name) and _is_identity_stamp(node.value.id):
        return node.value.id
    return None


def _stamp_of_key_slice(node: ast.AST) -> str | None:
    """``NER`` in the ``execution_log[NER.key]`` target of an assignment, or ``None``."""
    if not isinstance(node, ast.Subscript):
        return None
    subscript = node.slice
    if (
        isinstance(subscript, ast.Attribute)
        and subscript.attr == "key"
        and isinstance(subscript.value, ast.Name)
        and _is_identity_stamp(subscript.value.id)
    ):
        return subscript.value.id
    return None


def _forbidden_writes(tree: ast.AST) -> list[tuple[int, str]]:
    """Every write of a status into an identity slot, as ``(line, what it is)``."""
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            stamp_name = _stamp_of_attribute(node.func)
            if stamp_name is None:
                continue
            if node.func.attr == "mark":
                findings.append((node.lineno, f"{stamp_name}.mark(...) writes a status into an identity slot"))
            elif node.func.attr == "mark_value" and len(node.args) >= 2:
                value = node.args[1]
                if isinstance(value, ast.Constant) and value.value in FORBIDDEN_IDENTITY_VALUES:
                    findings.append(
                        (
                            node.lineno,
                            f"{stamp_name}.mark_value(..., {value.value!r}) writes a status, not a fingerprint",
                        )
                    )
        if isinstance(node, ast.Assign):
            assigned = node.value
            if not (isinstance(assigned, ast.Constant) and assigned.value in FORBIDDEN_IDENTITY_VALUES):
                continue
            for target in node.targets:
                stamp_name = _stamp_of_key_slice(target)
                if stamp_name is not None:
                    findings.append(
                        (node.lineno, f"execution_log[{stamp_name}.key] = {assigned.value!r} bypasses mark_value")
                    )
    return sorted(findings)


def test_the_gate_knows_every_identity_stamp() -> None:
    """A slot added to the vocabulary must be scanned here too, and pinning the set makes that fail."""
    assert IDENTITY_STAMP_NAMES == EXPECTED_IDENTITY_STAMPS


def test_no_worker_writes_a_status_into_an_identity_slot() -> None:
    findings = [
        f"{path.relative_to(REPO_ROOT)}:{line}: {message}"
        for path in _worker_files()
        for line, message in _forbidden_writes(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    ]

    assert not findings, "An identity-keyed stamp takes a producer fingerprint and nothing else:\n" + "\n".join(
        findings
    )


def test_the_scan_would_catch_a_status_write() -> None:
    """A gate that cannot fail is not a gate: the scanner is run over a snippet that does."""
    snippet = (
        'doc.execution_log = NER.mark_value(doc.execution_log, "DONE")\n'
        'doc.execution_log[MACRO_CATEGORY.key] = "True"\n'
        "doc.execution_log = NER.mark_failed(doc.execution_log)\n"
        "doc.execution_log = NER.mark_value(doc.execution_log, identity)\n"
    )

    findings = _forbidden_writes(ast.parse(snippet))

    assert [message for _line, message in findings] == [
        "NER.mark_value(..., 'DONE') writes a status, not a fingerprint",
        "execution_log[MACRO_CATEGORY.key] = 'True' bypasses mark_value",
    ]
