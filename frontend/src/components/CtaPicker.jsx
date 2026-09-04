import { useState } from "react";

const PRESET_CTAS = [
  "Reserve your seat",
  "Call now",
  "Get a callback",
  "Download the brochure",
  "Visit website",
  "Claim early-bird pricing",
];

// Reports the resolved list of up to 2 CTA strings (preset labels and/or
// the custom "Other" text) to the parent on every change -- the parent
// doesn't need to know about presets vs custom, just the final picks.
//
// initialCtas seeds the chip selection once at mount (e.g. reopening a
// saved draft for editing) -- this component is otherwise uncontrolled, so
// there's no other way for a parent to hand it a starting selection.
export default function CtaPicker({ onChange, initialCtas = [] }) {
  const [selectedPresets, setSelectedPresets] = useState(() => initialCtas.filter((c) => PRESET_CTAS.includes(c)));
  const [customActive, setCustomActive] = useState(() => initialCtas.some((c) => !PRESET_CTAS.includes(c)));
  const [customText, setCustomText] = useState(() => initialCtas.find((c) => !PRESET_CTAS.includes(c)) || "");

  const totalSelected = selectedPresets.length + (customActive ? 1 : 0);
  const atLimit = totalSelected >= 2;

  function emit(presets, active, text) {
    const result = [...presets];
    if (active && text.trim()) result.push(text.trim());
    onChange(result);
  }

  function togglePreset(cta) {
    const next = selectedPresets.includes(cta)
      ? selectedPresets.filter((c) => c !== cta)
      : atLimit
        ? selectedPresets
        : [...selectedPresets, cta];
    setSelectedPresets(next);
    emit(next, customActive, customText);
  }

  function toggleCustom() {
    if (!customActive && atLimit) return;
    const next = !customActive;
    setCustomActive(next);
    emit(selectedPresets, next, customText);
  }

  function handleCustomTextChange(text) {
    setCustomText(text);
    emit(selectedPresets, customActive, text);
  }

  return (
    <div className="cta-picker">
      <div className="cta-picker__chips">
        {PRESET_CTAS.map((cta) => {
          const selected = selectedPresets.includes(cta);
          return (
            <button
              key={cta}
              type="button"
              className={`cta-chip ${selected ? "cta-chip--selected" : ""}`}
              onClick={() => togglePreset(cta)}
              disabled={!selected && atLimit}
            >
              {selected && <span className="cta-chip__tick">✓</span>}
              {cta}
            </button>
          );
        })}
        <button
          type="button"
          className={`cta-chip cta-chip--other ${customActive ? "cta-chip--selected" : ""}`}
          onClick={toggleCustom}
          disabled={!customActive && atLimit}
        >
          {customActive && <span className="cta-chip__tick">✓</span>}
          Other
        </button>
      </div>

      {customActive && (
        <input
          className="filter-bar__input cta-picker__custom-input"
          placeholder="Type your own CTA"
          value={customText}
          onChange={(e) => handleCustomTextChange(e.target.value)}
        />
      )}

      <p className="cta-picker__hint">
        Select up to 2 -- the first is the primary CTA
        {totalSelected === 2 ? ", the second is A/B tested on the second message variant." : "."}
      </p>
    </div>
  );
}
