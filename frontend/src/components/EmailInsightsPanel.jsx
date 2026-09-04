import StatTile from "./StatTile";
import InsightsBarList from "./InsightsBarList";
import ContentTagBar from "./ContentTagBar";

const BLUE = "#2563eb";

export default function EmailInsightsPanel({ data }) {
  if (!data || data.count === 0) {
    return (
      <div className="insights-panel insights-panel--email">
        <h4 className="insights-panel__title">📧 Email subject lines</h4>
        <p className="insights-empty">
          No saved email content yet for this topic — generate and save an email to see insights here.
        </p>
      </div>
    );
  }

  const topWords = data.top_words.map((w) => ({ label: w.word, count: w.count }));
  const topTags = data.top_asset_tags.map((t) => ({ label: t.tag, count: t.count }));

  return (
    <div className="insights-panel insights-panel--email">
      <h4 className="insights-panel__title">📧 Email subject lines</h4>
      <div className="insights-panel__stats">
        <StatTile label="Saved emails" value={data.count} accentColor={BLUE} />
        <StatTile label="Avg. subject length" value={`${data.avg_subject_words} words`} accentColor={BLUE} />
        <StatTile label="Use an emoji" value={`${Math.round(data.emoji_usage_rate * 100)}%`} accentColor={BLUE} />
        <StatTile label="Include an image" value={`${Math.round(data.image_usage_rate * 100)}%`} accentColor={BLUE} />
      </div>
      <div className="insights-panel__row">
        <h5 className="insights-panel__subhead">Most common words in subject lines</h5>
        <InsightsBarList items={topWords} color={BLUE} />
      </div>
      <div className="insights-panel__row">
        <h5 className="insights-panel__subhead">Most-used image themes</h5>
        <InsightsBarList items={topTags} color={BLUE} emptyLabel="No images used yet." />
      </div>
      <div className="insights-panel__row">
        <h5 className="insights-panel__subhead">Service vs. promotional mix</h5>
        <ContentTagBar distribution={data.content_tag_distribution} />
      </div>
    </div>
  );
}
