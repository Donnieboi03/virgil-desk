/**
 * Page-context observe + act bundle (WebMarker SoM + Anthropic-style targets).
 * Bundled to dist/interactObserve.bundle.js for chrome.scripting.executeScript.
 */
import { mark, unmark, isMarked } from "webmarker-js";

const INTERACTIVE_SELECTOR =
  "a[href], button, input, textarea, select, [role=button], [role=link], " +
  "[role=checkbox], [role=radio], [role=tab], [role=menuitem], [role=row], " +
  "[role=option], [contenteditable=true], [tabindex]:not([tabindex='-1']), " +
  "tr.zA, tr.zE";

function isConversationRow(el) {
  if (!el || !(el instanceof Element)) return false;
  const tag = el.tagName.toLowerCase();
  if (tag === "tr" && /\bz[AE]\b/.test(el.className || "")) return true;
  const role = (el.getAttribute("role") || "").toLowerCase();
  if (role === "row" && tag === "tr") return true;
  if (
    role === "row" &&
    (el.getAttribute("data-legacy-thread-id") ||
      el.querySelector?.("[data-legacy-thread-id], .bog, .yW"))
  ) {
    return true;
  }
  return false;
}

function conversationRowLabel(el) {
  const pick = (sel) => {
    try {
      const n = el.querySelector(sel);
      return (n?.innerText || n?.textContent || "").trim().replace(/\s+/g, " ");
    } catch {
      return "";
    }
  };
  const sender =
    pick(".yW .zF") ||
    pick(".yW span[email]") ||
    pick(".yW") ||
    pick("[email]");
  const subject = pick(".bog") || pick(".y6 span") || pick(".y6");
  const snippet = pick(".y2");
  const parts = [];
  if (sender) parts.push(sender.slice(0, 80));
  if (subject) parts.push(subject.slice(0, 120));
  else if (snippet) parts.push(snippet.slice(0, 100));
  if (!parts.length) return null;
  return parts.join(" — ").slice(0, 200);
}

/** Lower = keep earlier when filling interact_targets_max. */
function targetPriority(el) {
  if (isConversationRow(el)) return 0;
  const tag = (el.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea") return 1;
  if (tag === "a" || tag === "button") return 2;
  return 3;
}

function viewportInfo() {
  return {
    w: window.innerWidth,
    h: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio || 1,
  };
}

function rectFromEl(el) {
  const r = el.getBoundingClientRect();
  return {
    x: Math.round(r.x),
    y: Math.round(r.y),
    w: Math.round(r.width),
    h: Math.round(r.height),
  };
}

function centerFromRect(rect) {
  return {
    x: Math.round(rect.x + rect.w / 2),
    y: Math.round(rect.y + rect.h / 2),
  };
}

function isVisible(el) {
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  if (r.bottom < 0 || r.right < 0 || r.top > window.innerHeight || r.left > window.innerWidth) {
    return false;
  }
  const style = window.getComputedStyle(el);
  if (style.visibility === "hidden" || style.display === "none" || style.opacity === "0") {
    return false;
  }
  return true;
}

function isOccluded(el, center) {
  const hit = document.elementFromPoint(center.x, center.y);
  if (!hit) return true;
  return !(hit === el || el.contains(hit) || hit.contains(el));
}

function labelFor(el) {
  if (isConversationRow(el)) {
    const rowLabel = conversationRowLabel(el);
    if (rowLabel) return rowLabel;
  }
  const aria = el.getAttribute("aria-label");
  if (aria) return aria.slice(0, 200);
  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    const ref = document.getElementById(labelledBy);
    if (ref?.textContent) return ref.textContent.trim().slice(0, 200);
  }
  if (el.id) {
    const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (lab?.textContent) return lab.textContent.trim().slice(0, 200);
  }
  const title = el.getAttribute("title");
  if (title) return title.slice(0, 200);
  const text = (el.innerText || el.textContent || "").trim();
  if (text) return text.slice(0, 200);
  const tag = el.tagName.toLowerCase();
  const role = el.getAttribute("role") || tag;
  return `${role} element`;
}

