import { useState } from "react";

const CHANNELS = [
  { value: "email", label: "Email" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "brochure", label: "Brochure" },
];

export default function ChannelPickerModal({ onContinue, onCancel }) {
  const [channel, setChannel] = useState("email");

  return (
    <div className="channel-picker-overlay" onClick={onCancel}>
      <div className="channel-picker-modal" onClick={(e) => e.stopPropagation()}>
        <div className="channel-picker-modal__header">
          <h3>Choose channel</h3>
          <button className="detail-panel__close" onClick={onCancel} aria-label="Close">
            &times;
          </button>
        </div>

        <p className="channel-picker-modal__hint">
          Content is generated for one channel at a time — pick which one you're creating.
        </p>

        <div className="channel-picker-modal__options">
          {CHANNELS.map((opt) => (
            <label key={opt.value} className="channel-picker-modal__option">
              <input
                type="radio"
                name="channel"
                value={opt.value}
                checked={channel === opt.value}
                onChange={() => setChannel(opt.value)}
              />
              {opt.label}
            </label>
          ))}
        </div>

        <div className="channel-picker-modal__actions">
          <button className="btn btn--ghost" onClick={onCancel} type="button">
            Cancel
          </button>
          <button className="btn btn--cta" onClick={() => onContinue(channel)} type="button">
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
