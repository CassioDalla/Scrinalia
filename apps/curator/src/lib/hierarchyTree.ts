/**
 * The arrangement plan as a tree, not a list indented by pixels.
 *
 * The API already says which rung hangs under which: ``code`` is unique and every row carries
 * ``parent_code``. This module turns those rows into a forest and answers what the screen may show
 * after the archivist collapses a branch or filters by a verdict. It is pure on purpose — the
 * component owns no rule about the tree, and ``bun test`` can pin the awkward cases (a missing
 * parent, a cycle, a filter that must not hide its own match) without a browser.
 *
 * The tree is a **proposal**, not the materialised arrangement. ``collapse_into_code`` is a link the
 * archivist wrote, and the materialisation follows it; the plan screen still draws the rung where
 * ``parent_code`` puts it and says on the row that the branch will move up. Re-parenting here would
 * show a result that only exists after the target is approved, which is a different lie.
 */

import type { HierarchyNodePlan, PlanStatus } from "@/api/client";

/** Why a node is a root although it carries a ``parent_code``. */
export type PlanRootReason = "orphan" | "cycle" | null;

export type PlanNode = {
  plan: HierarchyNodePlan;
  children: PlanNode[];
  rootReason: PlanRootReason;
};

/** The three filters the screen owns; all of them are applied on the client. */
export type PlanFilters = {
  status?: PlanStatus;
  flag?: string;
  q?: string;
};

export type PlanRow = {
  node: PlanNode;
  /** Depth in the rendered forest, which is not always ``plan.depth`` (an orphan starts at zero). */
  depth: number;
  /** Whether the row itself matched the filter, as opposed to being context for a match. */
  matches: boolean;
  /** Whether the filter keeps at least one child, so the branch toggle has something to hide. */
  hasChildren: boolean;
  /** The effective state: requested **and** not forced open by a filter. */
  collapsed: boolean;
  /** An ancestor of a match, so it may not be collapsed while the filter is active. */
  forced: boolean;
  /** A collapsed ancestor hides this row; it is part of the payload so the list can be narrowed. */
  hiddenByAncestor: boolean;
  /** Descendants this row hides while collapsed, inside the current filter. */
  hidden: number;
  /** Of those, the ones still ``SUGGESTED`` — collapsing must never hide work silently. */
  hiddenPending: number;
};

/**
 * The forest the screen draws.
 *
 * Roots are the rows with no ``parent_code`` **and** the rows whose parent is not in the set (a
 * rejected parent, a filtered subset, an older plan); the latter say so instead of vanishing. A
 * cycle is cut at its smallest code so every row still appears exactly once and the walk ends.
 */
export function buildPlanTree(items: readonly HierarchyNodePlan[]): PlanNode[] {
  const ordered = [...items].sort((left, right) => left.code.localeCompare(right.code));
  const byCode = new Map<string, PlanNode>();
  for (const plan of ordered) {
    // ``code`` is unique by contract; a duplicate would render two rows with the same key, so the
    // first one wins rather than making the tree depend on the order of a broken payload.
    if (byCode.has(plan.code)) continue;
    byCode.set(plan.code, { plan, children: [], rootReason: null });
  }

  const parentOf = new Map<string, string | null>();
  for (const [code, node] of byCode) {
    const parent = node.plan.parent_code;
    parentOf.set(code, parent && byCode.has(parent) ? parent : null);
  }

  const cycleRoots = findCycleRoots(parentOf);
  const roots: PlanNode[] = [];
  for (const node of byCode.values()) {
    const code = node.plan.code;
    const isCycleRoot = cycleRoots.has(code);
    const parent = isCycleRoot ? null : (parentOf.get(code) ?? null);

    if (parent === null) {
      node.rootReason = isCycleRoot ? "cycle" : node.plan.parent_code ? "orphan" : null;
      roots.push(node);
      continue;
    }

    // ``parentOf`` only names codes in ``byCode``, so the parent always exists here.
    byCode.get(parent)?.children.push(node);
  }

  return roots;
}

/**
 * The rungs a "recolher os decididos" click closes: the **maximal** subtrees with no pending rung.
 *
 * Collapsing every decided row would put hundreds of codes in the URL; collapsing the top of each
 * decided subtree is what the archivist meant. A leaf is left out because it has nothing to hide.
 */
export function decidedBranchCodes(tree: readonly PlanNode[]): Set<string> {
  const pending = new Map<string, number>();
  const parentOf = new Map<string, PlanNode | null>();
  const nodes: PlanNode[] = [];

  const count = (node: PlanNode, parent: PlanNode | null): number => {
    parentOf.set(node.plan.code, parent);
    nodes.push(node);
    let total = node.plan.status === "SUGGESTED" ? 1 : 0;
    for (const child of node.children) total += count(child, node);
    pending.set(node.plan.code, total);
    return total;
  };
  for (const root of tree) count(root, null);

  const collapsed = new Set<string>();
  for (const node of nodes) {
    if (node.children.length === 0) continue;
    if ((pending.get(node.plan.code) ?? 0) !== 0) continue;
    const parent = parentOf.get(node.plan.code) ?? null;
    // If the parent is fully decided too, the parent's code already covers this whole branch.
    if (parent && (pending.get(parent.plan.code) ?? 0) === 0) continue;
    collapsed.add(node.plan.code);
  }
  return collapsed;
}

/**
 * Every row the filter keeps, in pre-order, with the counts a collapsed row shows.
 *
 * The filter keeps the matches, their ancestors (so a match has a path) and the whole branch under
 * each match (so the hit is navigable, not just a dot on a line). Ancestors of a match are
 * ``forced``: a collapse they requested earlier never hides a match. The counts are
 * **view-relative** — what expanding this row would reveal now — so a status tab that already
 * removed the pending rows does not claim to hide them.
 */
