"""
Honest bench for the subject classifier (Fase 1.5, defeito 2/2 — entregável B1).

The previous plan claimed that turning the label into an NLI sentence fixes the
classification, and cited three measurements as proof (``alvenaria`` -> Urbanismo 0.536,
``residencial`` -> Urbanismo 0.604, ``eclético`` -> Urbanismo 0.424). A first probe could
not reproduce any of them, in any of twelve label-format/template combinations. The most
likely explanation is that the original experiment compared a *sentence* against *bare
names* — a mixed label set, where the sentence wins by lexical proximity rather than by
entailment, and the reported gain belongs to the arrangement rather than to the format.

This bench is built to answer that question instead of assuming it, and to do it on a
human-labelled set rather than on intuition:

* **Three arrangements per format.** ``sentence vs sentence``, ``sentence vs bare`` and
  ``bare vs bare``. If a format only wins in the mixed arrangement, the gain is an artefact
  and the table says so.
* **Two models, named by the registry.** ``mDeBERTa`` and ``xlm-roberta-large-xnli`` come from
  ``--config ENGINE[:PRESET]`` and are resolved through ``engines.classification.registry``. The
  bench names no model: a new model is a preset there, and the same registry is what both workers
  of the axis read, so every configuration compared here is one the worker can be told to run
  (issue #116).
* **Distribution next to accuracy.** The defect that started this was not low accuracy: it
  was 687 of 980 tags collapsing into one drawer. A model that scores 80% while stuffing
  60% of the tags into a single category is worse for the UI than one that scores 70% with
  a plausible spread, and the report prints both.

Nothing is written to the database. It reads the tags, sends them to the model in memory
and prints a table.

Run it from the repository root, against the real database and the real models::

    uv run python -m testing.evaluation.macro_category_quality
    uv run python -m testing.evaluation.macro_category_quality \\
        --config deberta_typology:cpu_local \\
        --config deberta_typology:xlm_roberta_local

The default is the configuration the macro-category worker itself declares, read from its
signature, so "the current configuration" cannot drift from the code. ``--device`` overrides the
preset's device for every configuration, which is the one engine parameter this bench needs to vary.

CPU is the default because that is what the worker runs on in production; a full run over
44 tags x 3 arrangements x 2 models is a few minutes, not a few hours.
"""

from __future__ import annotations

import argparse
import inspect
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import numpy as np

from scrinalia.core.logger import logger
from scrinalia.domains.archive.domain.vocabulary import SUBJECT_CATEGORIES
from scrinalia.domains.archive.engines.classification import registry as classification_registry
from scrinalia.domains.archive.engines.classification.registry import EngineName, PresetName
from scrinalia.domains.archive.workers.worker_macro_category import execute
from testing.evaluation.dataset import load_dataset

PAIRS_FILENAME = "macro_category_pairs.json"

#: Identifies the class of "this tag is not a subject at all". The deterministic guard in
#: ``domain.vocabulary`` decides it, not the model, so it is excluded from the model's
#: candidate labels and measured separately as a rule.
NONE_CLASS = "NENHUMA"


# =============================================================================
# Label formats
# =============================================================================


def label_bare(name: str) -> str:
    """The format the production worker used before this phase: the raw drawer name."""
    return name


def label_sentence(name: str) -> str:
    """The format the previous plan recommended: a short proposition around the drawer."""
    return f"um assunto sobre {name.lower()}"


def label_trata_de(name: str) -> str:
    """A second proposition phrasing, to check the gain is not tied to one wording."""
    return f"trata de {name.lower()}"


LABEL_FORMATS = {
    "bare": label_bare,
    "sentence": label_sentence,
    "trata_de": label_trata_de,
}

