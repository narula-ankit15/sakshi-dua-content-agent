// Generic double-opt-in confirmation overlay -- reused wherever an action
// is destructive (delete) or creates something new the user didn't
// explicitly type in (duplicate), so a stray click can't silently fire it.
export default function ConfirmDialog({ title, message, confirmLabel = "Confirm", cancelLabel = "Cancel", danger = false, onConfirm, onCancel }) {
  return (
    <div className="confirm-overlay" onClick={onCancel}>
      <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="confirm-modal__title">{title}</h3>
        {message && <p className="confirm-modal__message">{message}</p>}
        <div className="confirm-modal__actions">
          <button className="btn btn--ghost" onClick={onCancel} type="button">
            {cancelLabel}
          </button>
          <button
            className={`btn ${danger ? "btn--danger" : "btn--cta"}`}
            onClick={onConfirm}
            type="button"
            autoFocus
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
