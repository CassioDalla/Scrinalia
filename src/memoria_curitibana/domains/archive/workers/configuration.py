"""Effective configuration of a worker: precedence, validation and the resolved dictionary.

Both entry points need the same answer — the runner (before it executes) and the operations panel
(before it shows or saves) — so the rules live here once:

    explicit argument  >  persisted override  >  the worker's signature default

The engine is resolved **without instantiating it**: the panel has to answer "with which model will
this run?" for a worker that may never have run, and loading spaCy or torch to read a preset would
make the screen cost more than the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from inspect import Parameter
from typing import Any

from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.exceptions import InvalidWorkerSettingsError
from memoria_curitibana.domains.archive.models.operations import WorkerSetting
from memoria_curitibana.domains.archive.workers.catalogue import WorkerSpec, axis_registry, worker_signature

#: The one option name the panel refuses. ``config`` is a runner dataclass (``NerRunnerConfig`` and
#: friends), not a value a JSON request can carry, and a dict reaching ``execute`` would fail with an
#: attribute error instead of a sentence.
RESERVED_OPTIONS = frozenset({"config"})


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


def declared_parameters(spec: WorkerSpec) -> dict[str, Parameter]:
    """The parameters ``execute`` declares by name, excluding ``**kwargs``."""
    return {
        name: parameter
        for name, parameter in worker_signature(spec).parameters.items()
        if parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
    }


def _accepts_extra_kwargs(spec: WorkerSpec) -> bool:
    return any(parameter.kind is Parameter.VAR_KEYWORD for parameter in worker_signature(spec).parameters.values())


def validate_options(spec: WorkerSpec, options: dict[str, Any]) -> None:
    """
    Rejects an option the worker would not accept.

    A key the worker does not declare is only valid when it has ``**engine_kwargs`` — that is the
    documented way to override ``device`` or ``host`` per run.
    """
    declared = declared_parameters(spec)
    accepts_extra = _accepts_extra_kwargs(spec)

    for key in options:
        if key in RESERVED_OPTIONS:
            raise InvalidWorkerSettingsError(
                f"A opção '{key}' é um objeto do runner e não pode ser definida pela tela; "
                "use as opções declaradas pelo worker."
            )
        if key not in declared and not accepts_extra:
            raise InvalidWorkerSettingsError(
                f"O worker '{spec.name}' não aceita a opção '{key}'. Opções: {sorted(declared)}."
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
    if preset is not None and preset not in registry.PRESETS:
        raise InvalidWorkerSettingsError(
            f"Preset '{preset}' não existe para o eixo {spec.axis}. Opções: {sorted(registry.PRESETS)}."
        )


def _active_llm_check_rule(db: Session) -> Any | None:
    """The rule that decides the quality validator's engine; read here so the panel cannot invent one."""
    from memoria_curitibana.domains.archive.repository.cleaning_repo import CleaningRepository

    rules = CleaningRepository(db).get_active_rules("LLM_CHECK")
    return rules[0] if rules else None


def resolve_configuration(
    db: Session,
    spec: WorkerSpec,
    setting: WorkerSetting | None = None,
    *,
    engine_name: str | None = None,
    preset: str | None = None,
    db_batch_size: int | None = None,
    options: dict[str, Any] | None = None,
) -> ResolvedWorkerConfig:
    """
    Applies the precedence and returns the resolved configuration.

    ``setting`` is the persisted override (or ``None``); the keyword arguments are the explicit
    choice of this call. Everything the caller does not name falls back to the override and then to
    the signature default.
    """
    override_options = dict(setting.options or {}) if setting is not None else {}
    merged_options = {**override_options, **(options or {})}
    validate_options(spec, merged_options)

    declared = declared_parameters(spec)
    worker_options = {key: value for key, value in merged_options.items() if key in declared}
    engine_kwargs = {key: value for key, value in merged_options.items() if key not in declared}

    resolved_engine = engine_name if engine_name is not None else (setting.engine_name if setting else None)
    resolved_preset = preset if preset is not None else (setting.preset if setting else None)
    note = None

    if spec.engine_source == "signature":
        resolved_engine = resolved_engine or declared["engine_name"].default
        resolved_preset = resolved_preset or declared["preset"].default
    elif spec.engine_source == "llm_check_rule":
        rule = _active_llm_check_rule(db)
        if rule is None:
            resolved_engine = resolved_preset = None
            note = "Nenhuma regra LLM_CHECK ativa: a validação roda sem modelo."
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
        config = registry.describe_config(resolved_engine, resolved_preset, **engine_kwargs)

    return ResolvedWorkerConfig(
        engine_name=resolved_engine,
        preset=resolved_preset,
        db_batch_size=resolved_batch,
        worker_options=worker_options,
        engine_kwargs=engine_kwargs,
        config=config,
        note=note,
    )
