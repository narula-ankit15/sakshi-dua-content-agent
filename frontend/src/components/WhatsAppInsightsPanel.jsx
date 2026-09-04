import StatTile from "./StatTile";
import InsightsBarList from "./InsightsBarList";
import ContentTagBar from "./ContentTagBar";

const GREEN = "#16a34a";

export default function WhatsAppInsightsPanel({ data }) {
  if (!data || data.count === 0) {
    return (
      <div className="insights-panel insights-panel--whatsapp">
        <h4 className="insights-panel__title">💬 WhatsApp messages</h4>
        <p className="insights-empty">
          No saved WhatsApp content yet for this topic — generate and save a message to see insights here.
        </p>
      </div>
    );
  }

  const topCtas = data.top_cta_phrases.map((c) => ({ label: c.cta, count: c.count }));
  const topTags = data.top_asset_tags.map((t) => ({ label: t.tag, count: t.count }));

  return (
    <div className="insights-panel insights-panel--whatsapp">
      <h4 className="insights-panel__title">💬 WhatsApp messages</h4>
      <div className="insights-panel__stats">
        <StatTile label="Saved messages" value={data.count} accentColor={GREEN} />
        <StatTile label="Avg. message length" value={`${data.avg_message_words} words`} accentColor={GREEN} />
        <StatTile label="Include an image" value={`${Math.round(data.image_usage_rate * 100)}%`} accentColor={GREEN} />
      </div>
      <div className="insights-panel__row">
        <h5 className="insights-panel__subhead">Most-used CTA phrases</h5>
        <InsightsBarList items={topCtas} color={GREEN} emptyLabel="No CTAs used yet." />
      </div>
      <div className="insights-panel__row">
        <h5 className="insights-panel__subhead">Most-used image themes</h5>
        <InsightsBarList items={topTags} color={GREEN} emptyLabel="No images used yet." />
      </div>
      <div className="insights-panel__row">
        <h5 className="insights-panel__subhead">Service vs. promotional mix</h5>
        <ContentTagBar distribution={data.content_tag_distribution} />
      </div>
    </div>
  );
}
