/** Tab navigation and board merge helpers (shared with unit tests). */

export function chooseNavigationOp(handoffUrl, targetUrl) {
  /** Always openTab — background create({ active: false }). Never tabs.duplicate. */
  void handoffUrl;
  void targetUrl;
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

/**
 * Fold legacy Waiting column into You (two-lane board). Idempotent.
 * @param {{ you?: any[], agent?: any[], waiting?: any[] }} board
 * @returns {{ board: typeof board, changed: boolean }}
 */
export function foldWaitingIntoYou(board) {
  const waiting = board?.waiting || [];
  if (!waiting.length) {
    return {
      board: {
        you: [...(board?.you || [])],
        agent: [...(board?.agent || [])],
        waiting: [],
      },
      changed: false,
    };
  }
  const you = [...(board.you || [])];
  const ids = new Set(you.map((i) => i?.id).filter(Boolean));
  for (const item of waiting) {
    if (!item) continue;
    const next = { ...item, column: "you" };
    if (next.id && ids.has(next.id)) {
      const idx = you.findIndex((i) => i.id === next.id);
      if (idx >= 0) you[idx] = { ...you[idx], ...next, column: "you" };
    } else {
      you.push(next);
      if (next.id) ids.add(next.id);
    }
  }
  return {
    board: {
      you,
      agent: [...(board.agent || [])],
      waiting: [],
    },
    changed: true,
  };
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
      const item = patch.item || {};
      const col = item.column === "waiting" ? "you" : item.column;
      const stamped = col === "you" && item.column === "waiting" ? { ...item, column: "you" } : item;
      if (!next[col]) next[col] = [];
      next[col].push(stamped);
    } else if (patch.op === "update") {
      const id = patch.item.id;
      let targetCol = patch.item.column;
      if (targetCol === "waiting") targetCol = "you";
      const incoming =
        patch.item.column === "waiting" ? { ...patch.item, column: "you" } : patch.item;
      let placed = false;
      let prev = null;
      for (const c of ["you", "agent", "waiting"]) {
        const idx = next[c].findIndex((item) => item.id === id);
        if (idx < 0) continue;
        prev = next[c][idx];
        if (c === targetCol) {
          next[c][idx] = mergeBoardItemUpdate(prev, incoming);
          placed = true;
        } else {
          next[c] = next[c].filter((item) => item.id !== id);
        }
      }
      if (!placed) {
        next[targetCol].push(mergeBoardItemUpdate(prev, incoming));
      }
    } else if (patch.op === "remove") {
      for (const col of ["you", "agent", "waiting"]) {
        next[col] = next[col].filter((item) => item.id !== patch.id);
      }
    }
  }
  const folded = foldWaitingIntoYou(next);
  return folded.board;
}

/**
 * Host status/column patches often omit custody ids. Keep local agent_tab_id /
 * human_tab_id so Accept provision cannot be clobbered by a racing board_patch.
 */
export function mergeBoardItemUpdate(prev, incoming) {
  const merged = { ...(prev || {}), ...(incoming || {}) };
  if (
    incoming &&
    incoming.agent_tab_id == null &&
    prev &&
    prev.agent_tab_id != null
  ) {
    merged.agent_tab_id = prev.agent_tab_id;
  }
  if (
    incoming &&
    incoming.human_tab_id == null &&
    prev &&
    prev.human_tab_id != null
  ) {
    merged.human_tab_id = prev.human_tab_id;
  }
  return merged;
}
