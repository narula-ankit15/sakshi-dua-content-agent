import InsightsBarList from "./InsightsBarList";

const AMBER = "#d97706";

// Static, hand-picked numbers -- never computed from real content or
// disguised as derived data. This app has no send/open/click tracking, so
// this section exists only to show what a real performance view could look
// like once one is wired up, and is labeled as such everywhere it appears.
const SUBJECT_LENGTH_BUCKETS = [
  { label: "Under 30 characters", count: 24 },
  { label: "30–50 characters", count: 31 },
  { label: "50–70 characters", count: 19 },
  { label: "Over 70 characters", count: 11 },
];

const MESSAGE_STYLE_BUCKETS = [
  { label: "Line-broken + bold", count: 28 },
  { label: "Single paragraph", count: 14 },
];

export default function IllustrativeBenchmarks() {
  return (
    <div className="illustrative-panel">
      <div className="illustrative-panel__badge">SAMPLE DATA — illustrative only, not from real send/open data</div>
      <p className="illustrative-panel__note">
        This app doesn't track opens, clicks, or replies today — the bars below are a mocked-up example of what
        performance benchmarks could look like once it's connected to a real sending/analytics platform. They
        are not derived from your content.
      </p>
      <div className="insights-panel__row">
        <h5 className="insights-panel__subhead">Example: open rate by subject line length</h5>
        <InsightsBarList items={SUBJECT_LENGTH_BUCKETS} color={AMBER} />
      </div>
      <div className="insights-panel__row">
        <h5 className="insights-panel__subhead">Example: reply rate by WhatsApp message style</h5>
        <InsightsBarList items={MESSAGE_STYLE_BUCKETS} color={AMBER} />
      </div>
    </div>
  );
}
