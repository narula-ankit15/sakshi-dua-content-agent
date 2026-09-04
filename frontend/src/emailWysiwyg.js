// Lightweight WYSIWYG editing layer for the email preview iframe.
//
// Email HTML has to stay table-based to render in real inboxes (Outlook and
// a lot of mobile clients don't support position:absolute), so this never
// offers pixel-perfect drag placement -- dragging moves a block to a new
// position *among its existing siblings* (or drops a new text block into
// that same flow), it never drops something at an arbitrary x/y. Click text
// to edit it, select text to format it, drag a block's grip handle to
// reorder it, or drag the "+ Text" tool onto the canvas to add one.
//
// Dragging is implemented with plain mouse events (mousedown/mousemove/
// mouseup), not the native HTML5 Drag and Drop API -- native dragstart
// events are unreliable from inside a sandboxed iframe (the preview iframe
// intentionally has no "allow-scripts", to keep generated email HTML from
// ever executing code), so native drag silently never starts. Plain mouse
// events don't depend on that at all.
//
// Every control this module injects (styles, the grip/delete controls, the
// format toolbar, the "+ Text" tool) is tagged data-editor-ui and stripped
// back out by extractCleanHtml before the result is ever saved or sent --
// the exported HTML never contains editor chrome.

const INLINE_TAGS = new Set(["B", "STRONG", "I", "EM", "SPAN", "A", "BR", "U", "SMALL", "SUB", "SUP"]);
// Truly opaque -- no text worth editing inside, and no reason to recurse
// (recursing into <style> would offer its raw CSS text as "editable").
const OPAQUE_TAGS = new Set(["SCRIPT", "STYLE", "IMG", "HEAD", "TITLE", "META"]);
// Structural table/document scaffolding -- these can never be a leaf
// *themselves* (nobody wants contenteditable on a whole <table>), but the
// actual text in an email lives inside their descendants (<td>, <p>, ...),
// so unlike OPAQUE_TAGS these must still be recursed into.
const STRUCTURAL_TAGS = new Set(["HTML", "BODY", "TABLE", "TR", "TBODY", "THEAD", "TFOOT"]);

function isTextLeaf(el) {
  const hasDirectText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 0);
  const hasNonInlineChild = [...el.children].some((c) => !INLINE_TAGS.has(c.tagName));
  return hasDirectText && !hasNonInlineChild;
}

// Walks top-down and stops descending the first time it finds a text leaf,
// so e.g. a <p>Hello <b>world</b></p> gets marked once (the <p>), not once
// per inline child -- otherwise every bolded word would get its own set of
// drag/delete controls.
function findLeaves(el, out) {
  if (!el || el.nodeType !== 1) return;
  if (OPAQUE_TAGS.has(el.tagName)) return;
  if (el.hasAttribute("data-editor-ui")) return;
  if (!STRUCTURAL_TAGS.has(el.tagName) && isTextLeaf(el)) {
    out.push(el);
    return;
  }
  [...el.children].forEach((child) => findLeaves(child, out));
}

