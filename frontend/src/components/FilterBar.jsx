const CHANNEL_TABS = [
  { value: "all", label: "All" },
  { value: "email", label: "Email" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "brochure", label: "Brochure" },
];

// Cycled by index so each topic chip gets a stable, distinct pastel color
// regardless of how many topics exist.
const CHIP_PALETTE = [
  { bg: "#EFF6FF", fg: "#2563EB" }, // blue
  { bg: "#FAF5FF", fg: "#9333EA" }, // purple
  { bg: "#FFFBEB", fg: "#D97706" }, // amber
  { bg: "#FDF2F8", fg: "#DB2777" }, // pink
  { bg: "#ECFDF5", fg: "#059669" }, // green
  { bg: "#EEF2FF", fg: "#4F46E5" }, // indigo
  { bg: "#FFF7ED", fg: "#EA580C" }, // orange
  { bg: "#F0FDFA", fg: "#0D9488" }, // teal
  { bg: "#FEF2F2", fg: "#DC2626" }, // red
  { bg: "#F0F9FF", fg: "#0284C7" }, // sky
];

export default function FilterBar({ topics, selectedTopicIds, onToggleTopic, onClearTopics, channel, onChannelChange }) {
  return (
    <div className="filter-bar">
      <div className="filter-bar__row filter-bar__row--topics">
        <div className="filter-bar__topic-chips">
          {topics.map((t, i) => {
            const selected = selectedTopicIds.includes(t.topic_id);
            const color = CHIP_PALETTE[i % CHIP_PALETTE.length];
            return (
              <button
                key={t.topic_id}
                type="button"
                className={`topic-chip ${selected ? "topic-chip--selected" : ""}`}
                style={{ background: color.bg, color: color.fg, borderColor: selected ? color.fg : "transparent" }}
                onClick={() => onToggleTopic(t.topic_id)}
              >
                {t.topic_name}
              </button>
            );
          })}
        </div>
        {selectedTopicIds.length > 0 && (
          <button type="button" className="filter-bar__clear-topics" onClick={onClearTopics}>
            Clear all
          </button>
        )}
      </div>

      <div className="filter-bar__row">
        <div className="filter-bar__tabs">
          {CHANNEL_TABS.map((tab) => (
            <button
              key={tab.value}
              className={`channel-tab ${channel === tab.value ? "channel-tab--active" : ""}`}
              onClick={() => onChannelChange(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
