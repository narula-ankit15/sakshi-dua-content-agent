import { useEffect, useRef, useState } from "react";
import { getEmailSenders, getEmailSends, sendEmail } from "../api";
import ConfirmDialog from "./ConfirmDialog";
import LeadContactPicker from "./LeadContactPicker";
import { enableEditing, extractCleanHtml } from "../emailWysiwyg";

const ASSET_SCHEME_RE = /asset:\/\/([a-zA-Z0-9_-]+)/g;
const MAX_RECIPIENTS = 50;

// Splits a pasted block on commas AND newlines (people paste both -- a
// column copied from a spreadsheet is newline-separated, a comma-separated
// list from an email client is commas), trims, drops blanks, and dedupes
// case-insensitively so the same address pasted twice doesn't count twice
// against the cap or send twice.
function parseRecipients(text) {
  const seen = new Set();
  const result = [];
  for (const raw of text.split(/[,\n]/)) {
    const addr = raw.trim();
    if (!addr) continue;
    const key = addr.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(addr);
  }
  return result;
}

function resolveAssetPlaceholders(htmlBody, assetsById) {
  // The email agent doesn't know real asset URLs, so it's instructed to emit
  // src="asset://{asset_id}" instead of inventing one -- resolve those here.
  return htmlBody.replace(ASSET_SCHEME_RE, (match, assetId) => assetsById?.[assetId]?.url || match);
}

