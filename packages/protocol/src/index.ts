/** Virgil Desk shared protocol types (v1). */

export type Column = "you" | "agent" | "waiting";
export type WorkItemStatus =
  | "proposed"
  | "running"
  | "done"
  | "failed"
  | "denied";

export type ProposalKind = "calendar_slot" | "draft" | "fill" | "other";

export interface Proposal {
  id: string;
  kind: ProposalKind;
  payload: Record<string, unknown>;
  requires: "accept" | "deny";
}

export interface WorkItemEvidence {
  summary?: string;
  urls?: string[];
  scrape_excerpt?: string;
  screenshot_ref?: string;
}

export interface WorkItem {
  id: string;
  column: Column;
  title: string;
  source: {
    kind: "handoff" | "inbox" | "calendar";
    url?: string;
    ref?: string;
  };
  status: WorkItemStatus;
  evidence?: WorkItemEvidence;
  proposals?: Proposal[];
  agent_tab_id?: number;
  human_tab_id?: number;
}

export type BrowserOp =
  | "captureHandoffSnapshot"
  | "openTab"
  | "duplicateTab"
  | "closeTab"
  | "scroll"
  | "scrape"
  | "screenshot"
  | "click"
  | "fill"
  | "wait"
  | "focusTab";

export type TabMode = "snapshot" | "create" | "duplicate" | "reuse";

export type VerifyLevel = "read" | "action" | "handoff";

export interface BrowserCommand {
  command_id: string;
  run_id: string;
  op: BrowserOp;
  human_tab_id?: number;
  tab_id?: number;
  url?: string;
  verify_level?: VerifyLevel;
  params?: Record<string, unknown>;
}

export interface ScreenshotPayload {
  mime: string;
  base64: string;
  width: number;
  height: number;
}

export interface CommandResult {
  command_id: string;
  ok: boolean;
  url?: string;
  title?: string;
  scrape_excerpt?: string;
  screenshot?: ScreenshotPayload;
  error?: string;
  duration_ms: number;
  tab_id?: number;
}

export interface HandoffSnapshot {
  excerpt: string;
  links: string[];
  screenshot?: ScreenshotPayload;
}

export interface HandoffRequest {
  run_id?: string;
  url: string;
  title?: string;
  selection?: string;
  human_tab_id: number;
  agent_tab_id?: number;
  window_id: number;
  intent?: string;
  snapshot?: HandoffSnapshot;
}

export interface HandoffResponse {
  run_id: string;
  decomposition: string;
  items: WorkItem[];
}

export type WsExtensionMessage =
  | { type: "register"; extension_version: string }
  | { type: "handoff_started"; handoff: HandoffRequest }
  | { type: "command_result"; result: CommandResult; run_id: string }
  | { type: "item_ack"; patch_id: string }
  | { type: "board_snapshot"; board: { you: WorkItem[]; agent: WorkItem[]; waiting: WorkItem[] } };

export type WsHostMessage =
  | { type: "board_patch"; run_id: string; patch_id: string; ops: BoardPatchOp[] }
  | { type: "browser_command"; command: BrowserCommand }
  | { type: "run_finished"; run_id: string; status: string; summary?: string }
  | { type: "error"; run_id?: string; code: string; message: string };

export type BoardPatchOp =
  | { op: "clear" }
  | { op: "add"; item: WorkItem }
  | { op: "update"; item: WorkItem }
  | { op: "remove"; id: string };

export interface BoardState {
  you: WorkItem[];
  agent: WorkItem[];
  waiting: WorkItem[];
}

export const BOARD_STORAGE_KEY = "virgil_desk_board_v1";
export const SESSION_TAB_PAIRS_KEY = "virgil_desk_tab_pairs";

export function emptyBoard(): BoardState {
  return { you: [], agent: [], waiting: [] };
}

export function applyBoardPatch(
  board: BoardState,
  ops: BoardPatchOp[],
): BoardState {
  const next: BoardState = {
    you: [...board.you],
    agent: [...board.agent],
    waiting: [...board.waiting],
  };
  for (const patch of ops) {
    if (patch.op === "clear") {
      next.you = [];
      next.agent = [];
      next.waiting = [];
    } else if (patch.op === "add") {
      const col = patch.item.column;
      next[col] = [...next[col], patch.item];
    } else if (patch.op === "update") {
      const col = patch.item.column;
      next[col] = next[col].map((i) =>
        i.id === patch.item.id ? patch.item : i,
      );
    } else if (patch.op === "remove") {
      for (const col of ["you", "agent", "waiting"] as Column[]) {
        next[col] = next[col].filter((i) => i.id !== patch.id);
      }
    }
  }
  return next;
}