function kindFor(el) {
  const tag = el.tagName.toLowerCase();
  if (tag === "input") {
    const t = (el.getAttribute("type") || "text").toLowerCase();
    if (t === "file") return "file";
    if (t === "checkbox" || t === "radio") return "toggle";
    return "input";
  }
  if (tag === "textarea" || tag === "select") return tag === "select" ? "select" : "input";
  const role = (el.getAttribute("role") || "").toLowerCase();
  if (role === "checkbox" || role === "radio" || role === "switch") return "toggle";
  if (role === "combobox" || role === "listbox") return "select";
  return "clickable";
}

function selectorHint(el) {
  if (el.id && !/\d{3,}/.test(el.id)) return `#${CSS.escape(el.id)}`;
  const name = el.getAttribute("name");
  if (name) return `${el.tagName.toLowerCase()}[name="${name.replace(/"/g, '\\"')}"]`;
  const aria = el.getAttribute("aria-label");
  if (aria) return `[aria-label="${aria.replace(/"/g, '\\"')}"]`;
  return "";
}

function selectorStable(el, hint) {
  if (!hint) return false;
  if (el.id && !/\d{3,}/.test(el.id)) return true;
  if (el.getAttribute("name")) return true;
  if (el.getAttribute("aria-label")) return true;
  return false;
}

function findScrollContainers(max) {
  const out = [];
  const walk = (root) => {
    const nodes = querySelectorAllDeep(root, "*");
    for (const el of nodes) {
      if (out.length >= max) return;
      if (!(el instanceof HTMLElement)) continue;
      const style = window.getComputedStyle(el);
      const oy = style.overflowY;
      if (oy !== "auto" && oy !== "scroll") continue;
      if (el.scrollHeight <= el.clientHeight + 4) continue;
      if (!isVisible(el)) continue;
      const rect = rectFromEl(el);
      const center = centerFromRect(rect);
      if (isOccluded(el, center)) continue;
      out.push({
        id: out.length + 1,
        ref: `s${out.length + 1}`,
        label: labelFor(el),
        rect,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        _el: el,
      });
    }
  };
  walk(document);
  return out.map(({ _el, ...rest }) => rest);
}

function buildTargetsFromMarked(marked, maxTargets) {
  const entries = Object.entries(marked)
    .sort((a, b) => targetPriority(a[1].element) - targetPriority(b[1].element))
    .slice(0, maxTargets);
  return entries.map(([label, entry], idx) => {
    const el = entry.element;
    const rect = rectFromEl(el);
    const center = centerFromRect(rect);
    const hint = selectorHint(el);
    return {
      id: idx + 1,
      ref: `t${idx + 1}`,
      mark_label: label,
      kind: kindFor(el),
      label: labelFor(el),
      text: (el.innerText || el.textContent || "").trim().slice(0, 500),
      role: el.getAttribute("role") || undefined,
      tag: el.tagName.toLowerCase(),
      rect,
      center,
      selector_hint: hint || undefined,
      selector_stable: selectorStable(el, hint),
    };
  });
}

function querySelectorAllDeep(root, selector, out = []) {
  if (!root) return out;
  try {
    root.querySelectorAll?.(selector)?.forEach((el) => out.push(el));
  } catch {
    /* invalid selector in some documents */
  }
  const walkRoots = root.querySelectorAll ? root.querySelectorAll("*") : [];
  for (const el of walkRoots) {
    if (el.shadowRoot) querySelectorAllDeep(el.shadowRoot, selector, out);
  }
  return out;
}

function heuristicScan(maxTargets) {
  const seen = new Set();
  const candidates = [];
  const addEl = (el) => {
    if (!el || seen.has(el)) return;
    seen.add(el);
    if (!isVisible(el)) return;
    const rect = rectFromEl(el);
    const center = centerFromRect(rect);
    if (isOccluded(el, center)) return;
    candidates.push(el);
  };
  querySelectorAllDeep(document, INTERACTIVE_SELECTOR).forEach(addEl);
  candidates.sort((a, b) => targetPriority(a) - targetPriority(b));
  return candidates.slice(0, maxTargets).map((el, idx) => {
    const rect = rectFromEl(el);
    const center = centerFromRect(rect);
    const hint = selectorHint(el);
    return {
      id: idx + 1,
      ref: `t${idx + 1}`,
      kind: kindFor(el),
      label: labelFor(el),
      text: (el.innerText || el.textContent || "").trim().slice(0, 500),
      role: el.getAttribute("role") || undefined,
      tag: el.tagName.toLowerCase(),
      rect,
      center,
      selector_hint: hint || undefined,
      selector_stable: selectorStable(el, hint),
    };
  });
}