function injectStyles(doc) {
  const style = doc.createElement("style");
  style.setAttribute("data-editor-ui", "true");
  style.textContent = `
    [data-editable-block] { outline: 1px dashed transparent; outline-offset: 2px; cursor: text; transition: outline-color .1s; }
    [data-editable-block]:hover { outline-color: #4F46E5; }
    [data-editable-block]:focus { outline: 2px solid #4F46E5; }
    [data-editable-block].editor-dragging { opacity: 0.35; }
    [data-editable-block].editor-drop-before { box-shadow: inset 0 3px 0 0 #4F46E5; }
    [data-editable-block].editor-drop-after { box-shadow: inset 0 -3px 0 0 #4F46E5; }
    .editor-block-controls { display: inline-flex; gap: 2px; margin-left: 6px; vertical-align: middle; opacity: 0; transition: opacity .1s; user-select: none; }
    [data-editable-block]:hover .editor-block-controls, [data-editable-block]:focus .editor-block-controls { opacity: 1; }
    .editor-block-controls button, .editor-block-controls span {
      all: unset; cursor: pointer; font-size: 11px; line-height: 1; padding: 2px 5px;
      background: #111827; color: #fff; border-radius: 4px; font-family: sans-serif; display: inline-block;
    }
    .editor-block-controls .editor-grip { cursor: grab; }
    .editor-block-controls button:hover, .editor-block-controls .editor-grip:hover { background: #374151; }
    .editor-format-toolbar {
      position: absolute; display: flex; flex-wrap: wrap; align-items: center; gap: 2px; background: #111827;
      padding: 4px; border-radius: 8px; max-width: 480px;
      box-shadow: 0 4px 12px rgba(0,0,0,.25); z-index: 999999; font-family: sans-serif;
    }
    .editor-format-toolbar button {
      all: unset; cursor: pointer; font-size: 12px; padding: 4px 8px; color: #fff; border-radius: 4px; font-family: sans-serif; min-width: 22px; text-align: center;
    }
    .editor-format-toolbar button:hover { background: #374151; }
    .editor-format-toolbar .ef-divider { width: 1px; align-self: stretch; margin: 2px 3px; background: #374151; }
    .editor-format-toolbar select.ef-select {
      background: #1f2937; color: #fff; border: none; border-radius: 4px; font-size: 11.5px;
      padding: 4px 4px; max-width: 92px; font-family: sans-serif; cursor: pointer;
    }
    .editor-format-toolbar select.ef-select--font { max-width: 108px; }
    .editor-format-toolbar .ef-group {
      display: inline-flex; align-items: center; gap: 2px; background: #1f2937; border-radius: 4px; padding: 0 2px;
    }
    .editor-format-toolbar .ef-group button { padding: 4px 6px; min-width: 16px; }
    .editor-format-toolbar .ef-size-value { font-size: 11.5px; min-width: 16px; text-align: center; }
    .editor-format-toolbar .ef-color {
      position: relative; display: inline-flex; flex-direction: column; align-items: center; cursor: pointer;
      padding: 3px 6px 5px; border-radius: 4px; font-size: 13px; line-height: 1;
    }
    .editor-format-toolbar .ef-color:hover { background: #374151; }
    .editor-format-toolbar .ef-color::after {
      content: ""; display: block; width: 16px; height: 3px; border-radius: 2px; margin-top: 3px;
      background: linear-gradient(90deg, red, orange, yellow, green, blue, violet);
    }
    .editor-format-toolbar .ef-color input[type="color"] {
      position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; border: none; padding: 0;
    }
    .editor-add-text-tool {
      position: fixed; bottom: 16px; right: 16px; z-index: 999999;
      display: flex; align-items: center; gap: 6px;
      background: #4F46E5; color: #fff; padding: 8px 14px; border-radius: 999px;
      font-family: sans-serif; font-size: 12.5px; font-weight: 600; cursor: grab;
      box-shadow: 0 4px 14px rgba(17,24,39,.35); user-select: none;
    }
    .editor-add-text-tool.editor-dragging { opacity: 0.5; }
    .editor-undo-hint {
      position: fixed; bottom: 16px; left: 16px; z-index: 999999;
      background: rgba(17,24,39,.85); color: #fff; padding: 5px 10px; border-radius: 6px;
      font-family: sans-serif; font-size: 11px; user-select: none; pointer-events: none;
    }
  `;
  doc.head.appendChild(style);
}

function clearDropHighlight(el) {
  el?.classList.remove("editor-drop-before", "editor-drop-after");
}

// Drives a plain-mouse-events drag for one gesture (either an existing
// block's grip, or the "+ Text" tool). `onDrop(target, before)` is called
// once, only if the pointer was released over a valid same-parent sibling
// target; nothing happens on a release elsewhere (e.g. off the canvas).
function startMouseDrag(doc, handleEl, sourceBlock, { isValidTarget, onDrop }) {
  let currentTarget = null;
  let currentBefore = true;

  if (sourceBlock) sourceBlock.classList.add("editor-dragging");
  else handleEl.classList.add("editor-dragging");

  function onMouseMove(e) {
    const el = doc.elementFromPoint(e.clientX, e.clientY);
    const target = el?.closest?.("[data-editable-block]") || null;
    if (target !== currentTarget) {
      clearDropHighlight(currentTarget);
      currentTarget = target && isValidTarget(target) ? target : null;
    }
    if (currentTarget) {
      const rect = currentTarget.getBoundingClientRect();
      currentBefore = e.clientY < rect.top + rect.height / 2;
      currentTarget.classList.toggle("editor-drop-before", currentBefore);
      currentTarget.classList.toggle("editor-drop-after", !currentBefore);
    }
  }

  function finish() {
    doc.removeEventListener("mousemove", onMouseMove);
    doc.removeEventListener("mouseup", finish);
    sourceBlock?.classList.remove("editor-dragging");
    handleEl.classList.remove("editor-dragging");
    clearDropHighlight(currentTarget);
    if (currentTarget) onDrop(currentTarget, currentBefore);
  }

  doc.addEventListener("mousemove", onMouseMove);
  doc.addEventListener("mouseup", finish);
}

