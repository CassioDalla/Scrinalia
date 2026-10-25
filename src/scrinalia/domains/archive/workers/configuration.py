"""Effective configuration of a worker: precedence, validation and the resolved dictionary.

Both entry points need the same answer — the runner (before it executes) and the operations panel
(before it shows or saves) — so the rules live here once:

    explicit argument  >  persisted override  >  the worker's signature default

The engine is resolved **without instantiating it**: the panel has to answer "with which model will
this run?" for a worker that may never have run, and loading spaCy or torch to read a preset would
make the screen cost more than the run.

**What a worker accepts is its signature, and only its signature.** A key the worker does not declare
is refused at write time, which is what stops ``{"colunas_to_classify": [...]}`` from being persisted
as a default and reaching the engine constructor as a ``TypeError`` much later (#120). The columns an
AI worker may read are not a second list: they are :data:`AI_TEXT_COLUMNS`, the same tuple the SQL
composition reads and the evaluation benches check. The one deliberate exception is
:func:`validate_engine_options`: a raw pass-through to the engine constructor, per run, named
``engine_options`` — used by an operator who knows the library, never persisted as a default.
"""

from __future__ import annotations

import types
from dataclasses import dataclass, field
from functools import cache
from inspect import Parameter
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from sqlalchemy.orm import Session

from scrinalia.domains.archive.domain.text_quality import AI_TEXT_COLUMNS, unknown_ai_columns
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError
from scrinalia.domains.archive.models.operations import WorkerSetting
from scrinalia.domains.archive.workers.catalogue import (
    WorkerSpec,
    accepts_extra_kwargs,
    axis_registry,
    worker_module,
    worker_signature,
)

#: Parameters of ``execute`` that are not options a JSON request can carry: the session the runner
#: opens, the runner dataclass (``NerRunnerConfig``/``TypologyRunnerConfig``) and the ports
#: (``source``, ``storage``). ``config`` reaching ``execute`` as a dict would fail with an attribute
#: error instead of a sentence, and a port cannot travel through JSON at all.
NON_OPTION_PARAMETERS: frozenset[str] = frozenset({"db", "db_session", "config", "source", "storage", "run_control"})

#: Why each of them is refused, as the fragment the refusal sentence adds.
NON_OPTION_REASONS: dict[str, str] = {
    "config": "é um objeto do runner e não pode ser definida pela tela",
    "source": "é a porta de origem do staging e não pode ser definida pela tela",
    "storage": "é a porta de armazenamento e não pode ser definida pela tela",
    "db": "é a sessão de banco que o runner abre",
    "db_session": "é a sessão de banco que o runner abre",
    "run_control": "é o controle de cancelamento da execução, não uma opção do worker",
}

#: Parameters that already have a field of their own in the configuration. Accepting them inside
#: ``options`` would be a second definition of the same value: the runner forwards ``extra`` *after*
#: the resolved argument, so a ``{"db_batch_size": 8}`` could silently win over the field.
SEPARATE_OPTIONS: frozenset[str] = frozenset({"engine_name", "preset", "db_batch_size"})

#: The options that describe **one execution** and not a persisted default. ``limit`` caps a run; a
#: cap that outlived the command would be a trap, which is why the CLI documents it as unrunnable
#: from a default and why the settings write refuses it (#120).
RUN_ONLY_OPTIONS: frozenset[str] = frozenset({"limit"})

#: The one definition of the columns an AI worker may read, per option name. The benches read
#: ``AI_TEXT_COLUMNS`` through the same helper (:func:`unknown_ai_columns`), so a typo is refused by
#: the same rule wherever it is typed.
COLUMN_OPTIONS: dict[str, tuple[str, ...]] = {
    "columns_to_extract": AI_TEXT_COLUMNS,
    "columns_to_classify": AI_TEXT_COLUMNS,
}

#: What kind of control an option needs. ``columns`` is a list whose values are enumerated;
#: ``list`` is a list with no catalogue to pick from (a free list of strings).
OptionKind = Literal["boolean", "integer", "number", "text", "list", "columns"]

#: Where an option is admissible. ``setting`` is a default that belongs to the row, ``run`` is one
#: execution only, ``both`` is either.
OptionScope = Literal["setting", "run", "both"]


