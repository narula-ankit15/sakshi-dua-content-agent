export default function LeadFormFields({ form, onChange, autoFocusName = false }) {
  return (
    <>
      <div className="leads-page__add-form-row">
        <div className="campaign-form__field">
          <label className="filter-bar__label">
            Name<span className="required">*</span>
          </label>
          <input
            className="filter-bar__input"
            value={form.name}
            onChange={(e) => onChange({ ...form, name: e.target.value })}
            autoFocus={autoFocusName}
          />
        </div>
        <div className="campaign-form__field">
          <label className="filter-bar__label">Phone</label>
          <input
            className="filter-bar__input"
            value={form.phone}
            onChange={(e) => onChange({ ...form, phone: e.target.value })}
          />
        </div>
      </div>
      <div className="leads-page__add-form-row">
        <div className="campaign-form__field">
          <label className="filter-bar__label">Email</label>
          <input
            className="filter-bar__input"
            type="email"
            value={form.email}
            onChange={(e) => onChange({ ...form, email: e.target.value })}
          />
        </div>
        <div className="campaign-form__field">
          <label className="filter-bar__label">Organization</label>
          <input
            className="filter-bar__input"
            value={form.organization}
            onChange={(e) => onChange({ ...form, organization: e.target.value })}
          />
        </div>
      </div>
      <div className="campaign-form__field">
        <label className="filter-bar__label">Remarks</label>
        <textarea
          className="filter-bar__input campaign-form__textarea leads-page__remarks-textarea"
          rows={3}
          value={form.remarks}
          onChange={(e) => onChange({ ...form, remarks: e.target.value })}
        />
      </div>
    </>
  );
}
