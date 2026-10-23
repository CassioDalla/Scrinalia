"""An identity-keyed slot takes a producer fingerprint, and a worker cannot write anything else.

Issue #137: ``ArchiveDocument.execution_log["worker_ner_v2"]`` held ``"DONE"`` — a legal
``StampStatus`` — in 1,650 rows, so no reader could tell an attributed document from one whose run
nobody recorded the producer of. The vocabulary is the first half of the fix
(``IdentityStamp.mark_value`` raises ``ValueError`` for a status, and there is no ``mark`` to call).
This is the second half: it catches the path the vocabulary cannot, a worker that bypasses the API
and writes the JSONB directly, which compiles, runs, and would only show up in a report.

Issue #148: the gate used to carry a fixed set of forbidden statuses, so a dict update, a dict
literal or a local alias could write one of them and stay invisible. It now asks the slot's own
``fingerprint_pattern`` whether a constant is a producer at all — the same expression
``mark_value`` validates against — and follows a local alias and a local constant.

The scope is the worker modules, because that is where a slot is written. A fixture that sows a
legacy ``"DONE"`` on purpose (``test_text_quality_repo.py`` does) is data, not a write path.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest

from scrinalia.domains.archive import worker_stamp
from scrinalia.domains.archive.worker_stamp import IdentityStamp

REPO_ROOT = Path(__file__).resolve().parents[3]

WORKERS_DIR = REPO_ROOT / "src/scrinalia/domains/archive/workers"

#: Every identity-keyed stamp and the pattern its slot accepts, read from the module itself: the gate
#: does not keep a second list of stamps, and "is this a fingerprint?" has one definition.
IDENTITY_STAMPS: Mapping[str, IdentityStamp] = {
    name: value for name, value in vars(worker_stamp).items() if isinstance(value, IdentityStamp)
}

#: The names pinned by ``test_the_gate_knows_every_identity_stamp``, so adding one is deliberate.
IDENTITY_STAMP_NAMES = frozenset(IDENTITY_STAMPS)

#: The identity-keyed stamps the vocabulary holds today; adding one is an edit here and in the scan.
EXPECTED_IDENTITY_STAMPS = frozenset({"EMBEDDING", "MACRO_CATEGORY", "NER", "QUALITY_VALIDATOR", "TYPOLOGY"})


def _worker_files() -> list[Path]:
    """Every worker module, caches excluded."""
    return [path for path in sorted(WORKERS_DIR.glob("*.py")) if "__pycache__" not in path.parts]


def _stamp_aliases(tree: ast.AST) -> dict[str, str]:
    """Local names bound to an identity stamp, so ``stamp = NER`` is followed."""
    aliases = {name: name for name in IDENTITY_STAMP_NAMES}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and isinstance(value, ast.Name):
            resolved = aliases.get(value.id)
            if resolved is not None:
                aliases[target.id] = resolved
    return aliases


def _string_constants(tree: ast.AST) -> dict[str, str]:
    """Local names bound to a string constant, so ``value = "DONE"`` is followed.

    A reassignment is not tracked; the gate is a static safety net, not a dataflow analysis, and a
    name whose last assignment in the walk is not the one used at the write is a documented limit.
    """
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and isinstance(value, ast.Constant) and isinstance(value.value, str):
            constants[target.id] = value.value
    return constants


def _stamp_name(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    """The identity stamp a name refers to, following a local alias."""
    if isinstance(node, ast.Name):
        resolved = aliases.get(node.id)
        if resolved in IDENTITY_STAMP_NAMES:
            return resolved
    return None


def _stamp_of_attribute(node: ast.Attribute, aliases: Mapping[str, str]) -> str | None:
    """``NER`` in ``NER.mark_value(...)``, or ``None`` when the receiver is anything else."""
    return _stamp_name(node.value, aliases)


def _stamp_of_key(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    """``NER`` in ``NER.key``, or ``None``."""
    if isinstance(node, ast.Attribute) and node.attr == "key":
        return _stamp_name(node.value, aliases)
    return None


def _stamp_of_key_slice(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    """``NER`` in the ``execution_log[NER.key]`` target of an assignment, or ``None``."""
    if isinstance(node, ast.Subscript):
        return _stamp_of_key(node.slice, aliases)
    return None


def _is_execution_log(node: ast.AST) -> bool:
    """``execution_log`` or ``doc.execution_log``, the only ledger the gate follows."""
    return (isinstance(node, ast.Attribute) and node.attr == "execution_log") or (
        isinstance(node, ast.Name) and node.id == "execution_log"
    )


def _constant_value(node: ast.AST, constants: Mapping[str, str]) -> str | None:
    """A string literal, or the value of a local name bound to one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _invalid_constant(stamp_name: str, node: ast.AST, constants: Mapping[str, str]) -> str | None:
    """The literal when it is not a fingerprint this slot accepts, else ``None``."""
    value = _constant_value(node, constants)
    if value is not None and not IDENTITY_STAMPS[stamp_name].fingerprint_pattern.fullmatch(value):
        return value
    return None


