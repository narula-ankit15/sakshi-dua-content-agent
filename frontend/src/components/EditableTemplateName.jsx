import { useState } from "react";
import { renameContent } from "../api";

export default function EditableTemplateName({ entry, onRenamed, textClassName }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(entry.template_name);
  const [saving, setSaving] = useState(false);

  function startEdit(e) {
    e.stopPropagation();
    setValue(entry.template_name);
    setEditing(true);
  }

  async function commit() {
    const trimmed = value.trim();
    if (!trimmed || trimmed === entry.template_name) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await renameContent(entry.creative_id, trimmed);
      onRenamed(updated);
    } catch {
      // Keep it simple -- just drop back to the last saved name on failure.
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }

  if (editing) {
    return (
      <input
        autoFocus
        className="editable-template-name__input"
        value={value}
        disabled={saving}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setEditing(false);
        }}
      />
    );
  }

  return (
    <span className="editable-template-name">
      <span className={textClassName} title={entry.template_name}>
        {entry.template_name}
      </span>
      <button
        type="button"
        className="editable-template-name__edit"
        onClick={startEdit}
        aria-label="Edit template name"
        title="Edit template name"
      >
        ✏️
      </button>
    </span>
  );
}