@dataclass(frozen=True)
class ResolvedWorkerConfig:
    """What a run will actually use, and what the panel shows."""

    engine_name: str | None
    preset: str | None
    db_batch_size: int | None
    #: Parameters the worker declares (``columns_to_extract``, ``force``, ...).
    worker_options: dict[str, Any] = field(default_factory=dict)
    #: Everything else, forwarded to the engine constructor (``device``, ``host``, ...).
    engine_kwargs: dict[str, Any] = field(default_factory=dict)
    #: ``describe_config`` output: model, device, host, dimensions — never an instance.
    config: dict[str, Any] = field(default_factory=dict)
    note: str | None = None

    @property
    def forwarded_options(self) -> dict[str, Any]:
        """Both halves, as the runner's ``extra`` mapping expects them."""
        return {**self.worker_options, **self.engine_kwargs}


@dataclass(frozen=True)
class DeclaredOption:
    """
    One option the worker's ``execute`` declares, as the contract publishes it.

    It is derived from the signature and nothing else: the name and the default are the worker's own
    declaration, the kind is the type it already wrote, and ``choices`` is the catalogue the option
    is defined against (:data:`COLUMN_OPTIONS`). The screen renders a control from this, so the form
    cannot offer a key the worker would refuse.
    """

    name: str
    kind: OptionKind
    scope: OptionScope
    default: Any = None
    choices: tuple[str, ...] = ()


def declared_parameters(spec: WorkerSpec) -> dict[str, Parameter]:
    """The parameters ``execute`` declares by name, excluding ``**kwargs``."""
    return {
        name: parameter
        for name, parameter in worker_signature(spec).parameters.items()
        if parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
    }


def _type_hints(module_path: str) -> dict[str, Any]:
    """
    The resolved annotations of ``execute``.

    Every worker module uses ``from __future__ import annotations``, so the annotation of a parameter
    is the *string* ``"int | None"`` and not the type. Resolving it is read-only, cheap and cached.
    """
    return get_type_hints(worker_module(module_path).execute)


def _strip_optional(annotation: Any) -> tuple[Any, ...]:
    """The members of an annotation without ``None``: ``float | None`` -> ``(float,)``."""
    if annotation is Parameter.empty:
        return ()
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return tuple(member for member in get_args(annotation) if member is not type(None))
    return (annotation,)


def _kind_of(value: Any) -> OptionKind | None:
    """The control a value (or a type) needs; ``None`` when it is not a JSON-settable option."""
    # ``bool`` before ``int``: Python's ``bool`` is an ``int``, and a checkbox is not a number field.
    if value is bool or isinstance(value, bool):
        return "boolean"
    if value is int or isinstance(value, int):
        return "integer"
    if value is float or isinstance(value, float):
        return "number"
    if value is str or isinstance(value, str):
        return "text"
    if value is list or value is tuple or isinstance(value, (list, tuple)) or get_origin(value) in (list, tuple):
        return "list"
    return None


def _option_kind(name: str, parameter: Parameter, annotation: Any) -> OptionKind:
    if name in COLUMN_OPTIONS:
        return "columns"
    if parameter.default is not Parameter.empty and parameter.default is not None:
        kind = _kind_of(parameter.default)
        if kind is not None:
            return kind
    for member in _strip_optional(annotation):
        kind = _kind_of(member)
        if kind is not None:
            return kind
    # A parameter typed with something exotic (a callable, a dataclass) is not a JSON option; the
    # signature is still the definition, so it is published as text and the write path refuses a
    # value that is not a string.
    return "text"


@cache
def declared_options(spec: WorkerSpec) -> tuple[DeclaredOption, ...]:
    """The options the worker accepts, derived from its signature once per process."""
    annotations = _type_hints(spec.module)
    options: list[DeclaredOption] = []
    for name, parameter in declared_parameters(spec).items():
        if name in NON_OPTION_PARAMETERS or name in SEPARATE_OPTIONS:
            continue
        options.append(
            DeclaredOption(
                name=name,
                kind=_option_kind(name, parameter, annotations.get(name, parameter.annotation)),
                scope="run" if name in RUN_ONLY_OPTIONS else "both",
                default=None if parameter.default is Parameter.empty else parameter.default,
                choices=COLUMN_OPTIONS.get(name, ()),
            )
        )
    return tuple(options)


