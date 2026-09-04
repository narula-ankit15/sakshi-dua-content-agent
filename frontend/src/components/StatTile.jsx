export default function StatTile({ label, value, accentColor }) {
  return (
    <div className="stat-tile">
      <div className="stat-tile__value" style={{ color: accentColor }}>
        {value}
      </div>
      <div className="stat-tile__label">{label}</div>
    </div>
  );
}
