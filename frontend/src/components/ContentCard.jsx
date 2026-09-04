import { useState } from "react";
import ChannelIcon from "./ChannelIcon";
import StatusPill from "./StatusPill";
import EditableTemplateName from "./EditableTemplateName";
import ConfirmDialog from "./ConfirmDialog";
import { contentTagLabel, previewBody, previewTitle } from "../contentPreview";

export default function ContentCard({ entry, topicName, onSelect, onDelete, onRename, onEdit, onDuplicate }) {
  // 'delete' | 'duplicate' | null -- both are one-click-and-it's-done
  // actions (delete destroys, duplicate silently adds a new library entry),
  // so both go through the same confirm-overlay gate before firing.
  const [confirming, setConfirming] = useState(null);

  function handleEdit(e) {
    e.stopPropagation();
    onEdit(entry);
  }

  function confirmAndClose(action) {
    setConfirming(null);
    action(entry);
  }

  const tagLabel = contentTagLabel(entry);

  return (
    <div className={`content-card content-card--${entry.channel}`}>
      <div className="content-card__top">
        <ChannelIcon channel={entry.channel} />
        <div className="content-card__id">
          <EditableTemplateName entry={entry} onRenamed={onRename} textClassName="content-card__variant" />
          <span className="content-card__creative-id">
            {entry.template_id}
            {tagLabel && <span className="content-card__tag"> &middot; {tagLabel}</span>}
          </span>
        </div>
        {entry.status !== "approved" && <StatusPill status={entry.status} />}
        <button
          type="button"
          className="content-card__icon-btn content-card__icon-btn--danger"
          onClick={(e) => {
            e.stopPropagation();
            setConfirming("delete");
          }}
          aria-label="Delete this content"
          title="Delete"
        >
          🗑
        </button>
      </div>

      {topicName && <span className="content-card__topic">{topicName}</span>}
      <h3 className="content-card__title">{previewTitle(entry)}</h3>
      <p className="content-card__body">{previewBody(entry)}</p>

      <div className="content-card__footer">
        <span className="content-card__footer-left">
          <span className="content-card__date">
            {new Date(entry.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
          </span>
          {entry.channel === "email" && entry.sent_count > 0 && (
            <span className="content-card__sent-count" title={`Sent ${entry.sent_count} time${entry.sent_count === 1 ? "" : "s"}`}>
              ✉ {entry.sent_count} sent
            </span>
          )}
        </span>
        <div className="content-card__actions">
          {entry.status === "draft" && (
            <button type="button" className="content-card__icon-btn" onClick={handleEdit} aria-label="Edit this draft" title="Edit">
              ✎
            </button>
          )}
          <button
            type="button"
            className="content-card__icon-btn"
            onClick={(e) => {
              e.stopPropagation();
              setConfirming("duplicate");
            }}
            aria-label="Duplicate as a new draft"
            title="Duplicate"
          >
            ⧉
          </button>
          <button
            type="button"
            className="content-card__icon-btn"
            onClick={() => onSelect(entry)}
            aria-label="View"
            title="View"
          >
            👁
          </button>
        </div>
      </div>

      {confirming === "delete" && (
        <ConfirmDialog
          title="Delete this content?"
          message={`"${entry.template_name}" will be permanently deleted. This can't be undone.`}
          confirmLabel="Delete"
          danger
          onConfirm={() => confirmAndClose(onDelete)}
          onCancel={() => setConfirming(null)}
        />
      )}
      {confirming === "duplicate" && (
        <ConfirmDialog
          title="Duplicate this template?"
          message={`A new draft copy of "${entry.template_name}" will be added to the library.`}
          confirmLabel="Duplicate"
          onConfirm={() => confirmAndClose(onDuplicate)}
          onCancel={() => setConfirming(null)}
        />
      )}
    </div>
  );
}
