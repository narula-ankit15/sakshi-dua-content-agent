// Fixed category colors (never cycled/reassigned) so "promotional" always
// reads as purple and "service" always reads as teal, in both channel panels.
const TAG_COLORS = { promotional_communication: "#7c3aed", service: "#0d9488" };
const TAG_LABELS = { promotional_communication: "Promotional", service: "Service" };
const FALLBACK_COLOR = "#9ca3af";

export default function ContentTagBar({ distribution }) {
  const entries = Object.entries(distribution || {});
  const total = entries.reduce((sum, [, n]) => sum + n, 0);

  if (total === 0) {
    return <p className="insights-empty">No tagged content yet.</p>;
  }

  return (
    <div className="tag-distribution">
      <div className="tag-distribution__bar">
        {entries.map(([tag, n]) => (
          <span
            key={tag}
            className="tag-distribution__segment"
            style={{ width: `${(n / total) * 100}%`, background: TAG_COLORS[tag] || FALLBACK_COLOR }}
          />
        ))}
      </div>
      <div className="tag-distribution__legend">
        {entries.map(([tag, n]) => (
          <span key={tag} className="tag-distribution__legend-item">
            <span className="tag-distribution__swatch" style={{ background: TAG_COLORS[tag] || FALLBACK_COLOR }} />
            {TAG_LABELS[tag] || tag} ({n})
          </span>
        ))}
      </div>
    </div>
  );
}
