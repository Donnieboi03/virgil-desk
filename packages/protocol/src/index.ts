/** Virgil Desk shared protocol types (v1). */

export type Column = "you" | "agent" | "waiting";
export type WorkItemStatus =
  | "proposed"
  | "running"
  | "awaiting_human"
  | "done"
  | "failed"
  | "denied";

export type ParkKind = "auth_gate" | "human_remainder";

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

/** One visible row inside a pattern-class clump (inventory for execute). */
export interface WorkItemHintMember {
  sender?: string;
  subject_contains?: string;
}

export interface WorkItemHints {
  search_query?: string;
  sender?: string;
  subject_contains?: string;
  /** Clump inventory — execute walks each member before Done. */
  members?: WorkItemHintMember[];
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
  parent_id?: string;
  kind?: "parent" | "subtask";
  /** You park: auth/challenge gate (resume parent) vs informational human glance. */
  park_kind?: ParkKind;
  /** When true, Mark done unblocks parent agent for Resume. */
  resume?: boolean;
  /** Set on parent after You auth_gate Mark done; panel shows Resume agent. */
  resume_ready?: boolean;
  evidence?: WorkItemEvidence;
  proposals?: Proposal[];
  hints?: WorkItemHints;
  agent_tab_id?: number;
  human_tab_id?: number;
  run_id?: string;
  last_error?: string;
}

export type BrowserOp =
  | "captureHandoffSnapshot"
  | "navigate"
  | "openTab"
  | "duplicateTab"
  | "closeTab"
  | "scroll"
  | "scrape"
  | "screenshot"
  | "observe"
  | "probe_form"
  | "probe_links"
  | "probe_table"
  | "click"
  | "fill"
  | "key"
  | "wait"
  | "focusTab";

export type InteractTargetKind =
  | "clickable"
  | "input"
  | "select"
  | "toggle"
  | "scroll_container";

export interface ViewportInfo {
  w: number;
  h: number;
}

export interface RectInfo {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PointInfo {
  x: number;
  y: number;
}

export interface InteractTarget {
  id: number;
  ref: string;
  kind: InteractTargetKind;
  label: string;
  text?: string;
  role?: string;
  tag?: string;
  rect?: RectInfo;
  center?: PointInfo;
  selector_hint?: string;
  selector_stable?: boolean;
  frame_id?: number;
}

export interface ScrollContainer {
  id: number;
  ref: string;
  label: string;
  rect?: RectInfo;
  scrollHeight: number;
  clientHeight: number;
  frame_id?: number;
}

export interface ObservePayload {
  url: string;
  title: string;
  viewport: ViewportInfo;
  device_pixel_ratio: number;
  text_excerpt: string;
  text_omitted?: boolean;
  excerpt_note?: string;
  page_tree?: string;
  interact_targets: InteractTarget[];
  scroll_containers: ScrollContainer[];
}

export interface ActResolvedHit {
  ref?: string;
  tag?: string;
  center?: PointInfo;
}

export interface ActResolved {
  op: string;
  requested: Record<string, unknown>;
  used: string;
  hit?: ActResolvedHit;
  url_before?: string;
  url_after?: string;
}

export type TabMode = "snapshot" | "create" | "duplicate" | "reuse";

export type VerifyLevel = "read" | "action" | "handoff";

export interface BrowserCommand {
  command_id: string;
  run_id: string;
  op: BrowserOp;
  human_tab_id?: number;
  tab_id?: number;
  url?: string;
  handoff_url?: string;
  verify_level?: VerifyLevel;
  params?: Record<string, unknown>;
  skip_screenshot?: boolean;
}

export interface ScreenshotPayload {
  mime: string;
  base64: string;
  width: number;
  height: number;
}

export interface EyesHints {
  url_path_hint?: string;
}

export interface CommandResult {
  command_id: string;
  ok: boolean;
  url?: string;
  title?: string;
  scrape_excerpt?: string;
  text_omitted?: boolean;
  excerpt_note?: string;
  screenshot?: ScreenshotPayload;
  observe?: ObservePayload;
  interact_targets?: InteractTarget[];
  scroll_containers?: ScrollContainer[];
  page_tree?: string;
  form_fields?: Record<string, unknown>[];
  links?: { text: string; href: string; frame_id?: number }[];
  rows?: { index: number; cells: string[] }[];
  viewport?: ViewportInfo;
  device_pixel_ratio?: number;
  act_resolved?: ActResolved;
  error?: string;
  duration_ms: number;
  tab_id?: number;
  /** Eyes settle: true when T0 text/targets/links all thin after budget. */
  eyes_empty?: boolean;
  eyes_settle_ms?: number;
  eyes_settle_attempts?: number;
  /** True when settle budget was extended once for challenge markers. */
  challenge_extended?: boolean;
  /** Wall ms spent injecting the interact bundle for this op. */
  inject_ms?: number;
  /** chrome.scripting.executeScript result frame count (allFrames). */
  frame_count?: number;
  /**
   * Fail-only Eyes ladder: 0 default innerText/targets, 1 deep text/tree
   * promote, 2 soft hints (still empty). Not soft site tiers A–D.
   */
  eyes_mode?: 0 | 1 | 2;
  eyes_hints?: EyesHints;
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
  | { type: "registered"; ok: boolean; config?: Record<string, unknown> }
  | { type: "handoff_result"; run_id: string; decomposition?: string; items?: WorkItem[] }
  | { type: "board_patch"; run_id: string; patch_id: string; ops: BoardPatchOp[] }
  | { type: "browser_command"; command: BrowserCommand };

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

/** Root items: no parent_id (parents and flat handoff items). */
export function selectBoardRoots(items: WorkItem[]): WorkItem[] {
  return items.filter((i) => !i.parent_id);
}

/** Children of a parent across the board. */
export function childrenOf(items: WorkItem[], parentId: string): WorkItem[] {
  return items.filter((i) => i.parent_id === parentId);
}

/** Flatten all columns into one list. */
export function allBoardItems(board: BoardState): WorkItem[] {
  return [...board.you, ...board.agent, ...board.waiting];
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
      // Remove from any column first so column moves work.
      for (const c of ["you", "agent", "waiting"] as Column[]) {
        next[c] = next[c].filter((i) => i.id !== patch.item.id);
      }
      next[col] = [...next[col], patch.item];
    } else if (patch.op === "remove") {
      for (const col of ["you", "agent", "waiting"] as Column[]) {
        next[col] = next[col].filter((i) => i.id !== patch.id);
      }
    }
  }
  return next;
}