function addControls(doc, el, { onChangeNow, snapshot, isValidTarget, moveBlock }) {
  const controls = doc.createElement("span");
  controls.setAttribute("data-editor-ui", "true");
  controls.setAttribute("contenteditable", "false");
  controls.className = "editor-block-controls";
  controls.innerHTML = `
    <span class="editor-grip" title="Drag to reorder">⠿</span>
    <button type="button" data-action="delete" title="Delete">×</button>
  `;
  // Without this, interacting with a control first collapses/moves the
  // text selection (since mousedown normally sets focus/caret), which
  // would fire right before the click/drag handler runs.
  controls.addEventListener("mousedown", (e) => {
    if (e.target.closest(".editor-grip")) return; // the grip needs its own mousedown below
    e.preventDefault();
  });
  controls.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    if (btn.dataset.action === "delete") {
      snapshot();
      el.remove();
      onChangeNow();
    }
  });
  const grip = controls.querySelector(".editor-grip");
  grip.addEventListener("mousedown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    startMouseDrag(doc, grip, el, {
      isValidTarget: (target) => target !== el && isValidTarget(target, el),
      onDrop: (target, before) => {
        snapshot();
        moveBlock(el, target, before);
        onChangeNow();
      },
    });
  });
  el.appendChild(controls);
}

function markEditable(doc, el, deps) {
  el.setAttribute("contenteditable", "true");
  el.setAttribute("data-editable-block", "true");
  el.addEventListener("input", deps.onChangeDebounced);
  el.addEventListener("focus", deps.onFocusSnapshot);
  addControls(doc, el, deps);
}

// Email-safe web fonts only -- anything else silently falls back to the
// recipient's default font in most inboxes (Gmail/Outlook don't load
// arbitrary web fonts), so offering more than this would be a false promise.
const FONT_OPTIONS = [
  ["Arial, Helvetica, sans-serif", "Arial"],
  ["Helvetica, Arial, sans-serif", "Helvetica"],
  ["Georgia, 'Times New Roman', serif", "Georgia"],
  ["'Times New Roman', Times, serif", "Times New Roman"],
  ["Verdana, Geneva, sans-serif", "Verdana"],
  ["Tahoma, Geneva, sans-serif", "Tahoma"],
  ["'Trebuchet MS', Helvetica, sans-serif", "Trebuchet MS"],
  ["'Courier New', Courier, monospace", "Courier New"],
];

const HEADING_PRESETS = {
  P: { label: "Normal", fontSize: 15, fontWeight: 400 },
  H1: { label: "Heading 1", fontSize: 28, fontWeight: 700 },
  H2: { label: "Heading 2", fontSize: 22, fontWeight: 700 },
  H3: { label: "Heading 3", fontSize: 18, fontWeight: 700 },
};