export function planRows(
  tree: readonly PlanNode[],
  collapsed: ReadonlySet<string>,
  filters: PlanFilters = {},
): PlanRow[] {
  const selected = selectPlanCodes(tree, filters);
  const rows: PlanRow[] = [];

  const visit = (node: PlanNode, depth: number, hiddenByAncestor: boolean): void => {
    const code = node.plan.code;
    if (!selected.visible.has(code)) return;

    const children = node.children.filter((child) => selected.visible.has(child.plan.code));
    const forced = selected.forced.has(code);
    const isCollapsed = collapsed.has(code) && !forced;
    const stats = isCollapsed ? subtreeStats(node, selected.visible) : { descendants: 0, pending: 0 };

    rows.push({
      node,
      depth,
      matches: selected.matching.has(code),
      hasChildren: children.length > 0,
      collapsed: isCollapsed,
      forced,
      hiddenByAncestor,
      hidden: stats.descendants,
      hiddenPending: stats.pending,
    });

    for (const child of children) visit(child, depth + 1, hiddenByAncestor || isCollapsed);
  };

  for (const root of tree) visit(root, 0, false);
  return rows;
}

/** The rows a person can actually see: everything ``planRows`` returns minus what a collapse hides. */
export function visiblePlanRows(
  tree: readonly PlanNode[],
  collapsed: ReadonlySet<string>,
  filters: PlanFilters = {},
): PlanRow[] {
  return planRows(tree, collapsed, filters).filter((row) => !row.hiddenByAncestor);
}

/**
 * The codes the filter keeps.
 *
 * With no filter every row matches and nothing is forced, which is what lets the unfiltered screen
 * collapse anything. With a filter, ``forced`` is exactly the strict ancestors of the matches: those
 * must stay open, and a node that is both a match and an ancestor of another match is forced too.
 */
export function selectPlanCodes(
  tree: readonly PlanNode[],
  filters: PlanFilters = {},
): { visible: Set<string>; forced: Set<string>; matching: Set<string> } {
  const parentOf = new Map<string, PlanNode | null>();
  const byCode = new Map<string, PlanNode>();
  const nodes: PlanNode[] = [];

  const collect = (node: PlanNode, parent: PlanNode | null): void => {
    parentOf.set(node.plan.code, parent);
    byCode.set(node.plan.code, node);
    nodes.push(node);
    for (const child of node.children) collect(child, node);
  };
  for (const root of tree) collect(root, null);

  const matching = new Set<string>();
  const filtered = hasFilters(filters);
  for (const node of nodes) {
    if (!filtered || matchesFilters(node.plan, filters)) matching.add(node.plan.code);
  }

  if (!filtered) {
    return { visible: new Set(nodes.map((node) => node.plan.code)), forced: new Set(), matching };
  }

  const visible = new Set(matching);
  const forced = new Set<string>();

  // The path to every match, so no match can hide behind a collapsed ancestor.
  for (const code of matching) {
    let parent = parentOf.get(code) ?? null;
    while (parent) {
      visible.add(parent.plan.code);
      forced.add(parent.plan.code);
      parent = parentOf.get(parent.plan.code) ?? null;
    }
  }

  // The branch under every match, so the hit can be read and its children navigated.
  const addDescendants = (node: PlanNode): void => {
    for (const child of node.children) {
      visible.add(child.plan.code);
      addDescendants(child);
    }
  };
  for (const code of matching) {
    const node = byCode.get(code);
    if (node) addDescendants(node);
  }

  return { visible, forced, matching };
}

function matchesFilters(plan: HierarchyNodePlan, filters: PlanFilters): boolean {
  if (filters.status && plan.status !== filters.status) return false;
  if (filters.flag && !(plan.flags ?? []).includes(filters.flag)) return false;
  const term = filters.q?.toLowerCase();
  if (term && !plan.code.toLowerCase().includes(term)) return false;
  return true;
}

function hasFilters(filters: PlanFilters): boolean {
  return Boolean(filters.status || filters.flag || filters.q);
}

/** Visible descendants of a node, not counting the node itself. */
function subtreeStats(node: PlanNode, visible: ReadonlySet<string>): { descendants: number; pending: number } {
  let descendants = 0;
  let pending = 0;

  const walk = (parent: PlanNode): void => {
    for (const child of parent.children) {
      if (!visible.has(child.plan.code)) continue;
      descendants += 1;
      if (child.plan.status === "SUGGESTED") pending += 1;
      walk(child);
    }
  };
  walk(node);

  return { descendants, pending };
}

/**
 * The codes at which a ``parent_code`` chain closes on itself.
 *
 * A functional graph of parent pointers; the walk marks the path it is on (``1``) and the paths it
 * has finished (``2``). Meeting a ``1`` is a cycle, and its smallest code is cut so the forest stays
 * finite and every row still appears exactly once.
 */
function findCycleRoots(parentOf: ReadonlyMap<string, string | null>): Set<string> {
  const state = new Map<string, 1 | 2>();
  const roots = new Set<string>();

  for (const start of parentOf.keys()) {
    if (state.has(start)) continue;

    const path: string[] = [];
    const index = new Map<string, number>();
    let current: string | null = start;

    while (current !== null && !state.has(current)) {
      state.set(current, 1);
      index.set(current, path.length);
      path.push(current);
      current = parentOf.get(current) ?? null;
    }

    if (current !== null && state.get(current) === 1) {
      const cycle = path.slice(index.get(current) ?? 0);
      const root = [...cycle].sort((left, right) => left.localeCompare(right))[0];
      if (root !== undefined) roots.add(root);
    }

    for (const code of path) state.set(code, 2);
  }

  return roots;
}