def _validate_value(spec: WorkerSpec, option: DeclaredOption, value: Any) -> None:
    """Rejects a value the declared option cannot carry, before it is persisted or run."""
    label = option.name
    if option.kind == "boolean":
        if not isinstance(value, bool):
            raise InvalidWorkerSettingsError(f"A opção '{label}' é booleana: use true ou false, não {value!r}.")
        return
    if option.kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidWorkerSettingsError(f"A opção '{label}' espera um inteiro, não {value!r}.")
        return
    if option.kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidWorkerSettingsError(f"A opção '{label}' espera um número, não {value!r}.")
        return
    if option.kind == "text":
        if not isinstance(value, str):
            raise InvalidWorkerSettingsError(f"A opção '{label}' espera texto, não {value!r}.")
        return
    # ``list`` and ``columns``: the value has to be a list of strings, and for a column list every
    # name has to be one the AI text has — read from the same tuple the benches read.
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InvalidWorkerSettingsError(f"A opção '{label}' espera uma lista de nomes, não {value!r}.")
    if option.kind == "columns":
        if not value:
            raise InvalidWorkerSettingsError(
                f"A opção '{label}' não pode ser vazia: sem coluna o worker não teria texto para ler."
            )
        unknown = unknown_ai_columns(value)
        if unknown:
            raise InvalidWorkerSettingsError(
                f"A opção '{label}' nomeia colunas que o texto da IA não tem: {unknown}. "
                f"Conhecidas: {list(option.choices)}."
            )


def validate_options(spec: WorkerSpec, options: dict[str, Any]) -> None:
    """
    Rejects an option the worker would not accept, and a value the option cannot carry.

    A key the worker does not declare is refused, ``**engine_kwargs`` notwithstanding: that door is
    the raw pass-through of :func:`validate_engine_options`, which is a deliberate choice of the
    caller and never of a persisted default. The sentence names the declared options, and — for a
    worker that has the door — says where a pass-through belongs.
    """
    declared = {option.name: option for option in declared_options(spec)}

    for key, value in options.items():
        if key in NON_OPTION_PARAMETERS:
            raise InvalidWorkerSettingsError(
                f"A opção '{key}' {NON_OPTION_REASONS.get(key, 'não pode ser definida pela tela')}; "
                "use as opções declaradas pelo worker."
            )
        if key in SEPARATE_OPTIONS:
            raise InvalidWorkerSettingsError(
                f"A opção '{key}' tem campo próprio na configuração e não se define em 'options'."
            )
        option = declared.get(key)
        if option is None:
            sentence = f"O worker '{spec.name}' não aceita a opção '{key}'. Opções: {sorted(declared)}."
            if accepts_extra_kwargs(spec):
                sentence += (
                    " Para passar um parâmetro ao construtor do engine, use um repasse ao engine "
                    "('--engine-option' na linha de comando, ou o bloco avançado do painel de execução)."
                )
            raise InvalidWorkerSettingsError(sentence)
        _validate_value(spec, option, value)


def validate_settings_options(spec: WorkerSpec, options: dict[str, Any]) -> None:
    """
    Rejects a **persisted** default the worker would accept for one run only.

    ``limit`` caps one execution; a row that carried it would cap every execution and nobody would
    see why the pipeline stopped at N units. The run path keeps accepting it (``validate_options``).
    """
    validate_options(spec, options)
    run_only = sorted(key for key in options if key in RUN_ONLY_OPTIONS)
    if run_only:
        raise InvalidWorkerSettingsError(
            f"{run_only} valem para uma execução e não para um padrão: use o painel de execução "
            "(ou '--limit' na linha de comando)."
        )


def validate_engine_options(spec: WorkerSpec, engine_options: dict[str, Any]) -> None:
    """
    Validates the **named exception**: the raw pass-through to the engine constructor.

    Its keys are deliberately not enumerated — the declaration of what an engine constructor takes is
    the library's, and inventing a second one here would be the drift #120 is about. What is enforced
    is the boundary: only a worker that ends in ``**engine_kwargs`` has the door, and a key that is a
    worker option (or one of its fields) belongs in ``options``, not here. The value is the engine's
    to validate; a wrong one fails where the engine is built, with the engine's own sentence.
    """
    if not engine_options:
        return
    if not accepts_extra_kwargs(spec):
        raise InvalidWorkerSettingsError(f"O worker '{spec.name}' não repassa parâmetros ao construtor do engine.")
    declared = {option.name for option in declared_options(spec)}
    for key in engine_options:
        if key in NON_OPTION_PARAMETERS or key in SEPARATE_OPTIONS or key in declared:
            raise InvalidWorkerSettingsError(
                f"O repasse '{key}' é uma opção declarada do worker: use 'options', não 'engine_options'."
            )


