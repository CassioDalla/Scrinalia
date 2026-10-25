"""The SPA's request bodies are derived from the contract, never written by hand (issue #93).

``apps/curator/src/api/client.ts`` is the seam between the interface and the contract. A request body
typed out in a function's signature is a **second definition** of what the route accepts, and it fails
in the direction that compiles. Measured against the request models of the taxonomy and text-quality
routes:

| what the caller does to a field | result |
| --- | --- |
| renames a **required** one | refused — pydantic raises, the route answers 400 |
| omits a **required** one | refused — 400 |
| renames an **optional** one | **accepted and ignored** |
| sends an unknown extra one | **accepted and ignored** |

``EntityMergePreviewRequest`` with ``new_name`` renamed to ``new_nam`` validates, and the merge simply
does not rename. So the required half needs no rule — the API already refuses it — and the optional
half is exactly what a hand-written mirror loses without a trace. That is why the rule here is not
"keep the fields in sync" but "do not retype the body at all": the body **is** the model the route
declares.

The silence is not even uniform: ten of those thirteen models keep pydantic's default
(``extra="ignore"``) and three declare ``extra="forbid"``, so an unknown field is a 400 on
``SubjectExclusionRequest`` and a 200 everywhere else. A generated type cannot tell the two apart, and
the client must not learn the difference by copying the list. The API-side question lives in #177.

A **deliberate** narrowing is allowed, because it is a statement about the function and not about the
contract — and it is derived, so a rename in the model breaks the ``Pick`` at compile time. Each one
is listed in :data:`NARROWED` with the screen or the route that justifies it, so adding another is a
line a reviewer reads. Today there are four:

* ``TagPairPreviewBody`` — the pair form of the merge preview; the proposal form is ``previewMerge``'s.
* ``SubjectExclusionBody`` — ``source`` stays required, because the model's ``HUMAN`` default would
  let a ``RULE`` verdict be recorded as a human judgement.
* ``NerRemovalBody`` — the removal route takes the ban's model but reads only ``words`` (#176).
* ``MacroSuggestionBody`` — no screen offers ``columns_to_extract`` yet (#174).

The parser is deliberately textual, like ``test_api_query_shapes.py``: the SPA has no test runner of
its own (there is no ``vitest``), and the rules are about *source text*.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "packages" / "api-contract" / "openapi.json"
API_DIR = REPO_ROOT / "apps" / "curator" / "src" / "api"
CLIENT = API_DIR / "client.ts"

#: Every source file of the API layer, minus the generated one: a stale generated file is not a place
#: for a hand-written shape to hide.
SOURCES = sorted(path for path in API_DIR.glob("*.ts") if path.name != "schema.d.ts")

#: One top-level function of the api layer, from its declaration to the next one.
FUNCTION = re.compile(r"(?ms)^export async function (\w+)\(.*?(?=^export async function |\Z)")
#: The call that sends the request, and the route + method it names.
CALL = re.compile(r'client\.(GET|POST|PATCH|PUT|DELETE)\("([^"]+)"')
#: A type alias, from its declaration to the semicolon that ends it.
ALIAS = re.compile(r"(?ms)^(?:export\s+)?type\s+(\w+)\s*=\s*(.*?);")
#: The wrappers a body may be narrowed with. They all keep the model inside, so the derivation
#: survives — a rename in the contract makes the wrapper fail to compile, which is the point.
WRAPPER = re.compile(r"\b(?:Required|Pick|Omit|Partial|NonNullable)\s*<")

#: The narrowings this client has decided on, each with the model it derives from. A new one is a
#: change to this table; a removed one is too, because the client stopped offering something.
NARROWED = {
    "TagPairPreviewBody": "MergePreviewRequest",
    "SubjectExclusionBody": "SubjectExclusionRequest",
    "NerRemovalBody": "NerExclusionRequest",
    "MacroSuggestionBody": "SuggestMacroRequest",
}


def request_body_models() -> dict[tuple[str, str], str]:
    """Every route and method whose request body is a ``$ref``, and the schema it points at."""
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    models: dict[tuple[str, str], str] = {}
    for route, operations in spec["paths"].items():
        for method, operation in operations.items():
            schema = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            if "$ref" in schema:
                models[(method, route)] = schema["$ref"].rsplit("/", 1)[-1]
    return models


def _balanced_type(text: str, start: int) -> str:
    """The type expression beginning at ``start``, up to its separator (``,`` or the closing ``)``)."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char in "{[(<":
            depth += 1
        elif char in "}])>":
            if depth == 0:
                return text[start:index]
            depth -= 1
        elif char == "," and depth == 0:
            return text[start:index]
    return text[start:]


def body_types(source: str) -> dict[str, str]:
    """
    The declared type of each function's ``body`` parameter, by function name.

    Empty for a function that declares none — ``previewMerge`` and ``purgeStopwords`` build a one-key
    value at the call site instead, and that is a value whose keys are written somewhere, not a shape
    that shadows the contract. ``openapi-fetch`` excess-property-checks a fresh literal, so those are
    loud where a declared mirror is not.
    """
    found: dict[str, str] = {}
    for match in FUNCTION.finditer(source):
        block = match.group(0)
        call = block.find("client.")
        signature = block[:call] if call >= 0 else block
        parameter = re.search(r"\bbody\??\s*:\s*", signature)
        found[match.group(1)] = _balanced_type(signature, parameter.end()).strip() if parameter else ""
    return found


def aliases(source: str) -> dict[str, str]:
    """Every named type alias in a source text, with the type it is declared as."""
    return {name: body.strip() for name, body in ALIAS.findall(source)}


def resolve(type_text: str, table: dict[str, str], depth: int = 4) -> str:
    """Expand the named aliases a type text refers to, until the route or the model shows through."""
    for _ in range(depth):
        if 'components["schemas"]["' in type_text or 'paths["' in type_text:
            return type_text
        names = [name for name in table if re.search(rf"\b{re.escape(name)}\b", type_text)]
        if not names:
            return type_text
        for name in names:
            type_text = re.sub(rf"\b{re.escape(name)}\b", lambda _match, body=table[name]: body, type_text)
    return type_text


def narrowings(source: str) -> dict[str, str]:
    """Every alias that narrows a request model with a derived wrapper, and the model it derives from."""
    table = aliases(source)
    request_models = set(request_body_models().values())
    found: dict[str, str] = {}
    for name, body in table.items():
        if not WRAPPER.search(body):
            continue
        resolved = resolve(body, table)
        for model in request_models:
            if f'components["schemas"]["{model}"]' in resolved:
                found[name] = model
                break
    return found


def test_a_request_body_is_never_typed_out_in_a_signature() -> None:
    """The shape the call sends as ``body:`` is a type from the contract, not a literal."""
    offenders = {
        f"{path.relative_to(REPO_ROOT).as_posix()}: {name}: {shape[:80]}"
        for path in SOURCES
        for name, shape in body_types(path.read_text(encoding="utf-8")).items()
        if shape.startswith("{")
    }

    assert not offenders, (
        f"these functions declare their request body by hand: {sorted(offenders)}. Derive it from "
        "the model the route declares, because pydantic refuses a missing *required* field and "
        "*ignores* an unknown one — so a renamed optional field is dropped without a trace, and the "
        "screen keeps behaving as if the write had happened."
    )


def test_every_request_body_derives_from_the_route_it_calls() -> None:
    """The decision itself, checked against the contract rather than trusted to a convention."""
    source = CLIENT.read_text(encoding="utf-8")
    models = request_body_models()
    table = aliases(source)
    declared = body_types(source)

    assert ("post", "/api/v1/taxonomy/tags/merge/batch") in models, (
        "the contract read failed: the merge batch route lost its request body"
    )

    offenders: list[str] = []
    for match in FUNCTION.finditer(source):
        name = match.group(1)
        call = CALL.search(match.group(0))
        shape = declared.get(name, "")
        if call is None or not shape:
            continue
        method, route = call.group(1).lower(), call.group(2)
        model = models.get((method, route))
        if model is None:
            continue
        resolved = resolve(shape, table)
        if f'components["schemas"]["{model}"]' not in resolved and f'paths["{route}"]' not in resolved:
            offenders.append(f"{name}: {shape[:60]} -> {method.upper()} {route} declares {model}")

    assert not offenders, (
        f"these request bodies do not derive from the model their route declares: {sorted(offenders)}. "
        "Take the schema from the contract (or from `paths[route][method]`), so a rename reaches this "
        "client as a compile error instead of a field the server silently ignores."
    )


def test_the_deliberate_narrowings_are_the_ones_this_client_decided() -> None:
    """A narrowing is allowed, but only as a line in this table that a reviewer reads."""
    found = narrowings(CLIENT.read_text(encoding="utf-8"))

    assert found == NARROWED, (
        "the body narrowings changed: "
        f"added {sorted(set(found) - set(NARROWED))}, removed {sorted(set(NARROWED) - set(found))}. "
        "A narrowing that drops a field the model declares is a decision about the client's API, so it "
        "belongs in this table with the screen or route that justifies it — not in the diff alone."
    )


def test_the_scan_sees_a_hand_written_body_and_spares_a_call_site_value() -> None:
    """The scan itself, on the shapes it was written for — and on the ones it must leave alone."""
    hand_written = textwrap.dedent("""
        export async function banStopwords(body: { words: string[]; scope?: StopwordsScope }): Promise<Stopwords> {
          return unwrap(await client.POST("/api/v1/taxonomy/tags/stopwords", { body }));
        }
    """)
    assert body_types(hand_written) == {"banStopwords": "{ words: string[]; scope?: StopwordsScope }"}

    value = """
export async function purgeStopwords(): Promise<StopwordPurgeResponse> {
  return unwrap(await client.POST("/api/v1/taxonomy/tags/stopwords/purge", { body: {} }));
}
"""
    assert body_types(value) == {"purgeStopwords": ""}, "a one-key value built at the call site is not a shape"

    derived = """
export async function banStopwords(body: StopwordCreateRequest): Promise<StopwordBanResponse> {
  return unwrap(await client.POST("/api/v1/taxonomy/tags/stopwords", { body }));
}
"""
    assert body_types(derived) == {"banStopwords": "StopwordCreateRequest"}

    narrowed = """
type MergePreviewRequest = components["schemas"]["MergePreviewRequest"];
type PairBody = Required<Pick<MergePreviewRequest, "canonical_id" | "ids_to_merge">>;
export async function previewTagPair(
  body: PairBody,
): Promise<MergePreview> {
  return unwrap(await client.POST("/api/v1/taxonomy/tags/merge/preview", { body }));
}
"""
    assert body_types(narrowed)["previewTagPair"] == "PairBody"
    assert narrowings(narrowed) == {"PairBody": "MergePreviewRequest"}, (
        "a derived wrapper around the model is a narrowing, and it is the one shape this scan must see"
    )

    # The narrowing is derived, not retyped: the wrapper names the model's own keys, so the contract
    # renaming one of them is a compile error rather than a body the route silently ignores.
    assert 'Pick<MergePreviewRequest, "canonical_id" | "ids_to_merge">' in aliases(narrowed)["PairBody"]
