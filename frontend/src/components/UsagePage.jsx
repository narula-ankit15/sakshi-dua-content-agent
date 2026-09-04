import { useEffect, useState } from "react";
import { getUsage, setUsageCap } from "../api";
import InsightsBarList from "./InsightsBarList";
import StatTile from "./StatTile";

const INDIGO = "#4f46e5";

export default function UsagePage() {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [capInput, setCapInput] = useState("");
  const [savingCap, setSavingCap] = useState(false);

  function load() {
    setLoading(true);
    setError(null);
    getUsage()
      .then((data) => {
        setUsage(data);
        setCapInput(data.daily_cap != null ? String(data.daily_cap) : "");
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSaveCap(e) {
    e.preventDefault();
    setSavingCap(true);
    setError(null);
    try {
      const trimmed = capInput.trim();
      const cap = trimmed === "" ? null : Number(trimmed);
      const data = await setUsageCap(cap);
      setUsage(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingCap(false);
    }
  }

  const purposeItems = usage
    ? Object.entries(usage.requests_by_purpose).map(([purpose, count]) => ({
        label: purpose.replace(/_/g, " "),
        count,
      }))
    : [];

  const pctUsed =
    usage && usage.daily_cap ? Math.min(100, Math.round((usage.requests_today / usage.daily_cap) * 100)) : null;

  const imagePct =
    usage && usage.image_generation_daily_limit
      ? Math.min(100, Math.round((usage.images_generated_today / usage.image_generation_daily_limit) * 100))
      : null;

  return (
    <div className="usage-page">
      <section className="home__hero usage-hero">
        <h2 className="home__hero-title">API Usage</h2>
        <p className="home__hero-subtitle">
          Requests this app has actually made to Gemini today. Gemini's API doesn't expose your real account
          quota, so there's no way to pull a true "remaining" number from Google directly — enter your plan's
          daily limit below and this compares your usage against that instead.
        </p>
      </section>

      {loading && <div className="state-message">Loading usage&hellip;</div>}
      {error && <div className="state-message state-message--error">{error}</div>}

      {usage && !loading && (
        <section className="home__insights usage-panel">
          {usage.rate_limited_today && (
            <div className="usage-alert">
              ⚠️ At least one request today was rejected as rate-limited by Gemini — you may have hit a real cap
              on Google's side today.
            </div>
          )}

          <div className="insights-panel__stats usage-stats">
            <StatTile label="Requests today" value={usage.requests_today} accentColor={INDIGO} />
            <StatTile
              label="Remaining vs. your cap"
              value={usage.remaining_today != null ? usage.remaining_today : "—"}
              accentColor={INDIGO}
            />
            <StatTile
              label="Last request"
              value={usage.last_request_at ? new Date(usage.last_request_at).toLocaleTimeString() : "—"}
              accentColor={INDIGO}
            />
          </div>

          {usage.daily_cap != null && (
            <div className="usage-progress">
              <div className="usage-progress__track">
                <div
                  className={`usage-progress__fill ${pctUsed >= 100 ? "usage-progress__fill--full" : ""}`}
                  style={{ width: `${pctUsed}%` }}
                />
              </div>
              <span className="usage-progress__label">
                {usage.requests_today} / {usage.daily_cap} used today
              </span>
            </div>
          )}

          <div className="insights-panel__row usage-breakdown">
            <h5 className="insights-panel__subhead">AI hero image generation</h5>
            <p className="campaign-form__hint">
              A hard-capped, separate limit from the general request cap above — each AI-generated hero image is a
              real cost, regardless of the overall Gemini plan limit.
            </p>
            <div className="usage-progress">
              <div className="usage-progress__track">
                <div
                  className={`usage-progress__fill usage-progress__fill--amber ${imagePct >= 100 ? "usage-progress__fill--full" : ""}`}
                  style={{ width: `${imagePct ?? 0}%` }}
                />
              </div>
              <span className="usage-progress__label">
                {usage.images_generated_today} / {usage.image_generation_daily_limit ?? "—"} AI images generated
                today
                {usage.images_remaining_today === 0 && " — limit reached, try again tomorrow"}
              </span>
            </div>
          </div>

          <form className="usage-cap-form" onSubmit={handleSaveCap}>
            <label className="filter-bar__label" htmlFor="usage-cap-input">
              Your daily request cap (from your Gemini plan)
            </label>
            <div className="usage-cap-form__row">
              <input
                id="usage-cap-input"
                type="number"
                min="0"
                className="filter-bar__input"
                placeholder="e.g. 1500"
                value={capInput}
                onChange={(e) => setCapInput(e.target.value)}
              />
              <button className="btn btn--cta" type="submit" disabled={savingCap}>
                {savingCap ? "Saving…" : "Save cap"}
              </button>
            </div>
          </form>

          <div className="insights-panel__row usage-breakdown">
            <h5 className="insights-panel__subhead">Requests today by purpose</h5>
            <InsightsBarList items={purposeItems} color={INDIGO} emptyLabel="No requests made yet today." />
          </div>

          <button className="btn btn--ghost usage-refresh-btn" type="button" onClick={load}>
            ↻ Refresh
          </button>
        </section>
      )}
    </div>
  );
}