/** Export for unit tests / background priority merge. */
export function targetSortKeyFromTarget(t) {
  const tag = (t?.tag || "").toLowerCase();
  const role = (t?.role || "").toLowerCase();
  if (tag === "tr" || role === "row") return 0;
  if (tag === "input" || tag === "textarea") return 1;
  if (tag === "a" || tag === "button") return 2;
  return 3;
}

export function deskObserve(opts = {}) {
  const maxTargets = opts.maxTargets ?? 40;
  const annotate = opts.annotate !== false;
  let interact_targets = [];
  try {
    if (annotate) {
      if (isMarked()) unmark();
      const marked = mark({
        selector: INTERACTIVE_SELECTOR,
        viewPortOnly: true,
        getLabel: (_el, index) => String(index),
        markAttribute: "data-desk-mark-label",
      });
      interact_targets = buildTargetsFromMarked(marked, maxTargets);
    } else {
      interact_targets = heuristicScan(maxTargets);
    }
  } catch {
    interact_targets = heuristicScan(maxTargets);
  }
  const scroll_containers = findScrollContainers(20).map((s, i) => ({
    ...s,
    id: i + 1,
    ref: `s${i + 1}`,
  }));
  const vp = viewportInfo();
  return {
    url: location.href,
    title: document.title,
    viewport: { w: vp.w, h: vp.h },
    device_pixel_ratio: vp.devicePixelRatio,
    interact_targets,
    scroll_containers,
    marked: annotate && isMarked(),
  };
}

export function deskUnmark() {
  try {
    if (isMarked()) unmark();
  } catch {
    /* ignore */
  }
}

function normalizeTargetId(raw) {
  if (raw == null || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function resolveTarget(targets, params) {
  const targetId = normalizeTargetId(params.target_id);
  if (targetId != null) {
    const t = targets.find((x) => x.id === targetId);
    if (t) return { target: t, used: "target_id" };
  }
  if (params.ref) {
    const t = targets.find((x) => x.ref === params.ref);
    if (t) return { target: t, used: "ref" };
  }
  const text = params.text || params.contains;
  if (text) {
    const lower = String(text).toLowerCase();
    const t = targets.find(
      (x) =>
        x.label?.toLowerCase().includes(lower) ||
        x.text?.toLowerCase().includes(lower),
    );
    if (t) return { target: t, used: "text" };
  }
  if (params.selector && params.selector_stable) {
    const el = document.querySelector(params.selector);
    if (el) return { element: el, used: "selector" };
  }
  if (params.x != null && params.y != null) {
    return { point: { x: params.x, y: params.y }, used: "coordinates" };
  }
  return { error: "stale_observe: could not resolve target" };
}

function elementFromTarget(target) {
  if (target.mark_label != null) {
    const el = document.querySelector(`[data-desk-mark-label="${target.mark_label}"]`);
    if (el) return el;
  }
  if (target.selector_hint && target.selector_stable) {
    const el = document.querySelector(target.selector_hint);
    if (el) return el;
  }
  const { center } = target;
  return document.elementFromPoint(center.x, center.y);
}

function dispatchClick(el) {
  el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  const rect = el.getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
    el.dispatchEvent(
      new MouseEvent(type, {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: x,
        clientY: y,
      }),
    );
  }
  if (typeof el.click === "function") el.click();
}

function dispatchKey(el, key) {
  const target = el || document.activeElement || document.body;
  if (target?.focus) target.focus();
  const isEnter = key === "Enter";
  const opts = {
    key,
    code: isEnter ? "Enter" : key,
    keyCode: isEnter ? 13 : 0,
    which: isEnter ? 13 : 0,
    bubbles: true,
    cancelable: true,
  };
  target.dispatchEvent(new KeyboardEvent("keydown", opts));
  if (isEnter) {
    target.dispatchEvent(new KeyboardEvent("keypress", opts));
  }
  target.dispatchEvent(new KeyboardEvent("keyup", opts));
  if (isEnter && target.form?.requestSubmit) {
    target.form.requestSubmit();
  }
}

function reactFill(el, value, { pressKey } = {}) {
  el.focus();
  const tag = el.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea") {
    const setter = Object.getOwnPropertyDescriptor(
      tag === "input" ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        cancelable: true,
        inputType: "insertText",
        data: value,
      }),
    );
    el.dispatchEvent(new Event("change", { bubbles: true }));
    if (pressKey) {
      dispatchKey(el, pressKey);
    } else {
      el.dispatchEvent(new Event("blur", { bubbles: true }));
    }
    return true;
  }
  if (el.isContentEditable) {
    el.textContent = value;
    el.dispatchEvent(new InputEvent("input", { bubbles: true }));
    if (pressKey) dispatchKey(el, pressKey);
    return true;
  }
  return false;
}