def validate_engine_choice(spec: WorkerSpec, engine_name: str | None, preset: str | None) -> None:
    """Rejects an engine/preset that does not exist, or a worker that does not take one."""
    if spec.engine_source != "signature":
        if engine_name is not None or preset is not None:
            raise InvalidWorkerSettingsError(
                f"A engine do worker '{spec.name}' não é configurável aqui: "
                + (
                    "ela vive na regra LLM_CHECK ativa (tela de regras)."
                    if spec.engine_source == "llm_check_rule"
                    else "este worker não carrega modelo."
                )
            )
        return

    registry = axis_registry(spec.axis)
    if engine_name is not None and engine_name not in registry.AVAILABLE_ENGINES:
        raise InvalidWorkerSettingsError(
            f"Engine '{engine_name}' não existe para o eixo {spec.axis}. Opções: {sorted(registry.AVAILABLE_ENGINES)}."
        )
    # A retired preset is not merely unknown: it was declared and cannot run, and the reason is what
    # turns "did you mistype?" into "use this instead" (#122). The axis is read through ``getattr``
    # because only the axes that name an Ollama model have presets to retire.
    retired_presets: dict[str, str] = getattr(registry, "RETIRED_PRESETS", {})
    if preset is not None and preset in retired_presets:
        raise InvalidWorkerSettingsError(f"Preset '{preset}' foi aposentado: {retired_presets[preset]}")
    if preset is not None and preset not in registry.PRESETS:
        raise InvalidWorkerSettingsError(
            f"Preset '{preset}' não existe para o eixo {spec.axis}. Opções: {sorted(registry.PRESETS)}."
        )


def _active_llm_check_rule(db: Session) -> Any | None:
    """The rule that decides the quality validator's engine; read here so the panel cannot invent one."""
    from scrinalia.domains.archive.repository.cleaning_repo import CleaningRepository

    rules = CleaningRepository(db).get_active_rules("LLM_CHECK")
    return rules[0] if rules else None


def _default_preset(declared: dict[str, Parameter], registry: Any) -> str | None:
    """
    The preset a stale configuration falls back to when its own retired (#122).

    The worker's signature default when it declares one (``conflict-judge``), and otherwise the
    axis's first declared preset — which is the only one there is for the axes that can retire a
    preset, because a retirement is about an Ollama model and those axes name exactly one model.
    """
    if "preset" in declared:
        return str(declared["preset"].default)
    return next(iter(registry.PRESETS), None)


