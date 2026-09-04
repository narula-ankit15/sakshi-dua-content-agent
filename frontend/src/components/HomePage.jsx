import { useEffect, useState } from "react";
import { getInsights } from "../api";
import EmailInsightsPanel from "./EmailInsightsPanel";
import WhatsAppInsightsPanel from "./WhatsAppInsightsPanel";
import IllustrativeBenchmarks from "./IllustrativeBenchmarks";
import ArchitectureModal from "./ArchitectureModal";

export default function HomePage({ topicId, topicName, onSwitchTopic, onGoBrowse, onGoCreate }) {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showArchitecture, setShowArchitecture] = useState(false);

  useEffect(() => {
    if (!topicId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getInsights(topicId)
      .then((data) => {
        if (!cancelled) setInsights(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [topicId]);

  return (
    <div className="home">
      <section className="home__hero">
        <h2 className="home__hero-title">Workshop Content Studio</h2>
        <p className="home__hero-subtitle">
          Generate on-brand email, WhatsApp, and one-page brochure content for your workshops, backed by a
          multi-agent system that pulls straight from each topic's modules, methodology, and outcomes.
        </p>
        <div className="home__hero-actions">
          <button className="btn btn--cta home__hero-btn" onClick={onGoCreate}>
            + Create New Content
          </button>
          <button className="btn btn--ghost home__hero-btn" onClick={onGoBrowse}>
            Browse Library
          </button>
        </div>
      </section>

      <section className="home__insights">
        <div className="home__insights-header">
          <h3>Content Insights</h3>
          <div className="filter-bar__topic-display">
            <span>{topicName}</span>
            <button type="button" className="filter-bar__switch-topic" onClick={onSwitchTopic}>
              Switch topic
            </button>
          </div>
        </div>
        <p className="home__insights-hint">
          What kind of content you've actually been creating for this topic's library — length, wording,
          imagery, and CTA patterns. This app doesn't track sends or opens, so this is composition, not
          performance (see the illustrative example further down for what performance benchmarks could look
          like).
        </p>

        {loading && <div className="state-message">Loading insights&hellip;</div>}
        {error && <div className="state-message state-message--error">{error}</div>}

        {insights && !loading && !error && (
          <>
            <div className="insights-grid">
              <EmailInsightsPanel data={insights.email} />
              <WhatsAppInsightsPanel data={insights.whatsapp} />
            </div>
            <IllustrativeBenchmarks />
          </>
        )}
      </section>

      <button className="home__architecture-btn" onClick={() => setShowArchitecture(true)}>
        <span className="home__architecture-icon">?</span>
        How this content system works
      </button>

      {showArchitecture && <ArchitectureModal onClose={() => setShowArchitecture(false)} />}
    </div>
  );
}