export function deskAct(op, params, targets, urlBefore) {
  if (op === "key") {
    let el = null;
    const targetId = normalizeTargetId(params.target_id);
    if (targetId != null) {
      const t = targets.find((x) => x.id === targetId);
      if (t) el = elementFromTarget(t);
    }
    if (!el && params.ref) {
      const t = targets.find((x) => x.ref === params.ref);
      if (t) el = elementFromTarget(t);
    }
    const key = params.key || "Enter";
    dispatchKey(el, key);
    const target = el || document.activeElement || document.body;
    return {
      ok: true,
      act_resolved: {
        op,
        requested: params,
        used: el ? "target_id" : "active_element",
        hit: { tag: target.tagName?.toLowerCase() },
        url_before: urlBefore,
        url_after: location.href,
      },
    };
  }
  const resolved = resolveTarget(targets, params);
  if (resolved.error) {
    return { ok: false, error: resolved.error, act_resolved: { op, requested: params, used: "none" } };
  }
  let hit = {};
  try {
    if (op === "scroll") {
      const dir = params.direction === "up" ? -1 : 1;
      const ratio = params.ratio ?? 0.85;
      if (resolved.target?.kind === "scroll_container") {
        const el = elementFromTarget(resolved.target);
        if (el) el.scrollBy(0, dir * el.clientHeight * ratio);
        hit = { ref: resolved.target.ref };
      } else {
        window.scrollBy(0, dir * window.innerHeight * ratio);
        hit = { tag: "window" };
      }
      return {
        ok: true,
        act_resolved: {
          op,
          requested: params,
          used: resolved.used,
          hit,
          url_before: urlBefore,
          url_after: location.href,
        },
      };
    }
    let el = resolved.element;
    if (!el && resolved.target) el = elementFromTarget(resolved.target);
    if (!el && resolved.point) el = document.elementFromPoint(resolved.point.x, resolved.point.y);
    if (!el) {
      return {
        ok: false,
        error: "element not found at target",
        act_resolved: { op, requested: params, used: resolved.used },
      };
    }
    hit = {
      ref: resolved.target?.ref,
      tag: el.tagName?.toLowerCase(),
      center: centerFromRect(rectFromEl(el)),
    };
    if (op === "click") {
      dispatchClick(el);
    } else if (op === "fill") {
      if (!reactFill(el, params.value ?? "", { pressKey: params.press_key })) {
        return { ok: false, error: "fill not supported on element", act_resolved: { op, requested: params, used: resolved.used } };
      }
    } else {
      return { ok: false, error: `unknown op: ${op}` };
    }
    return {
      ok: true,
      act_resolved: {
        op,
        requested: params,
        used: resolved.used,
        hit,
        url_before: urlBefore,
        url_after: location.href,
      },
    };
  } catch (err) {
    return {
      ok: false,
      error: String(err),
      act_resolved: { op, requested: params, used: resolved.used || "none" },
    };
  }
}

const TAG_ROLES = {
  A: "link",
  BUTTON: "button",
  INPUT: "input",
  SELECT: "select",
  TEXTAREA: "textarea",
  IMG: "image",
  TABLE: "table",
  TR: "row",
  TH: "columnheader",
  TD: "cell",
  FORM: "form",
  NAV: "navigation",
  MAIN: "main",
  HEADER: "banner",
  FOOTER: "contentinfo",
  ASIDE: "complementary",
  SECTION: "region",
  ARTICLE: "article",
  UL: "list",
  OL: "list",
  LI: "listitem",
  DIALOG: "dialog",
  H1: "heading",
  H2: "heading",
  H3: "heading",
  H4: "heading",
  H5: "heading",
  H6: "heading",
};

