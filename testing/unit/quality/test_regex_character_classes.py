"""The local half of CodeQL's two character-class rules: no accidental range, no repeated character.

Both findings this file was written for landed on one line of ``worker_ner.py``:

* ``py/overly-large-range`` read ``[$-_@.&+]`` as the **range** ``$`` to ``_`` — 60 characters, every
  digit, every uppercase letter and ``[ \\ ] ^`` — where the author meant a handful of punctuation.
* ``py/regex/duplicate-in-character-class`` read ``[!*\\\\(\\\\),]`` as a class listing ``\\`` twice.

Neither is a style nit: the first smuggled ``\\`` and ``^`` into a URL pattern that then ate them, and
both are what CWE-20 is about on the CodeQL side. The ranges the queries allow are the deliberate ones
— ``A-Z``, ``a-z``, ``0-9``, ``A-F`` — so this gate reproduces the rule rather than banning ranges:

* ``overly-large-range`` (``Security/CWE-020/OverlyLargeRange.ql``, via the shared
  ``OverlyLargeRangeQuery``): a range of **10 or more** ASCII characters is suspicious when it crosses
  ``Z``-``a`` or ``9``-``A``, or when either bound is not alphanumeric — minus the query's own
  allowlist (``~`` at the top, a space or ``!`` at the bottom, ``@``-``_``, ``0``-``?``, ``@``-``Z``,
  and anything from the zero byte). An empty range is always reported.
* ``duplicate-in-character-class`` (``Expressions/Regex/DuplicateCharacterInSet.ql``): the same
  single-character element twice in one class, compared by its spelling as the query compares it.

The scope is the statically known patterns: a ``re.*`` call with a literal first argument. A pattern
built at runtime is invisible here — which is also where CodeQL stops.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The scope the gates read — the same one the sibling quality gates use.
SCANNED = ("src/scrinalia", "main.py", "testing", "docs/_hooks", "migrations")

#: ``re.<func>(pattern, ...)``, the calls whose first argument is a pattern.
_RE_FUNCTIONS = frozenset({"compile", "sub", "subn", "match", "fullmatch", "search", "split", "findall", "finditer"})

#: An element is ``(kind, low, high)``: a single character (``high`` is ``None``) or a range.
Element = tuple[str, str, str | None]

_ALNUM = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def _escape_length(pattern: str, index: int) -> int:
    """How many characters the escape starting at ``pattern[index] == "\\"`` occupies."""
    kind = pattern[index + 1 : index + 2]
    if kind == "x":
        return 4
    if kind == "u":
        return 6
    if kind == "U":
        return 10
    if kind == "N" and pattern[index + 2 : index + 3] == "{":
        closing = pattern.find("}", index + 3)
        return closing - index + 1 if closing != -1 else len(pattern) - index
    if kind.isdigit():  # an octal escape takes up to three digits
        length = 2
        while length < 4 and pattern[index + length : index + length + 1] in "01234567":
            length += 1
        return length
    return 2


def _class_elements(pattern: str, start: int) -> tuple[list[Element], int]:
    """The elements of the class opening at ``pattern[start]``, and the index just past its ``]``."""
    index = start + 1
    if pattern[index : index + 1] == "^":
        index += 1

    elements: list[Element] = []
    first = True
    while index < len(pattern):
        char = pattern[index]
        # A ``]`` that opens the class is a literal, exactly as the re module reads it.
        if char == "]" and not first:
            return elements, index + 1
        first = False
        if char == "\\":
            end = index + _escape_length(pattern, index)
            elements.append(("char", pattern[index:end], None))
            index = end
            continue
        # ``-`` is a range only between two characters; at either end it is the literal dash.
        if pattern[index + 1 : index + 2] == "-" and pattern[index + 2 : index + 3] not in ("", "]"):
            elements.append(("range", char, pattern[index + 2]))
            index += 3
            continue
        elements.append(("char", char, None))
        index += 1
    return elements, index


def character_classes(pattern: str) -> list[list[Element]]:
    """Every character class in ``pattern``, escapes outside a class respected."""
    classes: list[list[Element]] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += _escape_length(pattern, index)
            continue
        if char == "[":
            elements, index = _class_elements(pattern, index)
            classes.append(elements)
            continue
        index += 1
    return classes


def _allowed_wide_range(low: str, high: str) -> bool:
    """The query's allowlist: the wide ranges a reader is expected to write on purpose."""
    return high == "~" or low in (" ", "!", "\0") or (low, high) in {("@", "_"), ("0", "?"), ("@", "Z")}