function buildPreviewDoc(htmlBody, assetsById) {
  // Wraps a raw fragment in email-safe defaults (max-width, font, background)
  // so it renders like it would in an actual inbox, not a bare fragment.
  const resolved = resolveAssetPlaceholders(htmlBody, assetsById);
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body { margin: 0; padding: 24px; background: #f1f0f7; font-family: Arial, Helvetica, sans-serif; }
  .email-canvas { max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  img { max-width: 100%; height: auto; }
</style>
</head>
<body>
  <div class="email-canvas">${resolved}</div>
</body>
</html>`;
}

// onHtmlChange is optional -- when given, a manual HTML Code edit is lifted
// back up to the caller's draft (so Save/Update actually persists it)
// instead of only ever live-updating the Preview tab in this component's
// own local state. Left undefined in read-only contexts (e.g. DetailPanel,
// which has nowhere to save to), where editing here still live-previews
// but intentionally goes nowhere once you navigate away.
export default function EmailPreview({ subjectLines, selectedSubjectIndex = 0, htmlBody, assetsById, creativeId, onHtmlChange }) {
  const [tab, setTab] = useState("preview");
  const [code, setCode] = useState(htmlBody);
  const [showSendPanel, setShowSendPanel] = useState(false);
  const [sendToText, setSendToText] = useState("");
  const [showContactPicker, setShowContactPicker] = useState(false);
  const [confirmingSend, setConfirmingSend] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState(null);
  const recipients = parseRecipients(sendToText);
  const overCap = recipients.length > MAX_RECIPIENTS;
  const [sendHistory, setSendHistory] = useState([]);
  const [senders, setSenders] = useState([]);
  const [selectedSenderId, setSelectedSenderId] = useState(null);
  const activeSubject = subjectLines[selectedSubjectIndex] ?? subjectLines[0];
  const [subjectText, setSubjectText] = useState(activeSubject);
  const [editingSubject, setEditingSubject] = useState(false);

  // Click-to-edit/select-to-format editing of the rendered preview (as
  // opposed to the raw HTML Code tab). editModeSrcDoc is a *frozen*
  // snapshot taken once on entry -- the iframe's srcDoc must not change
  // again while editing, or React reloads the iframe (wiping the live DOM,
  // cursor, and any in-progress edit) on every keystroke. Edits are synced
  // out to `code`/onHtmlChange via the editor's own onChange callback
  // instead, without ever touching editModeSrcDoc.
  const [editMode, setEditMode] = useState(false);
  const [editModeSrcDoc, setEditModeSrcDoc] = useState(null);
  const iframeRef = useRef(null);

  useEffect(() => {
    setCode(htmlBody);
  }, [htmlBody]);

  useEffect(() => {
    // Fetched once -- the list of configured "send as" identities doesn't
    // change during a session. Whichever comes first is the default
    // selection, so the backend's EMAIL_SENDERS order is the source of
    // truth for which identity is preferred.
    let cancelled = false;
    getEmailSenders()
      .then((list) => {
        if (cancelled) return;
        setSenders(list);
        if (list.length > 0) setSelectedSenderId(list[0].id);
      })
      .catch(() => {
        if (!cancelled) setSenders([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // A different subject-line chip was picked (or a different entry was
    // opened) -- drop any in-progress manual edit and resync.
    setSubjectText(activeSubject);
    setEditingSubject(false);
  }, [activeSubject]);

  useEffect(() => {
    // Only a saved library entry has a creative_id -- an unsaved draft
    // preview has nothing to look up a history for yet.
    if (!creativeId) {
      setSendHistory([]);
      return;
    }
    let cancelled = false;
    getEmailSends(creativeId)
      .then((records) => {
        if (!cancelled) setSendHistory(records);
      })
      .catch(() => {
        if (!cancelled) setSendHistory([]);
      });
    return () => {
      cancelled = true;
    };
  }, [creativeId]);

  function handleViewInBrowser() {
    // Blob URL (not a data: URI) so the tab is a real same-origin-ish
    // document -- large HTML survives, and it isn't subject to the
    // preview iframe's sandbox="" restrictions.
    const blob = new Blob([buildPreviewDoc(code, assetsById)], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    // Open blank first (without the "noopener" feature string, which makes
    // some browsers always return null even on success) so we can reliably
    // tell whether it was actually blocked, then strip window.opener by
    // hand -- same security effect as noopener, without losing detection.
    const newTab = window.open("", "_blank");
    if (newTab) {
      newTab.opener = null;
      newTab.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } else {
      // Genuinely blocked -- fall back to navigating this tab.
      window.location.href = url;
    }
  }

  function handleDownloadHtml() {
    const blob = new Blob([buildPreviewDoc(code, assetsById)], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const slug =
      (subjectText || "email")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 60) || "email";
    const link = document.createElement("a");
    link.href = url;
    link.download = `${slug}.html`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function handleToggleEditMode() {
    if (editMode) {
      // Exiting -- do one last sync from the live DOM before tearing it down.
      const doc = iframeRef.current?.contentDocument;
      if (doc) {
        const clean = extractCleanHtml(doc);
        setCode(clean);
        onHtmlChange?.(clean);
      }
      setEditMode(false);
      setEditModeSrcDoc(null);
    } else {
      setTab("preview");
      setEditModeSrcDoc(resolveAssetPlaceholders(code, assetsById));
      setEditMode(true);
    }
  }

  function handleIframeLoad() {
    if (!editMode) return;
    const doc = iframeRef.current?.contentDocument;
    if (!doc) return;
    enableEditing(doc, {
      onChange: (html) => {
        setCode(html);
        onHtmlChange?.(html);
      },
    });
  }

  function handleContactsSelected(emails) {
    setShowContactPicker(false);
    const merged = parseRecipients([...recipients, ...emails].join(", "));
    setSendToText(merged.join(", "));
  }

  function handleSendFormSubmit(e) {
    e.preventDefault();
    if (recipients.length === 0 || overCap || sending) return;
    // A real, irreversible send from the user's own configured Gmail
    // account -- one more explicit confirmation beyond just clicking
    // "Send", since there's no undo once Gmail has accepted it.
    setConfirmingSend(true);
  }

  async function performSend() {
    setConfirmingSend(false);
    setSending(true);
    setSendResult(null);
    try {
      const response = await sendEmail({
        to: recipients,
        subject: subjectText,
        html_body: buildPreviewDoc(code, assetsById),
        creative_id: creativeId || null,
        sender_id: selectedSenderId,
      });
      const results = response.results;
      const succeeded = results.filter((r) => r.sent);
      const failed = results.filter((r) => !r.sent);
      setSendResult({
        ok: failed.length === 0,
        message:
          failed.length === 0
            ? `Sent to ${succeeded.length} recipient${succeeded.length === 1 ? "" : "s"}.`
            : `Sent to ${succeeded.length} of ${results.length}, ${failed.length} failed.`,
        failed,
      });
      if (creativeId && succeeded.length > 0) {
        const now = new Date().toISOString();
        setSendHistory((prev) => [...succeeded.map((r) => ({ to_email: r.to, sent_at: now })), ...prev]);
      }
      if (failed.length === 0) setSendToText("");
    } catch (err) {
      setSendResult({ ok: false, message: err.message || "Couldn't send the email.", failed: [] });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="email-preview">
      <div className="email-preview__chrome">
        <span className="email-preview__dot email-preview__dot--red" />
        <span className="email-preview__dot email-preview__dot--amber" />
        <span className="email-preview__dot email-preview__dot--green" />
        {editingSubject ? (
          <input
            type="text"
            className="email-preview__subject-input"
            value={subjectText}
            autoFocus
            onChange={(e) => setSubjectText(e.target.value)}
            onBlur={() => setEditingSubject(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                setEditingSubject(false);
              } else if (e.key === "Escape") {
                setSubjectText(activeSubject);
                setEditingSubject(false);
              }
            }}
          />
        ) : (
          <>
            <span className="email-preview__subject">Subject: {subjectText}</span>
            <button
              type="button"
              className="email-preview__subject-edit"
              onClick={() => setEditingSubject(true)}
              aria-label="Edit subject line"
              title="Edit subject line"
            >
              ✎
            </button>
          </>
        )}
      </div>

      <div className="email-preview__tabs">
        <button
          className={`email-preview__tab ${tab === "preview" ? "email-preview__tab--active" : ""}`}
          onClick={() => setTab("preview")}
          type="button"
        >
          Preview
        </button>
        <button
          className={`email-preview__tab ${tab === "code" ? "email-preview__tab--active" : ""}`}
          onClick={() => setTab("code")}
          type="button"
        >
          HTML Code
        </button>
        <button
          className={`email-preview__view-in-browser ${editMode ? "email-preview__tab--active" : ""}`}
          onClick={handleToggleEditMode}
          type="button"
        >
          {editMode ? "✓ Done Editing" : "✎ Edit Text"}
        </button>
        <button
          className="email-preview__icon-btn"
          onClick={handleViewInBrowser}
          type="button"
          aria-label="View in browser"
          title="View in browser"
        >
          ↗
        </button>
        <button
          className="email-preview__icon-btn"
          onClick={handleDownloadHtml}
          type="button"
          aria-label="Download HTML"
          title="Download HTML"
        >
          ⬇
        </button>
        <button
          className="email-preview__icon-btn"
          onClick={() => {
            setShowSendPanel((v) => !v);
            setSendResult(null);
          }}
          type="button"
          aria-label="Send Email"
          title="Send Email"
        >
          ✉
          {creativeId && sendHistory.length > 0 && (
            <span className="email-preview__icon-btn__badge">{sendHistory.length}</span>
          )}
        </button>
      </div>

      {showSendPanel && (
        <div className="email-preview__send-panel-wrap">
          <form className="email-preview__send-panel" onSubmit={handleSendFormSubmit}>
            {senders.length > 1 && (
              <div className="email-preview__sender-picker">
                <label className="email-preview__sender-label" htmlFor="email-sender-select">
                  Send from
                </label>
                <select
                  id="email-sender-select"
                  className="filter-bar__input"
                  value={selectedSenderId || ""}
                  onChange={(e) => setSelectedSenderId(e.target.value)}
                >
                  {senders.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name} ({s.email})
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="email-preview__send-to-header">
              <span className="email-preview__sender-label">To</span>
              <button type="button" className="btn btn--ghost email-preview__choose-contacts-btn" onClick={() => setShowContactPicker(true)}>
                👤 Choose Contacts
              </button>
            </div>
            <textarea
              className="filter-bar__input email-preview__send-textarea"
              placeholder="Paste up to 50 email addresses, separated by commas or new lines — or use Choose Contacts above"
              value={sendToText}
              onChange={(e) => setSendToText(e.target.value)}
            />
            <div className="email-preview__send-textarea-footer">
              <span className={`email-preview__send-count ${overCap ? "email-preview__send-count--over" : ""}`}>
                {recipients.length === 0
                  ? "No recipients yet"
                  : overCap
                    ? `${recipients.length} addresses — remove ${recipients.length - MAX_RECIPIENTS} to stay under the ${MAX_RECIPIENTS}-recipient limit`
                    : `${recipients.length} recipient${recipients.length === 1 ? "" : "s"}`}
              </span>
              <button className="btn btn--cta" type="submit" disabled={sending || recipients.length === 0 || overCap}>
                {sending ? "Sending…" : "Send"}
              </button>
            </div>
          </form>
          {creativeId && (
            <div className="email-preview__send-history">
              {sendHistory.length === 0 ? (
                <p className="insights-empty">Not sent yet.</p>
              ) : (
                <>
                  <p className="email-preview__send-history-label">Sent to:</p>
                  <ul className="email-preview__send-history-list">
                    {sendHistory.map((record, i) => (
                      <li key={i}>
                        <span>{record.to_email}</span>
                        <span className="email-preview__send-history-date">
                          {new Date(record.sent_at).toLocaleString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      )}
      {sendResult && (
        <div className={`state-message ${sendResult.ok ? "" : "state-message--error"}`}>
          {sendResult.message}
          {sendResult.failed?.length > 0 && (
            <ul className="email-preview__send-failures">
              {sendResult.failed.map((f) => (
                <li key={f.to}>
                  {f.to}: {f.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {showContactPicker && (
        <LeadContactPicker
          initialSelectedEmails={recipients}
          onSelect={handleContactsSelected}
          onCancel={() => setShowContactPicker(false)}
        />
      )}

      {confirmingSend && (
        <ConfirmDialog
          title="Send this email?"
          message={`This sends a real email to ${recipients.length} recipient${recipients.length === 1 ? "" : "s"} from ${senders.find((s) => s.id === selectedSenderId)?.display_name || "your configured Gmail account"}. This can't be undone.`}
          confirmLabel="Send"
          danger
          onConfirm={performSend}
          onCancel={() => setConfirmingSend(false)}
        />
      )}

      {tab === "preview" ? (
        <iframe
          ref={iframeRef}
          className="email-preview__iframe"
          title="email-preview"
          // No "allow-scripts", so generated HTML still can't execute code.
          // "allow-same-origin" alone is needed so this stays same-origin
          // (http://localhost:5174) instead of an opaque origin -- an opaque
          // origin gets classified by Chrome's Private Network Access checks
          // as a "public" address space, which blocks subresource requests to
          // locally-hosted image-template assets on 127.0.0.1 without ever
          // surfacing a visible network error, only a broken <img>.
          sandbox="allow-same-origin"
          srcDoc={editMode ? editModeSrcDoc : buildPreviewDoc(code, assetsById)}
          onLoad={handleIframeLoad}
        />
      ) : (
        <textarea
          className="email-preview__code"
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            onHtmlChange?.(e.target.value);
          }}
          spellCheck={false}
        />
      )}
      {tab === "code" && (
        <p className="email-preview__code-hint">
          {onHtmlChange
            ? "Editing here updates the Preview tab live, and will be saved when you save/update this template."
            : "Editing here updates the Preview tab live — it isn't saved back to the content library."}
        </p>
      )}
      {tab === "preview" && editMode && (
        <p className="email-preview__code-hint">
          Click any text to edit it, select text to format it (bold/italic/underline/size), or drag the{" "}
          <strong>⠿ + Text</strong> tool (bottom-right of the preview) onto the email to add a block. Hover a block
          and drag its ⠿ handle to reorder it, or hit × to delete it.{" "}
          {onHtmlChange
            ? "Changes here will be saved when you save/update this template."
            : "Changes here update the Preview live — they aren't saved back to the content library."}
        </p>
      )}
    </div>
  );
}
