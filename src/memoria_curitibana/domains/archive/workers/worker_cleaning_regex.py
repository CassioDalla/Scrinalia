import re

from sqlalchemy.orm import Session

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.core.unit_of_work import UnitOfWork
from memoria_curitibana.domains.archive.repository.cleaning_repo import CleaningRepository
from memoria_curitibana.domains.archive.schemas.cleaning_schema import CleaningUpdateCommand
from memoria_curitibana.domains.archive.worker_stamp import cleaning_rule_stamp

BATCH_SIZE = 500


def execute(db: Session) -> None:
    """
    Worker that applies dynamic Regex rules (Text Cleaning) created by the curators.
    Processes documents incrementally using the 'execution_log' as a tracker.
    """
    logger.info("🧹 Starting the Data Quality Cleaner Worker...")

    repo = CleaningRepository(db)
    uow = UnitOfWork(db)
    active_rules = repo.get_active_rules()

    if not active_rules:
        logger.info("No active cleaning rule found.")
        return

    logger.info(f"📋 Found {len(active_rules)} active rules. Starting the scan...")

    for rule in active_rules:
        rule_key = cleaning_rule_stamp(rule.rule_id).key

        try:
            # Compiles the regex only once per rule
            compiled_regex = re.compile(rule.regex_pattern, re.IGNORECASE)
        except Exception as e:
            logger.error(f"❌ Rule ID {rule.rule_id} ('{rule.rule_name}') has invalid Regex syntax: {e}. Skipping.")
            continue

        processed_docs = 0
        changes_made = 0

        while True:
            # Fetches the next batch of documents that have not yet seen THIS rule
            batch_docs = repo.get_unprocessed_documents_for_rule(
                rule_id=rule.rule_id, target_column=rule.target_column, limit=BATCH_SIZE
            )

            if not batch_docs:
                break  # End of the scan for this rule!

            try:
                updates: list[CleaningUpdateCommand] = []
                for doc in batch_docs:
                    cleaned_text = compiled_regex.sub(rule.replacement_string, doc.text)

                    if cleaned_text != doc.text:
                        changes_made += 1

                    updates.append(
                        CleaningUpdateCommand(
                            description_id=doc.description_id,
                            target_column=rule.target_column,
                            new_text=cleaned_text,
                            stamp_key=rule_key,
                        )
                    )
                    processed_docs += 1

                repo.apply_cleaning(updates)

                # Commits the whole batch
                uow.commit()

            except Exception as e:
                logger.error(f"💥 Error committing batch in Rule {rule.rule_id}: {e}")
                uow.rollback()
                break  # Skips to the next rule so it does not get stuck

        if processed_docs > 0:
            logger.success(
                f"✅ Rule '{rule.rule_name}' completed! Audited: {processed_docs} | Changed: {changes_made}."
            )

    logger.info("🏁 Cleaner Worker scan finished.")


if __name__ == "__main__":
    with get_db() as db:
        execute(db)