function setupFormatToolbar(doc, { onChangeDebounced, snapshot, markEditableFn }) {
  let toolbarEl = null;
  let currentBlock = null;

  function removeToolbar() {
    if (toolbarEl) {
      toolbarEl.remove();
      toolbarEl = null;
    }
  }

  // Shared by every character-level format (color, highlight, font, size,
  // spacing) -- wraps the current selection in a fresh <span> carrying the
  // new style. Block-level formats (heading, align, indent) don't go
  // through this; they mutate the containing block directly instead.
  function wrapSelection(styleSetter) {
    const sel = doc.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const range = sel.getRangeAt(0);
    try {
      const span = doc.createElement("span");
      const container = range.startContainer.nodeType === 3 ? range.startContainer.parentElement : range.startContainer;
      styleSetter(span, container);
      range.surroundContents(span);
      sel.removeAllRanges();
      const newRange = doc.createRange();
      newRange.selectNodeContents(span);
      sel.addRange(newRange);
    } catch {
      // The selection spans more than one element -- surroundContents can't
      // wrap that safely. Skipping the format beats corrupting the DOM.
    }
  }

  function currentComputedStyle(prop, fallback) {
    const sel = doc.getSelection();
    if (!sel || sel.rangeCount === 0) return fallback;
    const node = sel.getRangeAt(0).startContainer;
    const el = node.nodeType === 3 ? node.parentElement : node;
    if (!el) return fallback;
    return doc.defaultView.getComputedStyle(el)[prop] || fallback;
  }

  function changeHeading(tag) {
    if (!currentBlock) return;
    const preset = HEADING_PRESETS[tag];
    const clone = currentBlock.cloneNode(true);
    clone.querySelectorAll("[data-editor-ui]").forEach((el) => el.remove());
    const replacement = doc.createElement(tag);
    replacement.innerHTML = clone.innerHTML;
    replacement.style.cssText = `margin:0;font-family:inherit;font-size:${preset.fontSize}px;font-weight:${preset.fontWeight};`;
    currentBlock.parentNode.replaceChild(replacement, currentBlock);
    markEditableFn(replacement);
    currentBlock = replacement;
  }

  function applyFormat(cmd, value) {
    snapshot();
    switch (cmd) {
      case "bold":
      case "italic":
      case "underline":
      case "strikethrough":
        doc.execCommand(cmd === "strikethrough" ? "strikeThrough" : cmd);
        break;
      case "bullet-list":
        doc.execCommand("insertUnorderedList");
        break;
      case "bigger":
      case "smaller":
        wrapSelection((span, container) => {
          const cur = parseFloat(doc.defaultView.getComputedStyle(container).fontSize) || 14;
          span.style.fontSize = `${Math.max(10, cur + (cmd === "bigger" ? 2 : -2))}px`;
        });
        break;
      case "color":
        wrapSelection((span) => (span.style.color = value));
        break;
      case "highlight":
        wrapSelection((span) => (span.style.backgroundColor = value));
        break;
      case "font":
        wrapSelection((span) => (span.style.fontFamily = value));
        break;
      case "spacing-more":
      case "spacing-less":
        wrapSelection((span, container) => {
          const cur = parseFloat(doc.defaultView.getComputedStyle(container).letterSpacing) || 0;
          span.style.letterSpacing = `${cur + (cmd === "spacing-more" ? 0.5 : -0.5)}px`;
        });
        break;
      case "heading":
        changeHeading(value);
        break;
      case "align-left":
      case "align-center":
      case "align-right":
      case "align-justify":
        if (currentBlock) currentBlock.style.textAlign = cmd.replace("align-", "");
        break;
      case "indent":
        if (currentBlock) {
          const cur = parseFloat(currentBlock.style.marginLeft) || 0;
          currentBlock.style.marginLeft = `${cur + 24}px`;
        }
        break;
      case "outdent":
        if (currentBlock) {
          const cur = parseFloat(currentBlock.style.marginLeft) || 0;
          currentBlock.style.marginLeft = `${Math.max(0, cur - 24)}px`;
        }
        break;
      default:
        break;
    }
  }

  function showToolbar(rect, block) {
    removeToolbar();
    currentBlock = block;
    const headingTag = ["H1", "H2", "H3"].includes(block.tagName) ? block.tagName : "P";
    const currentSize = Math.round(parseFloat(currentComputedStyle("fontSize", "15")));
    const currentFont = currentComputedStyle("fontFamily", FONT_OPTIONS[0][0]);
    const fontMatch = FONT_OPTIONS.find(([value]) => currentFont.startsWith(value.split(",")[0].replace(/'/g, "")));

    toolbarEl = doc.createElement("div");
    toolbarEl.setAttribute("data-editor-ui", "true");
    toolbarEl.className = "editor-format-toolbar";
    toolbarEl.innerHTML = `
      <select class="ef-select" data-cmd="heading" title="Text style">
        ${Object.entries(HEADING_PRESETS)
          .map(([tag, p]) => `<option value="${tag}" ${tag === headingTag ? "selected" : ""}>${p.label}</option>`)
          .join("")}
      </select>
      <select class="ef-select ef-select--font" data-cmd="font" title="Font">
        ${FONT_OPTIONS.map(([value, label]) => `<option value="${value}" ${fontMatch?.[0] === value ? "selected" : ""}>${label}</option>`).join("")}
      </select>
      <span class="ef-group">
        <button type="button" data-cmd="smaller" title="Smaller text">−</button>
        <span class="ef-size-value">${currentSize}</span>
        <button type="button" data-cmd="bigger" title="Bigger text">+</button>
      </span>
      <span class="ef-divider"></span>
      <label class="ef-color" title="Text color">A<input type="color" data-cmd="color" value="#111827"></label>
      <label class="ef-color ef-color--highlight" title="Highlight color">🖍<input type="color" data-cmd="highlight" value="#fff59d"></label>
      <span class="ef-divider"></span>
      <button type="button" data-cmd="bold" title="Bold"><b>B</b></button>
      <button type="button" data-cmd="italic" title="Italic"><i>I</i></button>
      <button type="button" data-cmd="underline" title="Underline"><u>U</u></button>
      <button type="button" data-cmd="strikethrough" title="Strikethrough"><s>S</s></button>
      <span class="ef-divider"></span>
      <button type="button" data-cmd="align-left" title="Align left">L</button>
      <button type="button" data-cmd="align-center" title="Align center">C</button>
      <button type="button" data-cmd="align-right" title="Align right">R</button>
      <button type="button" data-cmd="align-justify" title="Justify">J</button>
      <span class="ef-divider"></span>
      <button type="button" data-cmd="bullet-list" title="Bulleted list">☰</button>
      <span class="ef-divider"></span>
      <button type="button" data-cmd="spacing-less" title="Decrease letter spacing">⇔−</button>
      <button type="button" data-cmd="spacing-more" title="Increase letter spacing">⇔+</button>
      <button type="button" data-cmd="outdent" title="Decrease indent">⇤</button>
      <button type="button" data-cmd="indent" title="Increase indent">⇥</button>
    `;
    doc.body.appendChild(toolbarEl);
    const scrollY = doc.defaultView.scrollY;
    const scrollX = doc.defaultView.scrollX;
    const toolbarHeight = toolbarEl.offsetHeight;
    // rect.top/.bottom are viewport-relative (i.e. already account for
    // current scroll), so they're what decide whether there's room *on
    // screen* above the selection -- not just room within the document.
    // Selecting text near the top of the scrolled preview would otherwise
    // place the toolbar above the visible viewport, making it invisible.
    const top =
      rect.top > toolbarHeight + 12
        ? rect.top + scrollY - toolbarHeight - 8
        : rect.bottom + scrollY + 8;
    const left = rect.left + scrollX;
    toolbarEl.style.top = `${Math.max(4, top)}px`;
    toolbarEl.style.left = `${Math.max(4, Math.min(left, doc.defaultView.innerWidth + scrollX - toolbarEl.offsetWidth - 4))}px`;
    toolbarEl.addEventListener("mousedown", (e) => {
      // Color inputs need their own native mousedown to open the picker --
      // preventing it here would block that. Everything else must not
      // steal focus/selection away from the text being formatted.
      if (e.target.matches('input[type="color"]')) return;
      e.preventDefault();
    });
    toolbarEl.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      e.preventDefault();
      applyFormat(btn.dataset.cmd);
      onChangeDebounced();
    });
    toolbarEl.addEventListener("input", (e) => {
      const input = e.target.closest('input[type="color"]');
      if (input) {
        applyFormat(input.dataset.cmd, input.value);
        onChangeDebounced();
      }
    });
    toolbarEl.addEventListener("change", (e) => {
      const select = e.target.closest("select");
      if (select) {
        applyFormat(select.dataset.cmd, select.value);
        onChangeDebounced();
      }
    });
  }

  doc.addEventListener("selectionchange", () => {
    const sel = doc.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
      removeToolbar();
      return;
    }
    const anchorEl = sel.anchorNode?.nodeType === 3 ? sel.anchorNode.parentElement : sel.anchorNode;
    const block = anchorEl?.closest("[data-editable-block]");
    if (!block) {
      removeToolbar();
      return;
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      removeToolbar();
      return;
    }
    showToolbar(rect, block);
  });
}