def _bad_dict_entries(
    node: ast.Dict, aliases: Mapping[str, str], constants: Mapping[str, str]
) -> list[tuple[int, str, str]]:
    """Every ``{STAMP.key: <non-fingerprint>}`` entry, as ``(line, stamp, value)``."""
    findings: list[tuple[int, str, str]] = []
    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:  # ``{**other}`` has no key expression.
            continue
        stamp_name = _stamp_of_key(key, aliases)
        if stamp_name is None:
            continue
        literal = _invalid_constant(stamp_name, value, constants)
        if literal is not None:
            findings.append((key.lineno, stamp_name, literal))
    return findings


def _forbidden_writes(tree: ast.AST) -> list[tuple[int, str]]:
    """Every non-fingerprint write into an identity slot, as ``(line, what it is)``."""
    aliases = _stamp_aliases(tree)
    constants = _string_constants(tree)
    findings: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            stamp_name = _stamp_of_attribute(node.func, aliases)
            if stamp_name is not None:
                if node.func.attr == "mark":
                    findings.append((node.lineno, f"{stamp_name}.mark(...) writes a status into an identity slot"))
                elif node.func.attr == "mark_value" and len(node.args) >= 2:
                    literal = _invalid_constant(stamp_name, node.args[1], constants)
                    if literal is not None:
                        findings.append(
                            (
                                node.lineno,
                                f"{stamp_name}.mark_value(..., {literal!r}) is not a producer fingerprint",
                            )
                        )
            if (
                node.func.attr == "update"
                and _is_execution_log(node.func.value)
                and node.args
                and isinstance(node.args[0], ast.Dict)
            ):
                for line, dict_stamp, literal in _bad_dict_entries(node.args[0], aliases, constants):
                    findings.append(
                        (
                            line,
                            f"execution_log.update({{{dict_stamp}.key: {literal!r}}}) bypasses mark_value",
                        )
                    )
        elif isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Dict):
                for target in node.targets:
                    if _is_execution_log(target):
                        for line, dict_stamp, literal in _bad_dict_entries(node.value, aliases, constants):
                            findings.append(
                                (
                                    line,
                                    f"execution_log = {{..., {dict_stamp}.key: {literal!r}}} bypasses mark_value",
                                )
                            )
            for target in node.targets:
                stamp_name = _stamp_of_key_slice(target, aliases)
                if stamp_name is None:
                    continue
                literal = _invalid_constant(stamp_name, node.value, constants)
                if literal is not None:
                    findings.append((node.lineno, f"execution_log[{stamp_name}.key] = {literal!r} bypasses mark_value"))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            stamp_name = _stamp_of_key_slice(node.target, aliases)
            if stamp_name is not None:
                literal = _invalid_constant(stamp_name, node.value, constants)
                if literal is not None:
                    findings.append((node.lineno, f"execution_log[{stamp_name}.key] = {literal!r} bypasses mark_value"))
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.BitOr) and isinstance(node.value, ast.Dict):
            if _is_execution_log(node.target):
                for line, dict_stamp, literal in _bad_dict_entries(node.value, aliases, constants):
                    findings.append(
                        (
                            line,
                            f"execution_log |= {{..., {dict_stamp}.key: {literal!r}}} bypasses mark_value",
                        )
                    )

    return sorted(findings)


