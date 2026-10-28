/**
 * The plan's tree builder and its two questions: what a collapse hides, and what a filter keeps.
 *
 * The cases are the ones the catalogue can produce and the screen cannot afford to guess: a rung
 * whose parent is not in the set, a cycle in ``parent_code`` (the apply has a guard; the view needs
 * its own), a filter that would hide its own match behind a collapsed ancestor, and the counts a
 * collapsed row promises. The test is pure — no DOM, no API — like the CSV parser's.
 */

import { describe, expect, it } from "bun:test";

import type { HierarchyNodePlan } from "../src/api/client";
import {
  buildPlanTree,
  decidedBranchCodes,
  planRows,
  selectPlanCodes,
  visiblePlanRows,
  type PlanNode,
} from "../src/lib/hierarchyTree";

let nextPlanId = 1;

function plan(
  code: string,
  parentCode: string | null,
  overrides: Partial<HierarchyNodePlan> = {},
): HierarchyNodePlan {
  return {
    plan_id: nextPlanId++,
    code,
    parent_code: parentCode,
    depth: code.split(" ").length,
    document_count: 0,
    status: "SUGGESTED",
    ...overrides,
  };
}

function codesOf(nodes: readonly PlanNode[]): string[] {
  return nodes.flatMap((node) => [node.plan.code, ...codesOf(node.children)]);
}

function row(rows: ReturnType<typeof planRows>, code: string) {
  const found = rows.find((item) => item.node.plan.code === code);
  if (!found) throw new Error(`no row for ${code}`);
  return found;
}

describe("buildPlanTree", () => {
  it("builds the forest in code order and nests by parent_code", () => {
    const tree = buildPlanTree([
      plan("B", "A"),
      plan("A C", "A"),
      plan("A", null),
      plan("A B", "A"),
      plan("A B 1", "A B"),
    ]);

    expect(tree.map((node) => node.plan.code)).toEqual(["A"]);
    expect(tree[0]?.children.map((node) => node.plan.code)).toEqual(["A B", "A C", "B"]);
    expect(tree[0]?.children[0]?.children.map((node) => node.plan.code)).toEqual(["A B 1"]);
    expect(tree[0]?.rootReason).toBeNull();
  });

  it("keeps a parent outside the set at the top and says why", () => {
    const tree = buildPlanTree([plan("A B", "A")]);

    expect(tree.map((node) => node.plan.code)).toEqual(["A B"]);
    expect(tree[0]?.rootReason).toBe("orphan");
  });

  it("cuts a parent_code cycle at its smallest code without losing a row", () => {
    const tree = buildPlanTree([plan("A", "B"), plan("B", "A"), plan("C", "A")]);

    expect(codesOf(tree).sort()).toEqual(["A", "B", "C"]);
    expect(tree).toHaveLength(1);
    expect(tree[0]?.plan.code).toBe("A");
    expect(tree[0]?.rootReason).toBe("cycle");
    expect(tree[0]?.children.map((node) => node.plan.code).sort()).toEqual(["B", "C"]);
  });

  it("treats a self-parent as a cycle, not as an orphan", () => {
    const tree = buildPlanTree([plan("A", "A"), plan("B", "A")]);

    expect(tree).toHaveLength(1);
    expect(tree[0]?.plan.code).toBe("A");
    expect(tree[0]?.rootReason).toBe("cycle");
    expect(tree[0]?.children.map((node) => node.plan.code)).toEqual(["B"]);
  });
});

describe("planRows and the collapse", () => {
  const tree = buildPlanTree([
    plan("A", null, { status: "APPROVED" }),
    plan("B", "A"),
    plan("C", "B"),
    plan("D", "A", { status: "REJECTED" }),
  ]);

  it("returns every row in pre-order and counts the whole hidden subtree", () => {
    const rows = planRows(tree, new Set(["A"]));
    const a = row(rows, "A");

    expect(a.collapsed).toBe(true);
    expect(a.hidden).toBe(3);
    expect(a.hiddenPending).toBe(2);
    expect(a.hasChildren).toBe(true);
    expect(rows.map((item) => item.node.plan.code)).toEqual(["A", "B", "C", "D"]);
    expect(visiblePlanRows(tree, new Set(["A"])).map((item) => item.node.plan.code)).toEqual(["A"]);
  });

  it("restores the rows when the branch expands", () => {
    const rows = planRows(tree, new Set());
    const a = row(rows, "A");

    expect(a.collapsed).toBe(false);
    expect(a.hidden).toBe(0);
    expect(visiblePlanRows(tree, new Set()).map((item) => item.node.plan.code)).toEqual([
      "A",
      "B",
      "C",
      "D",
    ]);
  });

  it("leaves a leaf without a branch to collapse", () => {
    const rows = planRows(tree, new Set());
    expect(row(rows, "C").hasChildren).toBe(false);
    expect(row(rows, "D").hasChildren).toBe(false);
  });

  it("ignores a collapsed code the tree no longer has", () => {
    expect(planRows(tree, new Set(["GONE"])).every((item) => !item.collapsed)).toBe(true);
  });
});

