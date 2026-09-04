import { useState } from "react";
import LeadFormFields from "./LeadFormFields";

const EMPTY_FORM = { name: "", phone: "", email: "", organization: "", remarks: "" };

export default function LeadFormModal({ title = "Add Lead", submitLabel = "Save Lead", onSave, onCancel }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({
        name: form.name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        organization: form.organization.trim(),
        remarks: form.remarks.trim(),
      });
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <div className="channel-picker-overlay" onClick={onCancel}>
      <form className="channel-picker-modal lead-form-modal" onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}>
        <div className="channel-picker-modal__header">
          <h3>{title}</h3>
        </div>

        <LeadFormFields form={form} onChange={setForm} autoFocusName />

        {error && <div className="state-message state-message--error">{error}</div>}

        <div className="channel-picker-modal__actions">
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="btn btn--cta" disabled={saving}>
            {saving ? "Saving…" : submitLabel}
          </button>
        </div>
      </form>
    </div>
  );
}
