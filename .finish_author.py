"""One-off: imports, dependencies and the last leftovers. Deleted after running."""

import pathlib
import re

CTRL = pathlib.Path("src/scrinalia/api/controllers")
DOMAIN = pathlib.Path("src/scrinalia/domains/archive")

PARAM = "        current_user: NamedDependency[AuthenticatedUser],\n"

HANDLER_PARAMS = {
    "hierarchy_controller.py": [
        (
            "        data: HierarchyPlanDecisionRequest,\n    ) -> HierarchyNodePlanDTO:",
            "        data: HierarchyPlanDecisionRequest,\n" + PARAM + "    ) -> HierarchyNodePlanDTO:",
        ),
        (
            "        data: HierarchyMaterialisationRequest,\n    ) -> HierarchyMaterialisationPreview:",
            "        data: HierarchyMaterialisationRequest,\n" + PARAM + "    ) -> HierarchyMaterialisationPreview:",
        ),
        (
            "        data: HierarchyMaterialisationRequest,\n    ) -> HierarchyMaterialisationResult:",
            "        data: HierarchyMaterialisationRequest,\n" + PARAM + "    ) -> HierarchyMaterialisationResult:",
        ),
    ],
    "text_quality_controller.py": [
        (
            "        data: CreateTextTemplateRequest,\n    ) -> TextTemplateMutationResponse:",
            "        data: CreateTextTemplateRequest,\n" + PARAM + "    ) -> TextTemplateMutationResponse:",
        ),
        (
            "        data: UpdateTextTemplateRequest,\n    ) -> TextTemplateMutationResponse:",
            "        data: UpdateTextTemplateRequest,\n" + PARAM + "    ) -> TextTemplateMutationResponse:",
        ),
    ],
    "system_controller.py": [
        (
            "        data: WorkerRunRequest,\n    ) -> WorkerRunDTO:",
            "        data: WorkerRunRequest,\n" + PARAM + "    ) -> WorkerRunDTO:",
        ),
        (
            "        data: WorkerSettingsRequest,\n    ) -> WorkerSettingsDTO:",
            "        data: WorkerSettingsRequest,\n" + PARAM + "    ) -> WorkerSettingsDTO:",
        ),
    ],
}

applied = 0
for name, pairs in HANDLER_PARAMS.items():
    path = CTRL / name
    text = path.read_text()
    for old, new in pairs:
        if new in text:
            continue
        if text.count(old) != 1:
            raise SystemExit(f"{name}: {old[:50]!r} x{text.count(old)}")
        text = text.replace(old, new)
        applied += 1
    path.write_text(text)

# --- imports and the dependency entry, for every controller that uses the account ---------------
for path in sorted(CTRL.glob("*.py")):
    text = path.read_text()
    if "AuthenticatedUser" not in text:
        continue

    text = text.replace(
        "from scrinalia.api.security import Access\n", "from scrinalia.api.security import Access, AuthenticatedUser\n"
    )

    if "provide_current_user" not in text:
        single = re.search(r"^from scrinalia\.api\.dependencies import (.+)$", text, re.M)
        block = re.search(r"^from scrinalia\.api\.dependencies import \(\n", text, re.M)
        if block:
            text = text[: block.end()] + "    provide_current_user,\n" + text[block.end() :]
        elif single:
            text = text[: single.start(1)] + "provide_current_user, " + text[single.start(1) :]
        else:
            raise SystemExit(f"{path.name}: sem import de dependencies")

    if '"current_user": Provide' not in text:
        anchor = '        "unit_of_work"' if False else None
        # insert as the first entry of the controller's dependencies dict
        marker = re.search(r"^    dependencies = \{  # noqa: RUF012\n", text, re.M)
        if marker is None:
            raise SystemExit(f"{path.name}: sem bloco de dependencies")
        text = (
            text[: marker.end()]
            + '        "current_user": Provide(provide_current_user, sync_to_thread=False),\n'
            + text[marker.end() :]
        )

    path.write_text(text)
    applied += 1

# --- the merge-log filter is a name, end to end -------------------------------------------------
tag_repo = DOMAIN / "repository/tag_repo.py"
text = tag_repo.read_text()
for old, new in [
    (
        "        canonical_id: int | None = None,\n        changed_by: Author | None = None,\n        include_undone: bool = True,\n        term: str | None = None,\n    ) -> int:",
        "        canonical_id: int | None = None,\n        changed_by_name: str | None = None,\n        include_undone: bool = True,\n        term: str | None = None,\n    ) -> int:",
    ),
    (
        "def _tag_merge_log_filters(\n        self, canonical_id: int | None, changed_by: Author | None, include_undone: bool, term: str | None",
        "def _tag_merge_log_filters(\n        self, canonical_id: int | None, changed_by_name: str | None, include_undone: bool, term: str | None",
    ),
]:
    if new in text:
        continue
    if text.count(old) != 1:
        raise SystemExit(f"tag_repo: {old[:60]!r} x{text.count(old)}")
    text = text.replace(old, new)
    applied += 1
tag_repo.write_text(text)

tag_service = DOMAIN / "services/tag_service.py"
text = tag_service.read_text()
old = "            changed_by=changed_by,\n            include_undone=include_undone,"
new = "            changed_by_name=changed_by_name,\n            include_undone=include_undone,"
if new not in text:
    if text.count(old) != 1:
        raise SystemExit(f"tag_service: {old[:50]!r} x{text.count(old)}")
    text = text.replace(old, new)
    applied += 1
tag_service.write_text(text)

# --- the two missing imports --------------------------------------------------------------------
run_service = DOMAIN / "services/worker_run_service.py"
text = run_service.read_text()
if "from scrinalia.core.author import Author" not in text:
    text = re.sub(r"^(from scrinalia\.)", "from scrinalia.core.author import Author\n\\1", text, count=1, flags=re.M)
    run_service.write_text(text)
    applied += 1

print("aplicadas:", applied)
