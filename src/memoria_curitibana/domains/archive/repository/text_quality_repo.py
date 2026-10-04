"""
Repository and SQL composition for the text-quality catalog.

Why the excerpt application is expressed in SQL and not in Python: the embedding worker
keys its idempotency stamp on an MD5 that PostgreSQL computes, so the "effective text"
must exist exactly once. If the worker removed the boilerplate in Python and the pending
query hashed the raw columns, every run would consider every document stale (or worse,
never). Building the composition as a SQL expression lets the read side (the stamp) and
the write side (the vector) share the same definition, and lets NER and typology read the
already-cleaned text from the database instead of reimplementing the rule.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, case, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.domain.text_quality import (
    AI_TEXT_COLUMNS,
    WHITESPACE_PATTERN,
    SuggestionCandidate,
    excerpt_fingerprint,
    normalize_excerpt,
)
from memoria_curitibana.domains.archive.models import ArchiveDocument, DomainTextTemplate
from memoria_curitibana.domains.archive.schemas.text_quality_schema import (
    TemplateCreateCommand,
    TemplateDryRunMatch,
    TemplateDryRunResponse,
    TemplateUpdateCommand,
    TextTemplateDTO,
)

#: Body columns embedded next to the title. The original worker used this order and the
#: stamp of every embedded document depends on it: reordering re-embeds the collection.
EMBEDDING_BODY_COLUMNS: tuple[str, ...] = ("scope_content", "admin_bio_history", "provenance")


@dataclass(frozen=True)
class ExcerptRule:
    """The minimum a SQL composition needs from a catalog row."""

    matchers: tuple[str, ...]
    replacement: str = ""


def excerpt_rules(templates: Sequence[TextTemplateDTO], scope: str | None = None) -> list[ExcerptRule]:
    """
    Active rules, in catalog order, ready to be applied by ``effective_column_sql``.

    ``scope`` selects the consumer asking for the text: an excerpt only takes part when
    its own scope includes that consumer, which is how a title template stays out of the
    embedded vector and inside the title suggestion.
    """
    return [
        ExcerptRule(matchers=tuple(template.matchers), replacement=template.replacement)
        for template in templates
        if template.applies and (scope is None or scope in template.scope)
    ]


def normalized_column_sql(column: str) -> ColumnElement[str]:
    """Whitespace-normalized value of a document column, computed by PostgreSQL."""
    if column not in AI_TEXT_COLUMNS:
        raise ValueError(f"'{column}' is not part of the AI text columns: {AI_TEXT_COLUMNS}")

    # The outer ``btrim`` mirrors ``normalize_excerpt``'s final ``.strip()``; the pattern is
    # the very same string Python compiles, so the two normalizations cannot drift.
    collapsed = func.regexp_replace(func.btrim(getattr(ArchiveDocument, column)), WHITESPACE_PATTERN, " ", "g")
    return cast(ColumnElement[str], func.btrim(collapsed))


def effective_column_sql(column: str, rules: Sequence[ExcerptRule]) -> ColumnElement[str]:
    """The column as the AI must read it: normalized, then every approved excerpt removed."""
    expression: ColumnElement[str] = normalized_column_sql(column)
    for rule in rules:
        for matcher in rule.matchers:
            expression = cast(ColumnElement[str], func.replace(expression, matcher, rule.replacement))

    # An excerpt ends where the separator begins ("Registros Fotográficos -" leaves
    # " Rua X"): trimming again keeps the effective text free of the residue.
    return cast(ColumnElement[str], func.btrim(expression))


def effective_title_sql(rules: Sequence[ExcerptRule]) -> ColumnElement[str]:
    """
    The title the AI reads: the human ``final_title`` when present, the original otherwise.

    A prefix template approved for the title (``"Registros Fotográficos - "``) is applied
    to both spellings, so the embedding receives the specific part of the title.
    """
    final = func.nullif(effective_column_sql("final_title", rules), "")
    original = effective_column_sql("original_title", rules)
    return cast(ColumnElement[str], func.coalesce(final, original))


def embedding_text_sql(rules: Sequence[ExcerptRule]) -> ColumnElement[str]:
    """The exact text handed to the embedding model (and hashed for the idempotency stamp)."""
    parts: list[ColumnElement[str]] = [func.nullif(effective_title_sql(rules), "")]
    parts.extend(func.nullif(effective_column_sql(column, rules), "") for column in EMBEDDING_BODY_COLUMNS)
    return cast(ColumnElement[str], func.concat_ws("\n", *parts))


def embedding_hash_sql(rules: Sequence[ExcerptRule]) -> ColumnElement[str]:
    """MD5 of the effective text, computed by PostgreSQL (the embedding stamp)."""
    return cast(ColumnElement[str], func.md5(embedding_text_sql(rules)))


def composed_text_sql(
    columns: Sequence[str], rules: Sequence[ExcerptRule], separator: str = ". "
) -> ColumnElement[str]:
    """Effective text of the requested columns joined for an AI worker (NER, typology)."""
    parts = [func.nullif(effective_column_sql(column, rules), "") for column in columns]
    return cast(ColumnElement[str], func.concat_ws(separator, *parts))


def apply_excerpts_in_python(text: str | None, rules: Sequence[ExcerptRule]) -> str:
    """
    Mirror of ``effective_column_sql`` for values already loaded as Python strings.

    Used by the read side (the derived title), where adding the expression to every query
    would buy nothing. An integration test pins it against the SQL expression on real rows,
    so the mirror cannot silently drift; the idempotency stamps never use this path.
    """
    value = normalize_excerpt(text or "")
    for rule in rules:
        for matcher in rule.matchers:
            value = value.replace(matcher, rule.replacement or "")
    return value.strip()


class TextQualityRepository:
    """Catalog persistence plus the document scans the curation needs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ==========================================
    # CATALOG READS
    # ==========================================

    def list_templates(self, status: str | None = None, only_active: bool = False) -> list[TextTemplateDTO]:
        stmt = select(DomainTextTemplate)
        if status is not None:
            stmt = stmt.where(DomainTextTemplate.status == status)
        if only_active:
            stmt = stmt.where(DomainTextTemplate.is_active.is_(True))
        stmt = stmt.order_by(DomainTextTemplate.status, DomainTextTemplate.occurrence_count.desc())
        return [TextTemplateDTO.model_validate(row) for row in self.db.scalars(stmt).all()]

    def get_template(self, template_id: int) -> TextTemplateDTO | None:
        row = self.db.scalars(
            select(DomainTextTemplate).where(DomainTextTemplate.template_id == template_id)
        ).one_or_none()
        return TextTemplateDTO.model_validate(row) if row else None

    def get_active_templates(self) -> list[TextTemplateDTO]:
        """Every row the AI composition must apply right now."""
        stmt = (
            select(DomainTextTemplate)
            .where(DomainTextTemplate.status == "APPROVED", DomainTextTemplate.is_active.is_(True))
            .order_by(DomainTextTemplate.template_id)
        )
        return [TextTemplateDTO.model_validate(row) for row in self.db.scalars(stmt).all()]

    def get_active_rules(self, scope: str | None = None) -> list[ExcerptRule]:
        """Convenience wrapper: the active catalog already converted to SQL rules."""
        return excerpt_rules(self.get_active_templates(), scope=scope)

    # ==========================================
    # CATALOG WRITES
    # ==========================================

    def create_template(self, command: TemplateCreateCommand) -> TextTemplateDTO:
        """A human-authored excerpt is born approved: the curator already decided."""
        text = normalize_excerpt(command.text)
        row = DomainTextTemplate(
            text=text,
            fingerprint=excerpt_fingerprint(text),
            variants=[normalize_excerpt(variant) for variant in command.variants if normalize_excerpt(variant)],
            scope=list(command.scope),
            action=command.action,
            replacement=command.replacement,
            reason=command.reason,
            source="HUMAN",
            status="APPROVED",
            is_active=True,
            created_by=command.created_by,
        )
        self.db.add(row)
        self.db.flush()
        return TextTemplateDTO.model_validate(row)

    def upsert_suggestions(self, candidates: Sequence[SuggestionCandidate]) -> int:
        """
        Persists suggestions idempotently, without ever touching a human decision.

        The ``WHERE`` on the conflict target is the whole point: re-running the frequency
        routine refreshes the evidence of a candidate that is still pending, and leaves an
        approved or rejected one exactly as the archivist left it.
        """
        if not candidates:
            return 0

        rows = [
            {
                "text": normalize_excerpt(candidate.text),
                "fingerprint": excerpt_fingerprint(candidate.text),
                "variants": [normalize_excerpt(variant) for variant in candidate.variants],
                "scope": list(candidate.scope),
                "action": "IGNORE",
                "replacement": "",
                "source": "SUGGESTED",
                "status": "SUGGESTED",
                "is_active": False,
                "occurrence_count": candidate.occurrence_count,
                "sample_document_ids": candidate.sample_document_ids,
            }
            for candidate in candidates
            if normalize_excerpt(candidate.text)
        ]

        if not rows:
            return 0

        stmt = (
            insert(DomainTextTemplate)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["fingerprint"],
                set_={
                    "variants": insert(DomainTextTemplate).excluded.variants,
                    "occurrence_count": insert(DomainTextTemplate).excluded.occurrence_count,
                    "sample_document_ids": insert(DomainTextTemplate).excluded.sample_document_ids,
                },
                where=(DomainTextTemplate.status == "SUGGESTED"),
            )
            .returning(DomainTextTemplate.template_id)
        )
        return len(self.db.execute(stmt).all())

    def update_template(self, template_id: int, command: TemplateUpdateCommand) -> TextTemplateDTO | None:
        """Applies a partial edit (approve, correct, deactivate, reject)."""
        row = self.db.scalars(
            select(DomainTextTemplate).where(DomainTextTemplate.template_id == template_id)
        ).one_or_none()
        if row is None:
            return None

        changes = command.model_dump(exclude_unset=True, exclude={"changed_by"})
        if "text" in changes and changes["text"] is not None:
            changes["text"] = normalize_excerpt(changes["text"])
            changes["fingerprint"] = excerpt_fingerprint(changes["text"])
        if "variants" in changes and changes["variants"] is not None:
            changes["variants"] = [normalize_excerpt(v) for v in changes["variants"] if normalize_excerpt(v)]
        if command.changed_by:
            row.created_by = row.created_by or command.changed_by

        for field, value in changes.items():
            setattr(row, field, value)

        self.db.flush()
        return TextTemplateDTO.model_validate(row)

    def delete_template(self, template_id: int) -> TextTemplateDTO | None:
        """Removes the decision from the catalog; the caller owns the retroactive effect."""
        row = self.db.scalars(
            select(DomainTextTemplate).where(DomainTextTemplate.template_id == template_id)
        ).one_or_none()
        if row is None:
            return None

        snapshot = TextTemplateDTO.model_validate(row)
        self.db.delete(row)
        self.db.flush()
        return snapshot

    def refresh_occurrence_count(self, template_id: int, occurrence_count: int) -> TextTemplateDTO | None:
        """Stores the measured evidence of an approved excerpt (documents it actually affects)."""
        row = self.db.scalars(
            select(DomainTextTemplate).where(DomainTextTemplate.template_id == template_id)
        ).one_or_none()
        if row is None:
            return None

        row.occurrence_count = occurrence_count
        self.db.flush()
        return TextTemplateDTO.model_validate(row)

    # ==========================================
    # DOCUMENT SCANS (read-only)
    # ==========================================

    def iter_text_columns(
        self, columns: Sequence[str] = AI_TEXT_COLUMNS, batch_size: int = 500
    ) -> Iterator[tuple[str, str, str | None]]:
        """Streams ``(description_id, column, value)`` without loading the collection at once."""
        last_id = ""
        while True:
            stmt = (
                select(ArchiveDocument.description_id, *[getattr(ArchiveDocument, column) for column in columns])
                .where(ArchiveDocument.description_id > last_id)
                .order_by(ArchiveDocument.description_id)
                .limit(batch_size)
            )
            rows = self.db.execute(stmt).all()
            if not rows:
                break

            last_id = rows[-1]._mapping["description_id"]
            for row in rows:
                mapping = row._mapping
                for column in columns:
                    yield mapping["description_id"], column, mapping[column]

    def count_documents(self, columns: Sequence[str] = AI_TEXT_COLUMNS) -> int:
        """How many documents the suggestion run is about to read."""
        non_null = or_(*[getattr(ArchiveDocument, column).is_not(None) for column in columns])
        return int(self.db.scalar(select(func.count()).select_from(ArchiveDocument).where(non_null)) or 0)

    @staticmethod
    def _affected_condition(rules: Sequence[ExcerptRule], columns: Sequence[str]) -> ColumnElement[bool]:
        return or_(
            *[normalized_column_sql(column).is_distinct_from(effective_column_sql(column, rules)) for column in columns]
        )

    @staticmethod
    def _non_null_condition(columns: Sequence[str]) -> ColumnElement[bool]:
        return or_(*[getattr(ArchiveDocument, column).is_not(None) for column in columns])

    def count_affected_documents(self, rules: Sequence[ExcerptRule], columns: Sequence[str] = AI_TEXT_COLUMNS) -> int:
        """How many documents the given excerpts would change, without changing anything."""
        stmt = (
            select(func.count())
            .select_from(ArchiveDocument)
            .where(self._affected_condition(rules, columns), self._non_null_condition(columns))
        )
        return int(self.db.scalar(stmt) or 0)

    def dry_run(
        self,
        rules: Sequence[ExcerptRule],
        columns: Sequence[str] = AI_TEXT_COLUMNS,
        sample_limit: int = 5,
    ) -> TemplateDryRunResponse:
        """Impact report: documents affected, documents scanned, and before/after samples."""
        selected: list[Any] = [ArchiveDocument.description_id]
        for column in columns:
            selected.append(normalized_column_sql(column).label(f"{column}__original"))
            selected.append(effective_column_sql(column, rules).label(f"{column}__applied"))

        condition = self._affected_condition(rules, columns)
        scanned = int(
            self.db.scalar(select(func.count()).select_from(ArchiveDocument).where(self._non_null_condition(columns)))
            or 0
        )
        affected = int(
            self.db.scalar(
                select(func.count()).select_from(ArchiveDocument).where(condition, self._non_null_condition(columns))
            )
            or 0
        )

        rows = self.db.execute(
            select(*selected).where(condition).order_by(ArchiveDocument.description_id).limit(sample_limit)
        ).all()

        samples: list[TemplateDryRunMatch] = []
        for row in rows:
            mapping = row._mapping
            for column in columns:
                original = mapping[f"{column}__original"]
                applied = mapping[f"{column}__applied"]
                if original != applied:
                    samples.append(
                        TemplateDryRunMatch(
                            description_id=mapping["description_id"],
                            column=column,
                            original_text=original or "",
                            modified_text=applied or "",
                        )
                    )
                    break

        return TemplateDryRunResponse(documents_affected=affected, documents_scanned=scanned, samples=samples)

    def find_documents_with_excerpt(
        self, matchers: Sequence[str], columns: Sequence[str] = AI_TEXT_COLUMNS
    ) -> list[str]:
        """Document ids that currently contain any of the spellings (used by the undo)."""
        conditions = [
            normalized_column_sql(column).contains(matcher, autoescape=True)
            for column in columns
            for matcher in matchers
            if matcher
        ]
        if not conditions:
            return []

        stmt = select(ArchiveDocument.description_id).where(or_(*conditions)).order_by(ArchiveDocument.description_id)
        return list(self.db.scalars(stmt).all())

    # ==========================================
    # RETROACTIVE EFFECT
    # ==========================================

    def requeue_documents(self, description_ids: Sequence[str], stamp_keys: Sequence[str]) -> int:
        """
        Removes the given stamps from the documents, so the next worker run redoes them.

        This is how an undo (or an approval) reaches work that was already done: the
        embedding re-queues by itself because its stamp is a hash of the text, but the
        status-stamped workers (NER, typology, quality validator) have to be told.
        """
        if not description_ids or not stamp_keys:
            return 0

        # ``execution_log`` may hold SQL NULL *or* the JSON scalar ``null``: the column type
        # keeps ``none_as_null=False``, so a Python ``None`` written by an older row is the
        # JSON literal and ``jsonb - text`` on it raises "cannot delete from scalar". Both
        # are folded into an empty object before the keys are removed.
        log_expression = case(
            (
                or_(
                    ArchiveDocument.execution_log.is_(None),
                    func.jsonb_typeof(ArchiveDocument.execution_log) == "null",
                ),
                literal({}, JSONB),
            ),
            else_=ArchiveDocument.execution_log,
        )
        for key in stamp_keys:
            log_expression = log_expression.op("-")(key)

        stmt = (
            update(ArchiveDocument)
            .where(ArchiveDocument.description_id.in_(list(description_ids)))
            .values(execution_log=log_expression)
        )
        result = cast(CursorResult, self.db.execute(stmt))
        return int(result.rowcount or 0)
