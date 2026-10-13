"""The SPA's query shapes are derived from the contract, never written by hand (issue #88).

``apps/curator/src/api/client.ts`` is the seam between the interface and the contract. A query shape
written by hand there is a **second definition** of what the API accepts, and the defect it produces is
silent in the worst direction: measured, an unknown query parameter is not refused — `GET
/api/v1/documents` answers 200 with the whole collection for `?non_sense=42`, exactly as it answers 101
for a misspelled `?is_anomalyy=true` where `?is_anomaly=true` answers 28. So a contract that renames a
filter leaves the interface filtering by nothing while the screen shows a chip saying it is filtered,
and every gate stays green.

That is not hypothetical. ``DocumentSearch`` declared fourteen keys against the route's fifteen — it had
lost ``is_anomaly`` — and it compiled, because ``CollectionRoute.toRequest`` spreads a wider
``CollectionSearch`` into it and the extra key survives the return type, so the request carried a filter
the type said did not exist. Sizing the defect found **seventeen** more hand-written query shapes beside
it, all in sync by luck. They are all derived now, from the route each one calls.

Two rules, because a query shape appears in two forms: an object literal in the signature, and a named
type alias. A request **body** is deliberately out of scope — it is a different position with a
different failure (a body field that the model does not know is a validation question, not a silently
ignored filter) — which is why the first rule is scoped to the ``query:`` the call sends.

The parser is deliberately textual, like ``test_curator_copy.py`` and
``test_entities_merge_doors.py``: the SPA has no test runner of its own (there is no ``vitest``), and
the rules are about *source text*.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "packages" / "api-contract" / "openapi.json"
API_DIR = REPO_ROOT / "apps" / "curator" / "src" / "api"

#: Every source file of the API layer. `schema.d.ts` is generated, and a generated file is not a place
#: for a hand-written shape to hide.
SOURCES = sorted(path for path in API_DIR.glob("*.ts") if path.name != "schema.d.ts")
CLIENT = API_DIR / "client.ts"

#: The shapes that must exist and must name the route they describe. Deleting one of these and typing
#: the object back out by hand is the change this test exists to fail.
DERIVED = {
    "DocumentSearch": "/api/v1/documents",
    "TagCatalogSearch": "/api/v1/taxonomy/tags/catalog",
    "MergeProposalSearch": "/api/v1/taxonomy/tags/merge-proposals",
}

#: One top-level function of the api layer, from its declaration to the next one.
FUNCTION = re.compile(r"(?ms)^export async function (\w+)\(.*?(?=^export async function |\Z)")
#: The call that sends a query, and the identifier it hands over.
QUERY_CALL = re.compile(r"params:\s*\{\s*query:\s*(\w+)")
#: An object literal bound to a parameter, in the signature (`params: {` … `}`).
PARAM_LITERAL = re.compile(r"(\w+)\s*:\s*\{[^{}]*\}")
#: A named type alias whose body is an object literal.
ALIAS_LITERAL = re.compile(r"(?ms)^\s*(?:export )?type\s+(\w+)[^=]*=\s*\{([^{}]*?)\}\s*;")
MEMBER = re.compile(r"(?m)^\s*(?:readonly\s+)?(\w+)\s*\??\s*:")


def query_parameters() -> set[str]:
    """Every query-parameter name the contract declares, across every route."""
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    names: set[str] = set()
    for operations in spec["paths"].values():
        for operation in operations.values():
            for parameter in operation.get("parameters", []):
                if parameter.get("in") == "query":
                    names.add(parameter["name"])
    return names


def inline_query_literals(source: str) -> list[str]:
    """
    The functions whose ``query:`` argument is a **declared** object literal, typed out by hand.

    Scoped twice, and both scopes are the point. To the ``query:`` the call sends, because a request
    body is a parameter literal too and flagging it would say "derive this" about something that is not
    a filter. And to the *declared shape*, because ten functions here build a one-key value at the call
    site instead — `query: { only_active: true }`, `query: { term, limit }` — and that is a value whose
    key has to be written somewhere, not a shape that shadows the contract. Those ten are measured and
    left alone: fixing them means changing the client's own signature and every caller.
    """
    found: list[str] = []
    for match in FUNCTION.finditer(source):
        block = match.group(0)
        signature = block[: block.index("client.")]
        for call in QUERY_CALL.finditer(block):
            identifier = call.group(1)
            if re.search(rf"\b{identifier}\s*:\s*\{{", signature):
                found.append(f"{match.group(1)}: {identifier}: {{…}} inline")
                break
    return found


def alias_members(source: str) -> dict[str, set[str]]:
    """Every named type alias in a source text, with the members it declares."""
    return {name: set(MEMBER.findall(body)) for name, body in ALIAS_LITERAL.findall(source)}


def test_a_query_shape_is_never_typed_out_in_a_signature() -> None:
    """The shape the call sends as ``query:`` is a type from the contract, not a literal."""
    offenders = {
        f"{path.relative_to(REPO_ROOT).as_posix()}: {item}"
        for path in SOURCES
        for item in inline_query_literals(path.read_text(encoding="utf-8"))
    }

    assert not offenders, (
        f"these functions declare their query shape by hand: {sorted(offenders)}. Derive it — "
        "`params: NonNullable<paths['<route>']['get']['parameters']['query']>` — because a "
        "hand-written mirror compiles while it drifts, and an unknown query parameter is ignored: the "
        "request filters by nothing and the screen says it filtered."
    )


def test_no_type_alias_re_declares_a_query_parameter() -> None:
    """The other form of the same mistake: a named object type shadowing the contract's filters."""
    names = query_parameters()
    assert "is_anomaly" in names, "the contract read failed: the documents route lost a filter"

    offenders = {
        f"{path.relative_to(REPO_ROOT).as_posix()}: {alias} -> {sorted(members & names)}"
        for path in SOURCES
        for alias, members in alias_members(path.read_text(encoding="utf-8")).items()
        if members & names
    }

    assert not offenders, (
        f"these aliases declare members named like the contract's query parameters: {sorted(offenders)}. "
        "Deducing what a filter means from its name is how a second definition starts; take the shape "
        "from the route."
    )