function addTextTool(doc, { onChangeNow, snapshot, isValidTarget, insertNewTextBlock }) {
  const tool = doc.createElement("div");
  tool.setAttribute("data-editor-ui", "true");
  tool.className = "editor-add-text-tool";
  tool.textContent = "⠿ + Text (drag onto the email)";
  tool.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startMouseDrag(doc, tool, null, {
      isValidTarget: (target) => isValidTarget(target, null),
      onDrop: (target, before) => {
        snapshot();
        insertNewTextBlock(target, before);
        onChangeNow();
      },
    });
  });
  doc.body.appendChild(tool);
}

function showUndoHint(doc) {
  if (doc.querySelector(".editor-undo-hint")) return;
  const hint = doc.createElement("div");
  hint.setAttribute("data-editor-ui", "true");
  hint.className = "editor-undo-hint";
  hint.textContent = (navigator.platform.includes("Mac") ? "⌘Z" : "Ctrl+Z") + " to undo";
  doc.body.appendChild(hint);
}

// Turns on click-to-edit/select-to-format/drag-to-reorder-or-add, plus
// Ctrl/Cmd+Z (and Shift+ for redo), for the given iframe document. Call
// once per editing session (e.g. on the iframe's onLoad while entering edit
// mode) -- calling it twice would double-mark every block. onChange fires
// (debounced for typing, immediately for structural edits) with the
// freshly-cleaned HTML string.
export function enableEditing(doc, { onChange }) {
  let debounceTimer = null;
  const onChangeDebounced = () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => onChange(extractCleanHtml(doc)), 400);
  };
  const onChangeNow = () => onChange(extractCleanHtml(doc));

  injectStyles(doc);

  const undoStack = [];
  const redoStack = [];
  let lastFocusSnapshotEl = null;

  function snapshotBody() {
    const clone = doc.body.cloneNode(true);
    clone.querySelectorAll("[data-editor-ui]").forEach((el) => el.remove());
    clone.querySelectorAll("[contenteditable]").forEach((el) => el.removeAttribute("contenteditable"));
    clone.querySelectorAll("[data-editable-block]").forEach((el) => el.removeAttribute("data-editable-block"));
    return clone.innerHTML;
  }

  function snapshot() {
    undoStack.push(snapshotBody());
    if (undoStack.length > 50) undoStack.shift();
    redoStack.length = 0;
  }

  function isValidTarget(target, source) {
    if (!target) return false;
    if (source) return target.parentNode === source.parentNode;
    return true; // the "+ Text" tool can drop next to any block
  }

  function moveBlock(source, target, before) {
    target.parentNode.insertBefore(source, before ? target : target.nextSibling);
  }

  function insertNewTextBlock(target, before) {
    const p = doc.createElement("p");
    p.textContent = "New text";
    p.style.cssText = "font-size:15px;color:#1a1a1a;margin:16px 40px;font-family:Helvetica,Arial,sans-serif;";
    target.parentNode.insertBefore(p, before ? target : target.nextSibling);
    markEditable(doc, p, blockDeps);
    p.focus();
    const range = doc.createRange();
    range.selectNodeContents(p);
    const sel = doc.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  const blockDeps = {
    onChangeNow,
    onChangeDebounced,
    snapshot,
    isValidTarget,
    moveBlock,
    onFocusSnapshot: (e) => {
      // One snapshot per "session" of typing in a block, taken right as it
      // gains focus (before any of this round's edits) -- not per
      // keystroke, or undo would only ever revert one character at a time.
      const el = e.target;
      if (lastFocusSnapshotEl === el) return;
      lastFocusSnapshotEl = el;
      snapshot();
    },
  };

  function setupContent(root) {
    const leaves = [];
    findLeaves(root, leaves);
    leaves.forEach((el) => markEditable(doc, el, blockDeps));
  }

  function restore(stack, otherStack) {
    if (stack.length === 0) return;
    otherStack.push(snapshotBody());
    doc.body.innerHTML = stack.pop();
    setupContent(doc.body);
    addTextTool(doc, { onChangeNow, snapshot, isValidTarget, insertNewTextBlock });
    showUndoHint(doc);
    lastFocusSnapshotEl = null;
    onChangeNow();
  }

  doc.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
    e.preventDefault();
    if (e.shiftKey) restore(redoStack, undoStack);
    else restore(undoStack, redoStack);
  });

  setupContent(doc.body);
  setupFormatToolbar(doc, { onChangeDebounced, snapshot, markEditableFn: (el) => markEditable(doc, el, blockDeps) });
  addTextTool(doc, { onChangeNow, snapshot, isValidTarget, insertNewTextBlock });
  showUndoHint(doc);
}

// Clones the document, strips every bit of editor-only chrome this module
// injects (contenteditable, the data-editable-block marker, and anything
// tagged data-editor-ui: the <style>, per-block controls, format toolbar,
// the "+ Text" tool), and returns a plain "<!doctype html>..." string safe
// to save or send.
export function extractCleanHtml(doc) {
  const clone = doc.documentElement.cloneNode(true);
  clone.querySelectorAll("[data-editor-ui]").forEach((el) => el.remove());
  clone.querySelectorAll("[contenteditable]").forEach((el) => el.removeAttribute("contenteditable"));
  clone.querySelectorAll("[data-editable-block]").forEach((el) => el.removeAttribute("data-editable-block"));
  return `<!doctype html>\n${clone.outerHTML}`;
}