describe("the filter and the tree", () => {
  const tree = buildPlanTree([
    plan("A", null, { status: "APPROVED" }),
    plan("B", "A"),
    plan("B 1", "B"),
    plan("B 2", "B", { flags: ["ORDINAL_INFERRED"] }),
    plan("C", "A", { status: "APPROVED" }),
    plan("C 1", "C", { status: "APPROVED" }),
  ]);

  it("keeps the matches, their parents and the branch under each match", () => {
    const rows = planRows(tree, new Set(), { status: "SUGGESTED" });

    expect(rows.map((item) => item.node.plan.code)).toEqual(["A", "B", "B 1", "B 2"]);
    expect(row(rows, "A").matches).toBe(false);
    expect(row(rows, "A").forced).toBe(true);
    expect(row(rows, "B").matches).toBe(true);
    expect(row(rows, "B 1").matches).toBe(true);
    expect(rows.some((item) => item.node.plan.code === "C")).toBe(false);
  });

  it("forces an ancestor open, so a collapse never hides a match", () => {
    const rows = planRows(tree, new Set(["A"]), { q: "B 1" });

    expect(row(rows, "A").forced).toBe(true);
    expect(row(rows, "A").collapsed).toBe(false);
    expect(row(rows, "B 1").hiddenByAncestor).toBe(false);
    expect(visiblePlanRows(tree, new Set(["A"]), { q: "B 1" }).map((item) => item.node.plan.code)).toEqual([
      "A",
      "B",
      "B 1",
    ]);
  });

  it("keeps the descendants of a match, and only those", () => {
    const rows = planRows(tree, new Set(), { q: "B" });

    expect(rows.map((item) => item.node.plan.code)).toEqual(["A", "B", "B 1", "B 2"]);
    expect(row(rows, "B 1").matches).toBe(true);
    expect(rows.some((item) => item.node.plan.code === "C")).toBe(false);
  });

  it("matches by flag on the same rule as by status", () => {
    const rows = planRows(tree, new Set(), { flag: "ORDINAL_INFERRED" });

    expect(rows.map((item) => item.node.plan.code)).toEqual(["A", "B", "B 2"]);
    expect(row(rows, "B 2").matches).toBe(true);
    expect(rows.some((item) => item.node.plan.code === "C")).toBe(false);
  });

  it("collapses a match's own non-matching descendants, and counts them", () => {
    const branch = buildPlanTree([
      plan("R", null, { status: "APPROVED" }),
      plan("R A", "R", { status: "APPROVED" }),
      plan("R A 1", "R A", { status: "REJECTED" }),
    ]);

    const rows = planRows(branch, new Set(["R A"]), { status: "APPROVED" });

    expect(row(rows, "R A").matches).toBe(true);
    expect(row(rows, "R A").collapsed).toBe(true);
    expect(row(rows, "R A").hidden).toBe(1);
    expect(row(rows, "R A").hiddenPending).toBe(0);
  });

  it("selects the matches, the path to them and their branches", () => {
    const selection = selectPlanCodes(tree, { q: "B" });

    expect([...selection.matching].sort()).toEqual(["B", "B 1", "B 2"]);
    expect([...selection.forced].sort()).toEqual(["A", "B"]);
    expect([...selection.visible].sort()).toEqual(["A", "B", "B 1", "B 2"]);
  });

  it("matches nothing when the filter matches nothing", () => {
    const rows = planRows(tree, new Set(), { q: "ZZZ" });
    expect(rows).toEqual([]);
  });
});

describe("decidedBranchCodes", () => {
  it("closes the top of a decided subtree, not every row inside it", () => {
    const tree = buildPlanTree([
      plan("R", null, { status: "APPROVED" }),
      plan("A", "R", { status: "APPROVED" }),
      plan("A 1", "A", { status: "APPROVED" }),
      plan("B", "R"),
    ]);

    expect([...decidedBranchCodes(tree)]).toEqual(["A"]);
  });

  it("returns the root alone when the whole catalogue is decided, and no leaves", () => {
    const tree = buildPlanTree([
      plan("R", null, { status: "REJECTED" }),
      plan("A", "R", { status: "APPROVED" }),
      plan("A 1", "A", { status: "APPROVED" }),
    ]);

    expect([...decidedBranchCodes(tree)]).toEqual(["R"]);
  });

  it("returns nothing when every branch still has a pending rung", () => {
    const tree = buildPlanTree([
      plan("R", null, { status: "APPROVED" }),
      plan("A", "R", { status: "APPROVED" }),
      plan("A 1", "A"),
    ]);

    expect([...decidedBranchCodes(tree)]).toEqual([]);
  });
});
