// Ranked horizontal bar list -- one series (one color) per list, so no
// legend is needed (the section heading above already names what's plotted).
export default function InsightsBarList({ items, color, emptyLabel = "Not enough saved content yet." }) {
  if (!items || items.length === 0) {
    return <p className="insights-empty">{emptyLabel}</p>;
  }
  const max = Math.max(...items.map((i) => i.count));
  return (
    <ul className="insights-bar-list">
      {items.map((item) => (
        <li key={item.label} className="insights-bar-row">
          <span className="insights-bar-row__label" title={item.label}>
            {item.label}
          </span>
          <span className="insights-bar-row__track">
            <span
              className="insights-bar-row__fill"
              style={{ width: `${Math.max(6, (item.count / max) * 100)}%`, background: color }}
            />
          </span>
          <span className="insights-bar-row__value">{item.count}</span>
        </li>
      ))}
    </ul>
  );
}
