"""The trial executor and its gabarito read (ADR 0018, #71).

The trial is the one place that runs a model over the collection without writing it, so the tests
here pin the three promises the screen depends on: the configurations see the same sample, the
human revisions are read as the gabarito (and nothing else), and no archival column, stamp or review
row changes.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from scrinalia.domains.archive.evaluation import trial as trial_module
from scrinalia.domains.archive.evaluation.metrics import ABSTAINED
from scrinalia.domains.archive.models import ArchiveAIReviewQueue, ArchiveDocumentRevision
from scrinalia.domains.archive.schemas.system_schema import WorkerRunRequest, WorkerTrialRequest
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE

TYPOLOGY = "typology"
ENGINE = "deberta_typology"
PRESET = "cpu_local"


class FakeEngine:
    """A deterministic classifier: the title's subject decides the answer, the score is fixed."""

    def __init__(self, score: float = 0.90) -> None:
        self.score = score
        self.calls: list[list[str]] = []

    def classify(self, texts: Sequence[str], labels: Sequence[str], batch_size: int = 1) -> list[dict]:
        self.calls.append(list(texts))
        answers = ["Fotografia" if "foto" in text.lower() else "Planta" for text in texts]
        return [{"labels": [answer], "scores": [self.score]} for answer in answers]


def _config(threshold: float) -> WorkerRunRequest:
    return WorkerRunRequest(
        engine_name=ENGINE,
        preset=PRESET,
        db_batch_size=8,
        options={"confidence_threshold": threshold, "columns_to_classify": ["original_title"]},
    )


def _verdict(db_session, doc, typology_id: int | None, *, revision: int = 1) -> None:
    """A human decision about one description, as the dossier writes it."""
    db_session.add(
        ArchiveDocumentRevision(
            description_id=doc.description_id,
            changed_by="ana",
            changes={"typology_id": {"old": None, "new": typology_id}},
        )
    )
    db_session.commit()


@pytest.fixture()
def corpus(db_session, generate_typology, generate_archive_doc):
    foto = generate_typology(id=1, name="Fotografia")
    planta = generate_typology(id=2, name="Planta")
    docs = {
        "foto": generate_archive_doc(original_title="Foto da praça", review_status="HUMAN_APPROVED"),
        "planta": generate_archive_doc(original_title="Planta da casa", review_status="HUMAN_APPROVED"),
        "nenhuma": generate_archive_doc(original_title="Mapa antigo", review_status="HUMAN_APPROVED"),
        "sample_foto": generate_archive_doc(original_title="Foto do largo"),
        "sample_planta": generate_archive_doc(original_title="Planta do sobrado"),
    }
    _verdict(db_session, docs["foto"], foto.typology_id)
    _verdict(db_session, docs["planta"], planta.typology_id)
    _verdict(db_session, docs["nenhuma"], None)
    return docs


def test_the_trial_measures_the_gabarito_and_the_production_sample(db_session, corpus, monkeypatch):
    engine = FakeEngine()
    builds = 0

    def build(_resolved):
        nonlocal builds
        builds += 1
        return engine

    monkeypatch.setattr(trial_module, "_build_engine", build)
    request = WorkerTrialRequest(sample=10, seed="test-seed", configs=[_config(0.50), _config(0.95)])

    result = trial_module._typology_trial(db_session, WORKER_CATALOGUE[TYPOLOGY], request, trial_module.RunControl())

    # One sample, both configurations: the random sample is the ai-writable pair, and the three
    # verdicts are read whole because they are the hard set the gabarito exists for.
    assert sorted(result.sample.description_ids) == sorted(
        [corpus["sample_foto"].description_id, corpus["sample_planta"].description_id]
    )
    assert sorted(result.sample.verdict_ids) == sorted(
        [corpus["foto"].description_id, corpus["planta"].description_id, corpus["nenhuma"].description_id]
    )
    assert result.sample.verdicts_available == 3
    assert result.unknown_verdicts == []

    strict, lenient = result.configs
    assert strict.verdicts_scored == 3
    assert strict.agreement == pytest.approx(2 / 3)  # Foto and Planta right, NENHUMA wrong
    assert strict.coverage == pytest.approx(1.0)
    assert strict.abstention_rate == pytest.approx(0.0)
    assert strict.distribution == {"Fotografia": 1, "Planta": 1}

    assert lenient.verdicts_scored == 3
    assert lenient.agreement == pytest.approx(1 / 3)  # only NENHUMA is right when it abstains
    assert lenient.coverage == pytest.approx(0.0)
    assert lenient.abstention_rate == pytest.approx(1.0)
    assert lenient.distribution == {ABSTAINED: 2}

    # The engine is built once per (engine, preset) and both configurations see the same texts.
    assert builds == 1
    assert len(engine.calls) == 2
    assert sorted(engine.calls[0]) == sorted(engine.calls[1])

    # The result carries the body "use this configuration" writes, with the effective options.
    assert strict.settings.engine_name == ENGINE
    assert strict.settings.preset == PRESET
    assert strict.settings.options["confidence_threshold"] == 0.50
    assert strict.pending == 2  # the two ai-writable sample descriptions
    assert strict.projected_hours is not None


def test_the_trial_writes_no_archival_content(db_session, corpus, monkeypatch):
    monkeypatch.setattr(trial_module, "_build_engine", lambda _resolved: FakeEngine())
    request = WorkerTrialRequest(sample=10, seed="test-seed", configs=[_config(0.50), _config(0.90)])

    trial_module._typology_trial(db_session, WORKER_CATALOGUE[TYPOLOGY], request, trial_module.RunControl())

    for key in ("sample_foto", "sample_planta"):
        doc = corpus[key]
        db_session.refresh(doc)
        assert doc.typology_id is None, "the trial must not classify the production sample"
        assert not doc.execution_log, "the trial must not stamp what it read"
    assert db_session.query(ArchiveAIReviewQueue).count() == 0


def test_the_verdict_is_the_latest_human_revision(db_session, corpus):
    doc = corpus["foto"]
    _verdict(db_session, doc, 2)  # the person changed their mind: Planta is the latest decision

    verdicts = trial_module._read_verdicts(db_session)

    assert verdicts[doc.description_id] == "Planta"


def test_a_description_approved_without_a_revision_is_not_a_verdict(
    db_session, generate_archive_doc, generate_typology
):
    generate_typology(id=1, name="Fotografia")
    doc = generate_archive_doc(original_title="Foto da praça", review_status="HUMAN_APPROVED", typology_id=1)

    assert doc.description_id not in trial_module._read_verdicts(db_session)


def test_the_trial_registry_is_the_catalogue_flag() -> None:
    """
    The panel offers a trial for the workers the catalogue marks, and the executor runs exactly
    those. A worker with one and not the other is either a button that 500s or a hidden feature.
    """
    assert set(trial_module.TRIALS) == {name for name, spec in WORKER_CATALOGUE.items() if spec.trial}
