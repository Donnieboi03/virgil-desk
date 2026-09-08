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
 * Items to render in a column: agent shows roots only; you/waiting show all.
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