#: The three arrangements. The middle one is the suspected artefact.
ARRANGEMENTS = {
    # Every candidate label uses the format being tested — the honest comparison.
    "same_format": lambda fn, categories: [fn(name) for name in categories],
    # The tested format against bare names — what the previous plan most likely measured.
    "mixed_vs_bare": lambda fn, categories: [fn(categories[0]), *list(categories[1:])],
    # The baseline: bare names on both sides.
    "bare_vs_bare": lambda _fn, categories: list(categories),
}


# =============================================================================
# Metrics
# =============================================================================


@dataclass
class GoldenPair:
    """One labelled tag: what the model should answer, and why the curator says so."""

    name: str
    documents: int
    expected: str | None
    needs_decision: bool = False
    already_covered: bool = False

    @property
    def is_subject(self) -> bool:
        """A pair with ``expected=None`` is the NENHUMA class and never reaches the model."""
        return self.expected is not None


@dataclass
class BenchResult:
    """What one (configuration, format, arrangement) combination scored on the golden set."""

    config: str
    label_format: str
    arrangement: str

    correct: int = 0
    total: int = 0
    distribution: Counter = field(default_factory=Counter)
    confidences_correct: list[float] = field(default_factory=list)
    confidences_wrong: list[float] = field(default_factory=list)
    positive_control_hits: int = 0
    positive_control_total: int = 0
    misses: list[tuple[str, str, float]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def largest_share(self) -> tuple[str, float]:
        """The biggest drawer's share of the answers — the collapse symptom, as a number."""
        if not self.distribution:
            return ("", 0.0)
        label, count = self.distribution.most_common(1)[0]
        return (label, count / max(1, sum(self.distribution.values())))

    @property
    def mean_confidence(self) -> tuple[float, float]:
        """
        Mean confidence split by whether the answer was right.

        This is the calibration check the defect demands: if the wrong answers carry the same
        confidence as the right ones (``1924`` was wrong with 0.73), then the score cannot be
        used to route a tag to human review, and the report has to say so.
        """
        right = float(np.mean(self.confidences_correct)) if self.confidences_correct else 0.0
        wrong = float(np.mean(self.confidences_wrong)) if self.confidences_wrong else 0.0
        return (right, wrong)


def evaluate(
    classify,
    pairs: list[GoldenPair],
    categories: list[str],
    label_format: str,
    arrangement: str,
    config_label: str,
) -> BenchResult:
    """Runs one configuration over the golden set and keeps everything the decision needs."""
    result = BenchResult(config=config_label, label_format=label_format, arrangement=arrangement)

    subjects = [pair for pair in pairs if pair.is_subject]
    labels = ARRANGEMENTS[arrangement](LABEL_FORMATS[label_format], categories)

    # ``classify`` is called once per tag so the confidence always belongs to that tag; a
    # batched call would make the pairing fragile for no measurable speed gain at this size.
    for pair in subjects:
        verdict = classify(pair.name, labels)
        predicted = verdict["label"]
        score = float(verdict["score"])

        result.total += 1
        result.distribution[predicted] += 1

        if pair.already_covered:
            result.positive_control_total += 1

        if predicted == pair.expected:
            result.correct += 1
            result.confidences_correct.append(score)
            if pair.already_covered:
                result.positive_control_hits += 1
        else:
            result.confidences_wrong.append(score)
            result.misses.append((pair.name, pair.expected or NONE_CLASS, score))

    return result


def none_class_scores(pairs: list[GoldenPair], guard) -> tuple[int, int]:
    """
    Measures the deterministic guard on the pairs the curator marked as NENHUMA.

    Reported apart from the models on purpose: whether a tag is a subject at all is decided
    by a rule, not by an entailment score, and mixing the two would hide which mechanism is
    carrying the result.
    """
    expected_none = [pair for pair in pairs if not pair.is_subject]
    caught = sum(1 for pair in expected_none if not guard(pair.name))
    return (caught, len(expected_none))


# =============================================================================
# The model, from the registry
# =============================================================================


@dataclass(frozen=True)
class BenchConfig:
    """One configuration to measure: the ``(engine, preset)`` pair the worker's identity is signed with."""

    engine: str
    preset: str | None
    device: str | None = None

    @property
    def label(self) -> str:
        return f"{self.engine}:{self.preset or '-'}"

    @property
    def engine_kwargs(self) -> dict[str, Any]:
        """Only what this bench varies. The model always comes from the preset, never from here."""
        return {"device": self.device} if self.device else {}

    @property
    def model(self) -> str | None:
        """The model this configuration resolves to, so the report can name what really ran."""
        described = classification_registry.describe_config(
            cast("EngineName", self.engine), cast("PresetName", self.preset), **self.engine_kwargs
        )
        model = described.get("model")
        return model if isinstance(model, str) else None


def worker_default_config() -> str:
    """
    The configuration the macro-category worker runs with when nobody says otherwise.

    Retyping ``"deberta_typology:cpu_local"`` here would be a second definition of the worker's
    default, and the day it changes the bench would keep scoring the old one while calling it "the
    current configuration".
    """
    parameters = inspect.signature(execute).parameters
    preset = parameters["preset"].default
    engine = parameters["engine_name"].default
    return f"{engine}:{preset}" if preset else str(engine)


def parse_config(text: str, device: str | None = None) -> BenchConfig:
    """
    Reads ``engine[:preset]`` and refuses a name the registry does not have.

    The registry is the only source of models here, which is why an unknown name is a sentence before
    anything is loaded, and why a model that exists only in the registry becomes runnable without
    editing this script — the property the unit test pins.
    """
    parts = text.split(":")
    if len(parts) > 2:
        raise SystemExit(f"--config {text!r} has {len(parts)} fields; expected engine[:preset].")
    engine = parts[0].strip()
    if not engine:
        raise SystemExit(f"--config {text!r} names no engine.")
    preset = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None

    if engine not in classification_registry.AVAILABLE_ENGINES:
        raise SystemExit(
            f"--config {text!r} names an engine the axis does not have. "
            f"Known: {sorted(classification_registry.AVAILABLE_ENGINES)}"
        )
    if preset is not None and preset not in classification_registry.PRESETS:
        raise SystemExit(
            f"--config {text!r} names a preset the axis does not have. Known: {sorted(classification_registry.PRESETS)}"
        )
    return BenchConfig(engine=engine, preset=preset, device=device)


def engine_classifier(config: BenchConfig) -> Callable[[str, list[str]], dict]:
    """
    The engine of one configuration, adapted to the one text / one label set call this bench makes.

    The engine is the axis's own object: the bench builds no pipeline, so the model, its truncation
    and its device are exactly what the worker gets from the same ``(engine, preset)`` pair.
    """
    engine = classification_registry.get_engine(
        cast("EngineName", config.engine), cast("PresetName", config.preset), **config.engine_kwargs
    )

    def classify(text: str, labels: list[str]) -> dict:
        # One text per call so the confidence always belongs to that tag; the engine answers a list.
        result = engine.classify([text], labels, batch_size=1)[0]
        return {"label": result["labels"][0], "score": float(result["scores"][0])}

    return classify


# =============================================================================
# Report
# =============================================================================


def load_pairs(payload: dict) -> tuple[list[GoldenPair], list[str]]:
    pairs = [
        GoldenPair(
            name=item["name"],
            documents=item["documents"],
            expected=item["expected"],
            needs_decision=item.get("needs_decision", False),
            already_covered=item.get("already_covered", False),
        )
        for item in payload["pairs"]
    ]
    return pairs, payload["vocabulary"]


def to_markdown(results: list[BenchResult]) -> str:
    """The table the curator reads: accuracy next to the collapse symptom."""
    lines = [
        "| Configuração | Rótulo | Arranjo | Acurácia | Maior gaveta | Conf. certa | Conf. errada | Controle+ |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for r in sorted(results, key=lambda r: (-r.accuracy, r.largest_share[1])):
        label, share = r.largest_share
        right, wrong = r.mean_confidence
        control = f"{r.positive_control_hits}/{r.positive_control_total}" if r.positive_control_total else "—"
        lines.append(
            f"| `{r.config}` | {r.label_format} | {r.arrangement} | {r.accuracy:.3f} "
            f"| {label} ({share:.0%}) | {right:.3f} | {wrong:.3f} | {control} |"
        )
    return "\n".join(lines)


def run(
    configs: list[BenchConfig], formats: list[str], arrangements: list[str], limit: int | None
) -> tuple[dict, list[BenchResult]]:
    from scrinalia.domains.archive.domain.vocabulary import is_subject_candidate

    pairs, _vocabulary = load_pairs(load_dataset(PAIRS_FILENAME))
    if limit:
        # Keep the head of the list: it is the part that decides the navigation.
        pairs = pairs[:limit]

    categories = list(SUBJECT_CATEGORIES)
    logger.info(f"📋 {len(pairs)} labelled tags · {len(categories)} subject drawers")
    logger.info(
        f"🧪 {len(configs)} configuration(s) x {len(formats)} label format(s) x {len(arrangements)} arrangement(s)"
    )
    for config in configs:
        logger.info(f"   `{config.label}` resolves to {config.model}")

    caught, expected_none = none_class_scores(pairs, is_subject_candidate)
    logger.info(f"🛡️ deterministic guard on the NENHUMA pairs: {caught}/{expected_none}")

    results: list[BenchResult] = []
    for config in configs:
        logger.info(f"--- loading {config.label} ---")
        classify = engine_classifier(config)
        for label_format in formats:
            for arrangement in arrangements:
                logger.info(f"   running {config.label} / {label_format} / {arrangement}")
                results.append(evaluate(classify, pairs, categories, label_format, arrangement, config.label))

    report = {
        "tags_labelled": len(pairs),
        "tags_as_subject": sum(1 for pair in pairs if pair.is_subject),
        "guard": {"caught": caught, "expected_none": expected_none},
        "vocabulary": categories,
        "configurations": [
            {"config": c.label, "engine": c.engine, "preset": c.preset, "model": c.model} for c in configs
        ],
        "results": [
            {
                "config": r.config,
                "label_format": r.label_format,
                "arrangement": r.arrangement,
                "accuracy": r.accuracy,
                "distribution": dict(r.distribution),
                "largest_share": list(r.largest_share),
                "mean_confidence_correct": r.mean_confidence[0],
                "mean_confidence_wrong": r.mean_confidence[1],
                "positive_control": [r.positive_control_hits, r.positive_control_total],
                "misses": r.misses,
            }
            for r in results
        ],
    }
    # Returned alongside the JSON so the printed table keeps the per-tag confidences; going
    # through the serialised form would average an average and print a number that is not
    # the measurement.
    return report, results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Honest bench for the subject classifier.")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="ENGINE[:PRESET]",
        help="A configuration to measure, resolved through the classification registry; repeat to compare.",
    )
    parser.add_argument("--formats", nargs="+", default=list(LABEL_FORMATS), choices=list(LABEL_FORMATS))
    parser.add_argument("--arrangements", nargs="+", default=list(ARRANGEMENTS), choices=list(ARRANGEMENTS))
    parser.add_argument("--device", default=None, help="Override the preset's device: cpu or cuda:N.")
    parser.add_argument("--limit", type=int, default=None, help="Use only the first N labelled tags.")
    parser.add_argument("--json", type=Path, default=None, help="Also write the raw report here.")
    args = parser.parse_args(argv)

    configs = [parse_config(text, args.device) for text in (args.config or [worker_default_config()])]
    report, results = run(configs, args.formats, args.arrangements, args.limit)

    print()
    print(to_markdown(results))
    print()
    print(f"Guard determinístico nos pares NENHUMA: {report['guard']['caught']}/{report['guard']['expected_none']}")
    print()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"💾 report written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
