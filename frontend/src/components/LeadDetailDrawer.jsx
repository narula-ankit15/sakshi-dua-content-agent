import { useEffect, useState } from "react";
import LeadFormFields from "./LeadFormFields";

function fieldToForm(lead) {
  return {
    name: lead.name,
    phone: lead.phone,
    email: lead.email,
    organization: lead.organization,
    remarks: lead.remarks,
  };
}

function initials(name) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
}

const FIELDS = [
  { key: "phone", label: "Phone", icon: "📞" },
  { key: "email", label: "Email", icon: "✉️" },
  { key: "organization", label: "Organization", icon: "🏢" },
  { key: "remarks", label: "Remarks", icon: "📝" },
];

export default function LeadDetailDrawer({ lead, onClose, onSave, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => fieldToForm(lead));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    // A different lead was opened -- always start back in view mode on its own data.
    setEditing(false);
    setForm(fieldToForm(lead));
    setError(null);
  }, [lead.id]);

  if (!lead) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(lead.id, {
        name: form.name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        organization: form.organization.trim(),
        remarks: form.remarks.trim(),
      });
      setEditing(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel lead-detail-panel" onClick={(e) => e.stopPropagation()}>
        <div className="lead-detail-panel__banner">
          <div className="lead-detail-panel__banner-top">
            <div className="lead-detail-panel__identity">
              <div className="lead-detail-panel__avatar">{initials(lead.name)}</div>
              <div>
                <div className="lead-detail-panel__name">{editing ? "Edit Lead" : lead.name}</div>
                <div className="lead-detail-panel__added">
                  Added{" "}
                  {new Date(lead.created_at).toLocaleDateString(undefined, {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </div>
              </div>
            </div>
            <div className="lead-detail-panel__actions">
              {!editing && (
                <>
                  <button
                    type="button"
                    className="lead-detail-panel__icon-btn"
                    onClick={() => setEditing(true)}
                    aria-label="Edit lead"
                    title="Edit"
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    className="lead-detail-panel__icon-btn lead-detail-panel__icon-btn--danger"
                    onClick={() => onDelete(lead)}
                    aria-label="Delete lead"
                    title="Delete"
                  >
                    🗑
                  </button>
                </>
              )}
              <button className="lead-detail-panel__icon-btn" onClick={onClose} aria-label="Close" title="Close">
                &times;
              </button>
            </div>
          </div>
        </div>

        <div className="detail-panel__body lead-detail-panel__body">
          {editing ? (
            <form className="leads-page__add-form" onSubmit={handleSubmit}>
              <LeadFormFields form={form} onChange={setForm} autoFocusName />
              {error && <div className="state-message state-message--error">{error}</div>}
              <div className="lead-detail-panel__edit-actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => {
                    setEditing(false);
                    setForm(fieldToForm(lead));
                    setError(null);
                  }}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn--cta" disabled={saving}>
                  {saving ? "Saving…" : "Save Changes"}
                </button>
              </div>
            </form>
          ) : (
            <div className="lead-detail-panel__fields">
              {FIELDS.map(({ key, label, icon }) => (
                <div className="lead-detail-panel__field" key={key}>
                  <span className="lead-detail-panel__field-icon">{icon}</span>
                  <div className="lead-detail-panel__field-text">
                    <div className="lead-detail-panel__field-label">{label}</div>
                    <div
                      className={`lead-detail-panel__field-value ${
                        !lead[key] ? "lead-detail-panel__field-value--empty" : ""
                      } ${key === "remarks" ? "lead-detail-panel__remarks" : ""}`}
                    >
                      {lead[key] || "Not provided"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
