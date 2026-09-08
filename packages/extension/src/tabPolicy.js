/** Tab navigation and board merge helpers (shared with unit tests). */

export function chooseNavigationOp(handoffUrl, targetUrl) {
  if (!targetUrl) return "openTab";
  try {
    const handoff = new URL(handoffUrl);
    const target = new URL(targetUrl);
    if (handoff.origin === target.origin && handoff.pathname === target.pathname) {
      return "duplicateTab";
    }
  } catch {
    /* invalid URL → default open */
  }
  return "openTab";
}

export function policyBlock(command, tabId) {
  if (
    command.human_tab_id &&
    tabId === command.human_tab_id &&
    command.op !== "captureHandoffSnapshot"
  ) {
    return "human_tab_blocked";
  }
  return null;
}

/** Root items: no parent_id. */
export function selectBoardRoots(items) {
  return (items || []).filter((i) => !i.parent_id);
}

export function childrenOf(items, parentId) {
  return (items || []).filter((i) => i.parent_id === parentId);
}

export function allBoardItems(board) {
  return [...(board.you || []), ...(board.agent || []), ...(board.waiting || [])];
}

export function applyBoardPatch(board, ops) {
  const next = {
    you: [...(board.you || [])],
    agent: [...(board.agent || [])],
    waiting: [...(board.waiting || [])],
  };
  for (const patch of ops) {
    if (patch.op === "clear") {
      next.you = [];
      next.agent = [];
      next.waiting = [];
    } else if (patch.op === "add") {
      next[patch.item.column].push(patch.item);
    } else if (patch.op === "update") {
      const col = patch.item.column;
      for (const c of ["you", "agent", "waiting"]) {
        next[c] = next[c].filter((item) => item.id !== patch.item.id);
      }
      next[col].push(patch.item);
    } else if (patch.op === "remove") {
      for (const col of ["you", "agent", "waiting"]) {
        next[col] = next[col].filter((item) => item.id !== patch.id);
      }
    }
  }
  return next;
}
