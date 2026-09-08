/**
 * Pure board helpers for panel accordion (testable without Chrome APIs).
 * Re-exports from tabPolicy for a stable panel import surface.
 */
export {
  selectBoardRoots,
  childrenOf,
  allBoardItems,
} from "./tabPolicy.js";

/**
 * Items to render in a column: agent shows roots only; you/waiting show all
 * (grouping handled separately via groupsForFollowColumn).
 * @param {string} column
 * @param {Array<{ parent_id?: string }>} items
 */
export function itemsForColumn(column, items) {
  const list = items || [];
  if (column === "agent") {
    return list.filter((i) => !i.parent_id);
  }
  return list;
}

/**
 * Children of parent from the same column list (agent accordion).
 */
export function childChecklist(allColumnItems, parentId) {
  return (allColumnItems || []).filter((i) => i.parent_id === parentId);
}

/**
 * You/Waiting follow-along groups: roots stay top-level; children nest under
 * parent_id with a label from allItems (parent may live in Agent).
 *
 * @param {Array<{ id?: string, parent_id?: string, title?: string, status?: string }>} columnItems
 * @param {Array<{ id?: string, title?: string }>} allItems
 * @returns {{
 *   roots: typeof columnItems,
 *   groups: Array<{ parentId: string, parentTitle: string, children: typeof columnItems }>,
 * }}
 */
export function groupsForFollowColumn(columnItems, allItems) {
  const list = columnItems || [];
  const byId = Object.fromEntries((allItems || []).map((i) => [i.id, i]));
  const roots = [];
  /** @type {Map<string, typeof list>} */
  const childMap = new Map();
  for (const item of list) {
    if (!item.parent_id) {
      roots.push(item);
      continue;
    }
    const pid = String(item.parent_id);
    if (!childMap.has(pid)) childMap.set(pid, []);
    childMap.get(pid).push(item);
  }
  const groups = [];
  for (const [parentId, children] of childMap.entries()) {
    const parent = byId[parentId];
    groups.push({
      parentId,
      parentTitle: parent?.title || parentId,
      children,
    });
  }
  // Stable order: groups by first child appearance in column list
  const order = [];
  const seen = new Set();
  for (const item of list) {
    if (!item.parent_id) continue;
    const pid = String(item.parent_id);
    if (seen.has(pid)) continue;
    seen.add(pid);
    order.push(pid);
  }
  groups.sort(
    (a, b) => order.indexOf(a.parentId) - order.indexOf(b.parentId),
  );
  return { roots, groups };
}

/**
 * Whether a follow group should start expanded.
 * @param {Array<{ status?: string }>} children
 */
export function followGroupShouldOpen(children) {
  return (children || []).some((c) => c.status !== "done" && c.status !== "denied");
}
