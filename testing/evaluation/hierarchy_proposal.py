"""
The tree the reference codes imply, measured on the **real** collection (Fase 2.5, H3).

This is the decision point of the phase, and the reason H3 ships before any screen: the report says
how regular the structure actually is. It already contradicted the roadmap's own estimate. Slicing
a code on every space turns ``BR PRADAP SMU ED AL`` into **1,123 parents of one document each**,
because the code interleaves the arrangement vocabulary with the identifiers of the leaf; the
vocabulary-aware slicer is what brings ~3,600 codes down to the few dozen rungs a human can
actually review.

Nothing here writes. The routine reads the reference codes and the level catalogue, and prints:

* how many descriptions carry a code and how many distinct rungs they imply;
* which rungs already exist as a record and which would have to be created;
* every rung whose ordinal is a *proposal* rather than the archivist's statement;
* the plural/singular collisions (``FOTOGRAFIA`` vs ``FOTOGRAFIAS``) the archivist has to decide;
* the codes the slicer could not read cleanly.

Run it from the repository root, against the database you mean to inspect::

    uv run python -m testing.evaluation.hierarchy_proposal

It prints a summary and writes the full JSON to ``.analysis/hierarchy_proposal.json``
(non-versioned), which is what the curator screen (H4) will consume through
``POST /api/v1/hierarchy/proposal``.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.domains.archive.repository.collection_vocabulary_repo import CollectionVocabularyRepository
from scrinalia.domains.archive.repository.hierarchy_repo import HierarchyRepository
from scrinalia.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from scrinalia.domains.archive.schemas.hierarchy_schema import HierarchyProposalCommand
from scrinalia.domains.archive.services.hierarchy_proposal_service import HierarchyProposalService

DEFAULT_OUTPUT = Path(".analysis") / "hierarchy_proposal.json"

#: How many nodes the JSON carries. The summary counts are always over the whole proposal.
DEFAULT_LIMIT = 5000


def build_report(db, limit: int = DEFAULT_LIMIT) -> dict:
    """Runs the proposal and reduces it to the numbers a decision needs."""
    service = HierarchyProposalService(
        HierarchyRepository(db), LevelCatalogRepository(db), CollectionVocabularyRepository(db)
    )
    proposal = service.propose(HierarchyProposalCommand(limit=limit))

    nodes = [node.model_dump() for node in proposal.nodes]
    with_documents = [node for node in nodes if node["document_count"] > 0]
    top = sorted(with_documents, key=lambda node: -node["document_count"])[:15]

    return {
        "total_codes": proposal.total_codes,
        "structural_codes": proposal.structural_codes,
        "total_nodes": proposal.total_nodes,
        "existing_nodes": proposal.existing_nodes,
        "nodes_to_create": proposal.nodes_to_create,
        "ambiguous_nodes": proposal.ambiguous_nodes,
        "flagged_nodes": proposal.flagged_nodes,
        "flags": proposal.flags,
        "unparsed_codes": proposal.unparsed_codes,
        "biggest_rungs": [
            {
                "code": node["code"],
                "depth": node["depth"],
                "documents": node["document_count"],
                "status": node["status"],
                "proposed_level": node["proposed_level_code"],
                "ordinal_inferred": node["ordinal_inferred"],
                "flags": node["flags"],
            }
            for node in top
        ],
        "nodes": nodes,
    }


def print_summary(report: dict) -> None:
    logger.info("=" * 78)
    logger.info("HIERARCHY PROPOSAL — read-only, measured on the live collection")
    logger.info("=" * 78)
    logger.info(f"Descriptions with a reference code : {report['total_codes']}")
    logger.info(f"Distinct arrangement rungs implied : {report['structural_codes']}")
    logger.info(f"Nodes proposed                     : {report['total_nodes']}")
    logger.info(f"  already exist as a record        : {report['existing_nodes']}")
    logger.info(f"  would have to be created         : {report['nodes_to_create']}")
    logger.info(f"  ambiguous (plural collision)     : {report['ambiguous_nodes']}")
    logger.info(f"  carrying at least one flag       : {report['flagged_nodes']}")

    logger.info("-" * 78)
    logger.info("Flags, by how many nodes carry them:")
    for flag, count in sorted(report["flags"].items(), key=lambda item: -item[1]):
        logger.info(f"  {flag:<34} {count}")

    logger.info("-" * 78)
    logger.info("The rungs that hold the most descriptions:")
    for node in report["biggest_rungs"]:
        inferred = "inferred" if node["ordinal_inferred"] else "ANCHORED"
        logger.info(
            f"  {node['documents']:>5} docs | depth {node['depth']} | {node['proposed_level'] or '?':<7} "
            f"| {inferred:<8} | {node['code']}"
        )

    if report["unparsed_codes"]:
        logger.info("-" * 78)
        logger.info(f"Codes the slicer could not read cleanly: {len(report['unparsed_codes'])}")
        for code in report["unparsed_codes"][:10]:
            logger.info(f"  {code}")

    logger.info("=" * 78)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where the JSON report goes.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Cap on nodes carried in the JSON.")
    args = parser.parse_args()

    with get_db() as db:
        report = build_report(db, limit=args.limit)

    print_summary(report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.success(f"Report written to {args.output}")

    statuses = Counter(node["status"] for node in report["nodes"])
    logger.info(f"Statuses in the page: {dict(statuses)}")


if __name__ == "__main__":
    main()