def range_problem(low: str, high: str) -> str | None:
    """Why ``low-high`` is suspicious, or ``None`` when it is not — the query's conditions."""
    if ord(low) > ord(high):
        return "is empty"

    size = ord(high) - ord(low) + 1
    if size < 10:
        return None

    crosses_z_to_a = ord(low) <= ord("Z") and ord("a") <= ord(high)
    crosses_9_to_a = ord(low) <= ord("9") and ord("A") <= ord(high)
    # The query only asks for a non-alphanumeric bound while both ends are still ASCII; a range like
    # ``A-ÿ`` is a deliberate accented alphabet, not a typo.
    non_alphanumeric_bound = ord(low) < 128 and ord(high) < 128 and not (low in _ALNUM and high in _ALNUM)

    if not (crosses_z_to_a or crosses_9_to_a or non_alphanumeric_bound):
        return None
    if _allowed_wide_range(low, high):
        return None
    return f"spans {size} characters, from {low!r} to {high!r}"


def regex_issues(pattern: str) -> list[str]:
    """The duplicate characters and suspicious ranges in ``pattern``, as readable sentences."""
    issues: list[str] = []
    for elements in character_classes(pattern):
        seen: dict[str, int] = {}
        for kind, low, _ in elements:
            if kind == "char":
                seen[low] = seen.get(low, 0) + 1
        issues.extend(
            f"duplicate character {text!r} in a character class" for text, count in sorted(seen.items()) if count > 1
        )
        for kind, low, high in elements:
            if kind == "range" and high is not None:
                problem = range_problem(low, high)
                if problem:
                    issues.append(f"suspicious range {low!r}-{high!r} ({problem})")
    return issues


def _static_patterns() -> list[tuple[Path, int, str]]:
    """Every ``re.*`` call with a literal pattern inside :data:`SCANNED`."""
    files: list[Path] = []
    for entry in SCANNED:
        path = REPO_ROOT / entry
        files.extend([path] if path.is_file() else sorted(path.rglob("*.py")))

    found: list[tuple[Path, int, str]] = []
    for path in files:
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr not in _RE_FUNCTIONS:
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "re"):
                continue
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.append((path, node.lineno, argument.value))
    return found


def test_the_check_reads_a_class_the_way_the_re_module_does() -> None:
    """A parser that drops a class reports nothing, so the readings are pinned one by one."""
    assert character_classes(r"[$-_@.&+]") == [
        [
            ("range", "$", "_"),
            ("char", "@", None),
            ("char", ".", None),
            ("char", "&", None),
            ("char", "+", None),
        ]
    ]
    assert character_classes("[A-Za-z]") == [[("range", "A", "Z"), ("range", "a", "z")]]
    assert character_classes("[]]") == [[("char", "]", None)]]
    assert character_classes(r"[\]a]") == [[("char", "\\]", None), ("char", "a", None)]]
    assert character_classes(r"[a\-z]") == [[("char", "a", None), ("char", "\\-", None), ("char", "z", None)]]
    assert character_classes(r"[a-]") == [[("char", "a", None), ("char", "-", None)]]
    assert character_classes(r"[\d-x]") != []
    assert character_classes(r"a-[b]") == [[("char", "b", None)]]


def test_the_check_notices_both_findings_and_allows_the_deliberate_ranges() -> None:
    """Both directions: what the two queries report, and what they deliberately leave alone."""
    assert regex_issues(r"[$-_@.&+]") == ["suspicious range '$'-'_' (spans 60 characters, from '$' to '_')"]
    escaped_backslash = chr(92) * 2
    assert regex_issues(r"[!*\\(\\),]") == [f"duplicate character {escaped_backslash!r} in a character class"]
    assert regex_issues("[aa]") == ["duplicate character 'a' in a character class"]

    assert regex_issues("[A-Za-z0-9._:-]") == []
    assert regex_issues("[0-9a-fA-F]") == []
    assert regex_issues(r"[\/\\\-\u2013\u2014]+") == []
    assert regex_issues("[A-Za-zÀ-ÿ]") == []  # non-ASCII: an alphabet, not a typo
    assert regex_issues("[@-_]") == []  # the query's own allowlist
    assert regex_issues("[z-a]") == ["suspicious range 'z'-'a' (is empty)"]


def test_no_character_class_is_accidental() -> None:
    """No rule the query names may come back in a statically known pattern."""
    violations: list[str] = []
    for path, lineno, pattern in _static_patterns():
        for issue in regex_issues(pattern):
            violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {issue} in {pattern!r}")

    assert not violations, (
        "a regular expression character class is accidental (CodeQL ``py/overly-large-range`` / "
        "``py/regex/duplicate-in-character-class``) at "
        + "; ".join(violations)
        + " — write the characters out instead of a range nobody can read, and never list one twice: "
        "an unescaped ``-`` between two characters is a range, and a range that crosses ``Z``-``a`` "
        "or ``9``-``A`` matches far more than it looks."
    )