def _clean_persisted_options(spec: WorkerSpec, options: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    """
    The persisted defaults this worker can still honour, and a note for every one it cannot.

    The read path must survive what the write path refuses, for the same reason a retired preset
    falls back instead of taking the panel down (#122): a row written before this rule is not a new
    mistake, and resolving it strictly would make the whole panel answer 500. The row is healed the
    next time somebody saves it, because the screen only writes the fields it shows.
    """
    declared = {option.name: option for option in declared_options(spec)}
    kept: dict[str, Any] = {}
    for key, value in options.items():
        if key in RUN_ONLY_OPTIONS:
            notes.append(f"Padrão salvo ignorado — a opção '{key}' vale para uma execução e não para um padrão.")
            continue
        option = declared.get(key)
        if option is None:
            notes.append(
                f"Padrão salvo ignorado — a opção '{key}' não é declarada por este worker; "
                "repasses ao engine valem por execução."
            )
            continue
        try:
            _validate_value(spec, option, value)
        except InvalidWorkerSettingsError as error:
            notes.append(f"Padrão salvo ignorado — {error}")
            continue
        kept[key] = value
    return kept


def resolve_configuration(
    db: Session,
    spec: WorkerSpec,
    setting: WorkerSetting | None = None,
    *,
    engine_name: str | None = None,
    preset: str | None = None,
    db_batch_size: int | None = None,
    options: dict[str, Any] | None = None,
    engine_options: dict[str, Any] | None = None,
) -> ResolvedWorkerConfig:
    """
    Applies the precedence and returns the resolved configuration.

    ``setting`` is the persisted override (or ``None``); the keyword arguments are the explicit
    choice of this call. Everything the caller does not name falls back to the override and then to
    the signature default.
    """
    # The explicit choice of *this call* is validated here, next to ``validate_options`` below and
    # for the same reason: the CLI resolves its configuration through this function too, so a
    # refusal that only the panel makes is not a guarantee — ``--engine`` used to reach a worker
    # whose engine lives in the active LLM_CHECK rule and override it silently. The persisted
    # override is validated where it is written (``WorkerOperationsService.update_settings``) and
    # read leniently below, because an old row is not a new mistake.
    validate_engine_choice(spec, engine_name, preset)
    explicit_options = dict(options or {})
    explicit_engine_options = dict(engine_options or {})
    validate_options(spec, explicit_options)
    validate_engine_options(spec, explicit_engine_options)

    notes: list[str] = []
    override_options = _clean_persisted_options(spec, dict(setting.options or {}), notes) if setting is not None else {}
    merged_options = {**override_options, **explicit_options}

    declared = declared_parameters(spec)
    worker_options = {key: value for key, value in merged_options.items() if key in declared}
    engine_kwargs = {
        **{key: value for key, value in merged_options.items() if key not in declared},
        **explicit_engine_options,
    }

    resolved_engine = engine_name if engine_name is not None else (setting.engine_name if setting else None)
    resolved_preset = preset if preset is not None else (setting.preset if setting else None)

    if spec.engine_source == "signature":
        resolved_engine = resolved_engine or declared["engine_name"].default
        resolved_preset = resolved_preset or declared["preset"].default
    elif spec.engine_source == "llm_check_rule":
        rule = _active_llm_check_rule(db)
        if rule is None:
            resolved_engine = resolved_preset = None
            notes.append("Nenhuma regra LLM_CHECK ativa: a validação roda sem modelo.")
        else:
            resolved_engine = resolved_engine or rule.engine_name or "ollama_title_check"
            resolved_preset = resolved_preset or rule.preset
    else:
        resolved_engine = resolved_preset = None

    resolved_batch = db_batch_size if db_batch_size is not None else (setting.db_batch_size if setting else None)
    if resolved_batch is None and "db_batch_size" in declared:
        resolved_batch = declared["db_batch_size"].default

    config: dict[str, Any] = {}
    if spec.axis and resolved_engine:
        registry = axis_registry(spec.axis)
        # A *persisted* row or an active ``LLM_CHECK`` rule can still name a preset that retired
        # (#122). The write path refuses the name, so this is a stale row, not a new mistake — and a
        # stale row must not take the operations panel down: the read falls back to the worker's own
        # default and says why. The explicit ``--preset``/request of this call never reaches here
        # retired, because ``validate_engine_choice`` above already refused it.
        retired_presets: dict[str, str] = getattr(registry, "RETIRED_PRESETS", {})
        if resolved_preset in retired_presets:
            fallback = _default_preset(declared, registry)
            notes.append(
                f"O preset '{resolved_preset}' foi aposentado e esta configuração usa '{fallback}': "
                f"{retired_presets[resolved_preset]}"
            )
            resolved_preset = fallback
        config = registry.describe_config(resolved_engine, resolved_preset, **engine_kwargs)

    return ResolvedWorkerConfig(
        engine_name=resolved_engine,
        preset=resolved_preset,
        db_batch_size=resolved_batch,
        worker_options=worker_options,
        engine_kwargs=engine_kwargs,
        config=config,
        note=" ".join(notes) if notes else None,
    )


def effective_worker_options(spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> dict[str, Any]:
    """
    The option values a run really uses, for the ledger to record (#120).

    ``resolved.worker_options`` carries only what somebody named; the value the worker will really
    use is the named one, else the signature default, else — for the options whose default lives in
    the worker's own runner dataclass, like the columns a run reads — whatever the worker resolves.
    That last step is why the spec may name an ``option_resolver``: it calls the same helper
    ``execute`` calls, so the ledger records the run and not a second interpretation of it.
    """
    declared = declared_parameters(spec)
    values: dict[str, Any] = {}
    for name, parameter in declared.items():
        if name in NON_OPTION_PARAMETERS or name in SEPARATE_OPTIONS:
            continue
        if name in resolved.worker_options:
            values[name] = resolved.worker_options[name]
        elif parameter.default is not Parameter.empty and parameter.default is not None:
            values[name] = parameter.default
    if spec.option_resolver is not None:
        resolver = getattr(worker_module(spec.module), spec.option_resolver)
        values.update(resolver(**values))
    return values