function axVisible(el) {
  if (!(el instanceof HTMLElement)) return true;
  if (el.getAttribute("aria-hidden") === "true") return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  if (parseFloat(style.opacity) === 0) return false;
  return true;
}

function axRole(el) {
  const aria = el.getAttribute?.("role");
  if (aria) return aria;
  const tag = el.tagName;
  if (TAG_ROLES[tag]) return TAG_ROLES[tag];
  if (tag === "INPUT") {
    const t = (el.type || "text").toLowerCase();
    if (t === "checkbox") return "checkbox";
    if (t === "radio") return "radio";
    if (t === "submit" || t === "button") return "button";
    return "textbox";
  }
  return null;
}

function axLabel(el) {
  const aria = el.getAttribute?.("aria-label");
  if (aria) return aria.slice(0, 80);
  const labelledBy = el.getAttribute?.("aria-labelledby");
  if (labelledBy) {
    const parts = labelledBy
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent?.trim())
      .filter(Boolean);
    if (parts.length) return parts.join(" ").slice(0, 80);
  }
  const tag = el.tagName;
  if (tag === "IMG") return (el.alt || el.title || "").slice(0, 80);
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    return (el.placeholder || el.title || "").slice(0, 80);
  }
  if (tag === "A" || tag === "BUTTON" || /^H[1-6]$/.test(tag)) {
    return (el.textContent || "").trim().slice(0, 80);
  }
  return "";
}

