import { useEffect, useState } from "react";
import { createLead, deleteLead, listLeadImportHistory, listLeads, updateLead } from "../api";
import ConfirmDialog from "./ConfirmDialog";
import LeadFormModal from "./LeadFormModal";
import LeadDetailDrawer from "./LeadDetailDrawer";
import LeadImportModal from "./LeadImportModal";
import LeadImportHistory from "./LeadImportHistory";

export default function LeadsPage() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState("");

  const [showAddModal, setShowAddModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [openLead, setOpenLead] = useState(null); // lead being viewed/edited in the side drawer

  const [importBatches, setImportBatches] = useState([]);
  const [importToast, setImportToast] = useState(null);

  const [confirmingDelete, setConfirmingDelete] = useState(null); // the lead object, or null

  function load() {
    setLoading(true);
    setError(null);
    listLeads({ search: search.trim() })
      .then(setLeads)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  function loadImportHistory() {
    listLeadImportHistory().then(setImportBatches).catch(() => setImportBatches([]));
  }

  useEffect(() => {
    // Debounced -- refiltering on every keystroke would otherwise fire a
    // request per character typed.
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    loadImportHistory();
  }, []);

  async function handleAddLead(payload) {
    await createLead(payload);
    setShowAddModal(false);
    load();
  }

  async function handleUpdateLead(leadId, payload) {
    const updated = await updateLead(leadId, payload);
    setLeads((prev) => prev.map((l) => (l.id === leadId ? updated : l)));
    setOpenLead(updated);
  }

  function handleImported(result) {
    setShowImportModal(false);
    setImportToast(
      `Imported ${result.imported} lead${result.imported === 1 ? "" : "s"}.` +
        (result.skipped.length > 0 ? ` ${result.skipped.length} row(s) skipped -- see the history table below.` : "")
    );
    setTimeout(() => setImportToast(null), 5000);
    load();
    loadImportHistory();
  }

  async function handleConfirmDelete() {
    const lead = confirmingDelete;
    setConfirmingDelete(null);
    try {
      await deleteLead(lead.id);
      setLeads((prev) => prev.filter((l) => l.id !== lead.id));
      setOpenLead((prev) => (prev?.id === lead.id ? null : prev));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="leads-page">
      <section className="home__hero">
        <h2 className="home__hero-title">Leads</h2>
        <p className="home__hero-subtitle">
          Everyone who's shown interest — add them one at a time, or import a whole list from a CSV.
        </p>
      </section>

      <div className="leads-page__toolbar">
        <div className="leads-page__filters">
          <input
            className="filter-bar__input leads-page__search-input"
            placeholder="🔍 Search by name, organization, phone, or remarks…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="leads-page__toolbar-actions">
          <button type="button" className="btn btn--ghost" onClick={() => setShowImportModal(true)}>
            ⬆ Upload CSV
          </button>
          <button type="button" className="btn btn--cta" onClick={() => setShowAddModal(true)}>
            + Add Lead
          </button>
        </div>
      </div>

      {importToast && <div className="state-message">{importToast}</div>}

      {showAddModal && <LeadFormModal onSave={handleAddLead} onCancel={() => setShowAddModal(false)} />}

      {showImportModal && (
        <LeadImportModal onImported={handleImported} onCancel={() => setShowImportModal(false)} />
      )}

      {loading && <div className="state-message">Loading leads&hellip;</div>}
      {error && <div className="state-message state-message--error">{error}</div>}
      {!loading && !error && leads.length === 0 && (
        <div className="state-message">
          {search.trim()
            ? "No leads match your search."
            : "No leads found. Add one, or upload a CSV to get started."}
        </div>
      )}

      {!loading && !error && leads.length > 0 && (
        <div className="leads-table-wrap">
          <table className="leads-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th>Email</th>
                <th>Organization</th>
                <th>Remarks</th>
                <th>Added</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id} className="leads-table__row" onClick={() => setOpenLead(lead)}>
                  <td className="leads-table__name">{lead.name}</td>
                  <td>{lead.phone || "—"}</td>
                  <td>{lead.email || "—"}</td>
                  <td>{lead.organization || "—"}</td>
                  <td className="leads-table__remarks">{lead.remarks || "—"}</td>
                  <td className="leads-table__date">
                    {new Date(lead.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="content-card__icon-btn content-card__icon-btn--danger"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmingDelete(lead);
                      }}
                      aria-label={`Delete ${lead.name}`}
                      title="Delete"
                    >
                      🗑
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <LeadImportHistory batches={importBatches} />

      {openLead && (
        <LeadDetailDrawer
          lead={openLead}
          onClose={() => setOpenLead(null)}
          onSave={handleUpdateLead}
          onDelete={setConfirmingDelete}
        />
      )}

      {confirmingDelete && (
        <ConfirmDialog
          title="Delete this lead?"
          message={`"${confirmingDelete.name}" will be permanently deleted. This can't be undone.`}
          confirmLabel="Delete"
          danger
          onConfirm={handleConfirmDelete}
          onCancel={() => setConfirmingDelete(null)}
        />
      )}
    </div>
  );
}