def test_the_gate_knows_every_identity_stamp() -> None:
    """A slot added to the vocabulary must be scanned here too, and pinning the set makes that fail."""
    assert IDENTITY_STAMP_NAMES == EXPECTED_IDENTITY_STAMPS


def test_no_worker_writes_a_non_fingerprint_into_an_identity_slot() -> None:
    findings = [
        f"{path.relative_to(REPO_ROOT)}:{line}: {message}"
        for path in _worker_files()
        for line, message in _forbidden_writes(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    ]

    assert not findings, "An identity-keyed stamp takes a producer fingerprint and nothing else:\n" + "\n".join(
        findings
    )


VALID_FINGERPRINT = "ab" * 32
VALID_EMBEDDING_FINGERPRINT = "a" * 32 + ":" + "b" * 64


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        pytest.param(
            'doc.execution_log = NER.mark_value(doc.execution_log, "DONE")\n',
            ["NER.mark_value(..., 'DONE') is not a producer fingerprint"],
            id="mark-value",
        ),
        pytest.param(
            'doc.execution_log[MACRO_CATEGORY.key] = "True"\n',
            ["execution_log[MACRO_CATEGORY.key] = 'True' bypasses mark_value"],
            id="direct-subscript",
        ),
        pytest.param(
            'doc.execution_log.update({TYPOLOGY.key: "ERROR"})\n',
            ["execution_log.update({TYPOLOGY.key: 'ERROR'}) bypasses mark_value"],
            id="dict-update",
        ),
        pytest.param(
            'doc.execution_log = {**doc.execution_log, QUALITY_VALIDATOR.key: "DONE"}\n',
            ["execution_log = {..., QUALITY_VALIDATOR.key: 'DONE'} bypasses mark_value"],
            id="dict-literal",
        ),
        pytest.param(
            'doc.execution_log |= {EMBEDDING.key: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n',
            ["execution_log |= {..., EMBEDDING.key: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'} bypasses mark_value"],
            id="dict-augassign",
        ),
        pytest.param(
            'stamp = NER\ndoc.execution_log = stamp.mark_value(doc.execution_log, "DONE")\n',
            ["NER.mark_value(..., 'DONE') is not a producer fingerprint"],
            id="alias",
        ),
        pytest.param(
            'value = "DONE"\ndoc.execution_log[NER.key] = value\n',
            ["execution_log[NER.key] = 'DONE' bypasses mark_value"],
            id="local-constant",
        ),
        pytest.param(
            f'doc.execution_log[EMBEDDING.key] = "{"a" * 32}"\n',
            ["execution_log[EMBEDDING.key] = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' bypasses mark_value"],
            id="bare-embedding-md5",
        ),
    ],
)
def test_the_scan_would_catch_a_non_fingerprint_write(snippet: str, expected: list[str]) -> None:
    """A gate that cannot fail is not a gate: each shape is run over a snippet that does."""
    findings = _forbidden_writes(ast.parse(snippet))

    assert [message for _line, message in findings] == expected


def test_the_scan_accepts_a_fingerprint_and_the_two_allowed_writers() -> None:
    """The pattern and the failure writer are the two paths a worker is allowed to take."""
    snippet = (
        f'doc.execution_log[NER.key] = "{VALID_FINGERPRINT}"\n'
        f'doc.execution_log[EMBEDDING.key] = "{VALID_EMBEDDING_FINGERPRINT}"\n'
        "doc.execution_log = NER.mark_failed(doc.execution_log)\n"
        "doc.execution_log = NER.mark_value(doc.execution_log, identity)\n"
    )

    assert _forbidden_writes(ast.parse(snippet)) == []