function axInteractive(el) {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  if (["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(tag)) return true;
  if (el.isContentEditable) return true;
  const role = el.getAttribute("role");
  return Boolean(
    role &&
      ["button", "link", "tab", "menuitem", "checkbox", "radio", "textbox", "switch", "option"].includes(
        role,
      ),
  );
}

function axStructural(el) {
  const tag = el.tagName;
  return (
    /^H[1-6]$/.test(tag) ||
    ["NAV", "MAIN", "HEADER", "FOOTER", "SECTION", "ARTICLE", "ASIDE", "TABLE", "FORM", "DIALOG"].includes(
      tag,
    )
  );
}

/**
 * Deep visible text for Eyes escalation (light DOM + open shadow).
 * Used when body.innerText settle is empty — not the default scrape path.
 */
export function deskDeepText(opts = {}) {
  const maxChars = opts.maxChars ?? 4000;
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "LINK", "META", "BR", "HR", "SVG", "PATH"]);
  const parts = [];
  let used = 0;

  function pushText(raw) {
    if (used >= maxChars) return;
    const t = (raw || "").replace(/\s+/g, " ").trim();
    if (!t || t.length < 2) return;
    const slice = t.slice(0, Math.min(200, maxChars - used));
    if (!slice) return;
    parts.push(slice);
    used += slice.length + 1;
  }

  function walk(node) {
    if (used >= maxChars || !node) return;
    if (node.nodeType === Node.TEXT_NODE) {
      pushText(node.textContent);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node;
    if (!axVisible(el)) return;
    const tag = el.tagName;
    if (SKIP.has(tag)) return;
    // Prefer element-level labels for status/alerts/headings before descending.
    if (
      /^H[1-6]$/.test(tag) ||
      ["MAIN", "ARTICLE", "DIALOG"].includes(tag) ||
      ["status", "alert", "heading"].includes((el.getAttribute("role") || "").toLowerCase())
    ) {
      const label = axLabel(el);
      if (label) pushText(label);
    }
    for (const child of el.childNodes) walk(child);
    if (el.shadowRoot) {
      for (const child of el.shadowRoot.childNodes) walk(child);
    }
  }

  if (document.body) walk(document.body);
  let text = parts.join("\n");
  if (text.length > maxChars) text = text.slice(0, maxChars);
  return {
    text,
    chars: text.length,
    url: location.href,
    title: document.title,
  };
}

/** Compact accessibility-ish tree for Eyes (URL-change / empty escalate). */
export function deskPageTree(opts = {}) {
  const maxNodes = opts.maxNodes ?? 400;
  const maxChars = opts.maxChars ?? 2000;
  let nodeCount = 0;
  const lines = [`Page: ${document.title}`, `URL: ${location.href}`, ""];

  function walk(node, depth) {
    if (nodeCount >= maxNodes || depth > 25) return;
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent?.trim();
      if (text && text.length > 1) {
        lines.push(`${" ".repeat(depth)}${text.slice(0, 80)}`);
        nodeCount++;
      }
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node;
    if (!axVisible(el)) return;
    const tag = el.tagName;
    if (["SCRIPT", "STYLE", "NOSCRIPT", "LINK", "META", "BR", "HR"].includes(tag)) return;
    const role = axRole(el);
    const label = axLabel(el);
    const should = role || axInteractive(el) || axStructural(el);
    if (should) {
      nodeCount++;
      const parts = [];
      if (role) parts.push(role);
      if (tag === "INPUT") parts.push(`type=${el.type || "text"}`);
      if (/^H[1-6]$/.test(tag)) parts.push(`level=${tag[1]}`);
      if (label) parts.push(`"${label}"`);
      if (el.value && ["INPUT", "TEXTAREA", "SELECT"].includes(tag)) {
        const t = (el.type || "").toLowerCase();
        if (t !== "password" && t !== "hidden") parts.push(`value="${String(el.value).slice(0, 80)}"`);
      }
      if (el.checked) parts.push("checked");
      if (tag === "A" && el.href) parts.push(`href=${String(el.href).slice(0, 80)}`);
      lines.push(`${" ".repeat(depth)}[${parts.join(" ")}]`);
    }
    const nextDepth = should ? depth + 1 : depth;
    // Walk light children always; also open-shadow kids (do not replace light).
    for (const child of el.childNodes) walk(child, nextDepth);
    if (el.shadowRoot) {
      for (const child of el.shadowRoot.childNodes) walk(child, nextDepth);
    }
  }

  if (document.body) walk(document.body, 0);
  let text = lines.join("\n");
  if (text.length > maxChars) text = `${text.slice(0, maxChars)}\n... (truncated)`;
  return { page_tree: text, nodes: nodeCount };
}

export function deskProbeForm() {
  const fields = [];
  querySelectorAllDeep(document, "input, textarea, select, [contenteditable=true]").forEach(
    (el, i) => {
      if (fields.length >= 40) return;
      if (!axVisible(el)) return;
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (type === "hidden" || type === "password") return;
      fields.push({
        id: i + 1,
        tag,
        type: tag === "input" ? type : tag,
        name: el.getAttribute("name") || undefined,
        label: labelFor(el),
        value:
          tag === "select"
            ? el.value
            : el.isContentEditable
              ? (el.textContent || "").slice(0, 200)
              : String(el.value || "").slice(0, 200),
        checked: el.checked || undefined,
      });
    },
  );
  return { form_fields: fields, url: location.href };
}

export function deskProbeLinks(max = 80) {
  const links = [];
  querySelectorAllDeep(document, "a[href]").forEach((a) => {
    if (links.length >= max) return;
    if (!axVisible(a)) return;
    const href = a.href || "";
    if (!href.startsWith("http")) return;
    links.push({
      text: (a.innerText || a.textContent || "").trim().slice(0, 120),
      href: href.slice(0, 500),
    });
  });
  return { links, url: location.href };
}

export function deskProbeTable(maxRows = 40) {
  const table =
    document.querySelector("table") ||
    document.querySelector('[role="table"]') ||
    document.querySelector('[role="grid"]');
  if (!table) return { rows: [], url: location.href, found: false };
  const rows = [];
  const trs = table.querySelectorAll("tr, [role=row]");
  trs.forEach((tr, i) => {
    if (i >= maxRows) return;
    const cells = [...tr.querySelectorAll("th, td, [role=cell], [role=columnheader], [role=gridcell]")].map(
      (c) => (c.innerText || c.textContent || "").trim().slice(0, 120),
    );
    if (cells.length) rows.push({ index: i, cells });
  });
  return { rows, url: location.href, found: true };
}

// UMD-style global for executeScript world injection
if (typeof globalThis !== "undefined") {
  globalThis.deskObserve = deskObserve;
  globalThis.deskUnmark = deskUnmark;
  globalThis.deskAct = deskAct;
  globalThis.deskPageTree = deskPageTree;
  globalThis.deskDeepText = deskDeepText;
  globalThis.deskProbeForm = deskProbeForm;
  globalThis.deskProbeLinks = deskProbeLinks;
  globalThis.deskProbeTable = deskProbeTable;
}