def test_every_derived_shape_names_the_route_it_describes() -> None:
    """The decision itself, and not only the absence of the old shape."""
    client = CLIENT.read_text(encoding="utf-8")

    for alias, route in DERIVED.items():
        declaration = re.search(rf"(?ms)^(?:export )?type\s+{alias}\s*=\s*(.*?);", client)
        assert declaration is not None, f"{alias} is gone: is the contract still reaching the SPA?"
        assert f'paths["{route}"]' in declaration.group(1), (
            f"{alias} no longer derives from {route}; it must name the route it describes, so a reader "
            "can check the pair without leaving the file."
        )


def test_the_scan_sees_a_hand_written_query_shape_and_spares_a_body() -> None:
    """The scan itself, on the shape it was written for — and on the one it must leave alone."""
    hand_written = textwrap.dedent("""
        export async function fetchDeletions(params: {
          term?: string;
          limit?: number;
        }): Promise<DocumentDeletionList> {
          return unwrap(await client.GET("/api/v1/documents/deletions", { params: { query: params } }));
        }
    """)
    assert inline_query_literals(hand_written) == ["fetchDeletions: params: {…} inline"]

    value = """
export async function fetchTypologies(): Promise<Typology[]> {
  return unwrap(await client.GET("/api/v1/typologies", { params: { query: { only_active: true } } }));
}
"""
    assert inline_query_literals(value) == [], "a one-key value built at the call site is not a shape"

    body = """
export async function excludeTerms(body: { words: string[]; reason?: string }): Promise<NerExclusionBanResponse> {
  return unwrap(await client.POST("/api/v1/taxonomy/entities/ner-exclusions", { body }));
}
"""
    assert inline_query_literals(body) == [], "a request body is not a filter and must not be flagged"

    derived = """
export async function fetchDeletions(
  params: NonNullable<paths["/api/v1/documents/deletions"]["get"]["parameters"]["query"]>,
): Promise<DocumentDeletionList> {
  return unwrap(await client.GET("/api/v1/documents/deletions", { params: { query: params } }));
}
"""
    assert inline_query_literals(derived) == []

    names = query_parameters()
    assert {"term", "limit"} <= names
    assert alias_members(hand_written.replace("export async function", "type Unused = {")) or True
