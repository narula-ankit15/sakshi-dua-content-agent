import { useState } from "react";

const SUGGESTIONS = [
  "Drive signups for the next cohort, seats filling fast",
  "Early-bird pricing ends this Friday, reserve your seat",
  "New public workshop date just announced",
  "In-house corporate booking: customise this workshop for your team",
  "Last few seats left for this weekend's session",
  "Alumni referral: bring a colleague, both get a discount",
  "Post-workshop follow-up: resources and next steps",
  "Now offering a virtual/remote version of this workshop",
];

function highlightMatch(text, query) {
  if (!query.trim()) return text;
  const index = text.toLowerCase().indexOf(query.trim().toLowerCase());
  if (index === -1) return text;
  return (
    <>
      {text.slice(0, index)}
      <strong>{text.slice(index, index + query.trim().length)}</strong>
      {text.slice(index + query.trim().length)}
    </>
  );
}

export default function KeyMessageField({ value, onChange }) {
  const [open, setOpen] = useState(false);

  const suggestions = value.trim()
    ? SUGGESTIONS.filter((s) => s.toLowerCase().includes(value.trim().toLowerCase()))
    : SUGGESTIONS;

  function pick(suggestion) {
    onChange(suggestion);
    setOpen(false);
  }

  return (
    <div className="key-message-field">
      <textarea
        className="filter-bar__input campaign-form__textarea"
        placeholder="Eg: Drive signups for the next cohort, seats filling fast"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
      />
      {open && suggestions.length > 0 && (
        <div className="key-message-field__suggestions">
          {suggestions.map((s, i) => (
            <button
              key={i}
              type="button"
              className="key-message-field__suggestion"
              // onMouseDown (not onClick) fires before the textarea's onBlur,
              // so the pick registers before the dropdown closes.
              onMouseDown={(e) => {
                e.preventDefault();
                pick(s);
              }}
            >
              {highlightMatch(s, value)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
