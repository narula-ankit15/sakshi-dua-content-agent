import { useEffect, useMemo, useState } from "react";
import { listLeads } from "../api";

export default function LeadContactPicker({ initialSelectedEmails = [], onSelect, onCancel }) {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState(() => new Set());

  useEffect(() => {
    setLoading(true);
    setError(null);
    listLeads()
      .then((data) => {
        setLeads(data);
        const initialLower = new Set(initialSelectedEmails.map((e) => e.toLowerCase()));
        setSelectedIds(new Set(data.filter((l) => l.email && initialLower.has(l.email.toLowerCase())).map((l) => l.id)));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleLeads = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return leads;
    return leads.filter((l) =>
      [l.name, l.organization, l.phone, l.email, l.remarks].some((field) => field?.toLowerCase().includes(q))
    );
  }, [leads, search]);

  const selectableVisible = visibleLeads.filter((l) => l.email);
  const allVisibleSelected = selectableVisible.length > 0 && selectableVisible.every((l) => selectedIds.has(l.id));

  function toggle(leadId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(leadId)) next.delete(leadId);
      else next.add(leadId);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        selectableVisible.forEach((l) => next.delete(l.id));
      } else {
        selectableVisible.forEach((l) => next.add(l.id));
      }
      return next;
    });
  }

  function handleSubmit() {
    const emails = leads.filter((l) => selectedIds.has(l.id) && l.email).map((l) => l.email);
    onSelect(emails);
  }

  return (
    <div className="channel-picker-overlay" onClick={onCancel}>
      <div className="channel-picker-modal lead-picker-modal" onClick={(e) => e.stopPropagation()}>
        <div className="channel-picker-modal__header">
          <h3>Choose Contacts</h3>
        </div>
        <p className="channel-picker-modal__hint">
          Pick from your Leads list — selected contacts' emails are added to the To field.
        </p>

        <div className="lead-picker-modal__filters">
          <input
            className="filter-bar__input"
            placeholder="🔍 Search by name, organization, phone, or remarks…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {loading && <div className="state-message">Loading leads&hellip;</div>}
        {error && <div className="state-message state-message--error">{error}</div>}
        {!loading && !error && visibleLeads.length === 0 && (
          <div className="state-message">No leads match this filter.</div>
        )}

        {!loading && !error && visibleLeads.length > 0 && (
          <div className="lead-picker-modal__list">
            <table className="leads-table">
              <thead>
                <tr>
                  <th className="lead-picker-modal__checkbox-col">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleAllVisible}
                      aria-label="Select all"
                    />
                  </th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Organization</th>
                </tr>
              </thead>
              <tbody>
                {visibleLeads.map((lead) => (
                  <tr
                    key={lead.id}
                    className={`leads-table__row ${!lead.email ? "lead-picker-modal__row--disabled" : ""}`}
                    onClick={() => lead.email && toggle(lead.id)}
                  >
                    <td className="lead-picker-modal__checkbox-col">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(lead.id)}
                        disabled={!lead.email}
                        onChange={() => toggle(lead.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td className="leads-table__name">{lead.name}</td>
                    <td>{lead.email || <span className="lead-picker-modal__no-email">No email on file</span>}</td>
                    <td>{lead.organization || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="channel-picker-modal__actions">
          <button type="button" className="btn btn--ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn btn--cta" onClick={handleSubmit} disabled={selectedIds.size === 0}>
            Add {selectedIds.size > 0 ? selectedIds.size : ""} Selected
          </button>
        </div>
      </div>
    </div>
  );
}
