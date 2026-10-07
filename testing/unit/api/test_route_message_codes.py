"""
Every route answer that carries a sentence must carry a code next to it.

The API used to answer only ``message``, with the prose written in Portuguese inside the controller
or the service. That works until the front has to speak another language: translating the screens
would leave every confirmation and every refusal in the server's language, and turning the prose
into an identifier afterwards is an incompatible change — ``message`` would stop being the text the
screen prints.

So a route answers both, and this module is what keeps that true for the routes that come next. It
is deliberately a structural test over the schemas rather than a list of names: a hand-maintained
list is the thing that goes stale, and the failure it would hide is a new route shipping without a
code, which nobody notices until the translation lands.
"""

import importlib
import pkgutil

import pydantic
import pytest

from scrinalia.domains.archive.schemas import RouteMessageCode, RouteResponse

#: The packages that declare the shapes the API answers with. Both are walked as packages rather
#: than as namespaces: a model lives in a submodule and is only re-exported by ``__init__``, so
#: reading the package namespace would compare ``obj.__module__`` against the package and match
#: nothing — which is how this test first passed with the defect deliberately reintroduced.
SCHEMA_PACKAGES: tuple[str, ...] = (
    "scrinalia.domains.archive.schemas",
    "scrinalia.api.schemas",
)


def _response_models() -> list[type[pydantic.BaseModel]]:
    """Every model declared by the schema packages, one pass per module."""
    found: list[type[pydantic.BaseModel]] = []
    for package_name in SCHEMA_PACKAGES:
        package = importlib.import_module(package_name)
        for info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{package_name}.{info.name}")
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, pydantic.BaseModel)
                    and obj is not pydantic.BaseModel
                    and obj.__module__ == module.__name__
                ):
                    found.append(obj)
    return found


def test_every_message_bearing_response_also_carries_a_code() -> None:
    """
    A response with ``message`` and no ``code`` is the defect this contract exists to prevent.

    ``MacroCategoriesSuggestionResponse`` is the one shape allowed to have both optional: the
    clustering route succeeds with an empty answer, so its sentence is a warning that may be absent.
    It still declares the field, which is what this test checks — the assertion is about the field
    existing, not about it being required.
    """
    offenders = [
        model.__name__
        for model in _response_models()
        if "message" in model.model_fields and "code" not in model.model_fields
    ]

    assert offenders == [], (
        f"these responses carry a message without a code: {offenders}. "
        "Inherit RouteResponse, or add the optional code if the message is itself optional."
    )


def test_the_shared_base_is_what_carries_the_pair() -> None:
    """The pair is defined once, so a change to the contract has one place to happen."""
    assert set(RouteResponse.model_fields) == {"code", "message"}
    assert RouteResponse.model_fields["code"].is_required()
    assert RouteResponse.model_fields["message"].is_required()


def test_the_enum_covers_more_than_one_route() -> None:
    """
    The codes are a shared vocabulary, not a per-route string.

    A regression that replaced the enum with a bare ``str`` would still satisfy the test above, so
    this one asserts the field is typed with the enum — and that the enum is the one place a new
    outcome is declared.
    """
    assert RouteResponse.model_fields["code"].annotation is RouteMessageCode
    assert issubclass(RouteMessageCode, str), "a code has to survive JSON as a plain string"
    assert len(RouteMessageCode) >= 20, "one member per outcome, shared across the routes that produce it"


@pytest.mark.parametrize("code", list(RouteMessageCode))
def test_every_code_is_a_stable_upper_snake_identifier(code: RouteMessageCode) -> None:
    """
    The code is what a translation catalogue is keyed by, so its shape is part of the contract.

    It must not be the sentence: a code that carried prose would be as untranslatable as the message
    it was meant to replace, and renaming it later would break every client that already maps it.
    """
    assert code.value == code.name
    assert code.value.isupper()
    assert code.value.replace("_", "").isalnum()
