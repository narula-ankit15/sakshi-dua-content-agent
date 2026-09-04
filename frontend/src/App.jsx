import { useEffect, useState } from "react";
import Header from "./components/Header";
import FilterBar from "./components/FilterBar";
import ContentCard from "./components/ContentCard";
import DetailPanel from "./components/DetailPanel";
import GenerateWorkspace from "./components/GenerateWorkspace";
import ChannelPickerModal from "./components/ChannelPickerModal";
import UsagePage from "./components/UsagePage";
import LeadsPage from "./components/LeadsPage";
import { deleteContent, duplicateContent, getContent, listAssets, listContent, listTopics } from "./api";
import "./App.css";

export default function App() {
  const [topics, setTopics] = useState([]);
  // Empty selection means "no filter" -- Browse Library shows content
  // across every topic until the user actively picks one or more chips.
  const [selectedTopicIds, setSelectedTopicIds] = useState([]);

  const [view, setView] = useState("browse");
  const [channel, setChannel] = useState("all");
  const [entries, setEntries] = useState([]);
  const [assetsById, setAssetsById] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [toast, setToast] = useState(null);
  const [showChannelPicker, setShowChannelPicker] = useState(false);
  const [newContentChannel, setNewContentChannel] = useState(null);
  // Set only when "Edit" was clicked on a saved draft -- GenerateWorkspace
  // reads this to prefill its form instead of starting blank, and to save
  // back over the same creative_id instead of creating a new one.
  const [editingEntry, setEditingEntry] = useState(null);
  // Bumped whenever the browse list needs a refetch that isn't already
  // implied by selectedTopicIds/channel changing -- e.g. returning from
  // "New Content".
  const [refreshToken, setRefreshToken] = useState(0);

  const topicsById = Object.fromEntries(topics.map((t) => [t.topic_id, t.topic_name]));

  useEffect(() => {
    listTopics()
      .then(setTopics)
      .catch(() => setTopics([]));
  }, []);

  function toggleTopicFilter(topicId) {
    setSelectedTopicIds((prev) =>
      prev.includes(topicId) ? prev.filter((id) => id !== topicId) : [...prev, topicId]
    );
  }

  function clearTopicFilters() {
    setSelectedTopicIds([]);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listContent({ topicIds: selectedTopicIds, channel })
      .then((data) => {
        if (!cancelled) setEntries(data);
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
  }, [selectedTopicIds, channel, refreshToken]);

  useEffect(() => {
    // Content can now span multiple topics at once -- resolve assets
    // (needed for WhatsApp image previews) per distinct topic present in
    // the current result set and merge them into one lookup map.
    const topicIds = [...new Set(entries.map((e) => e.topic_id))];
    if (topicIds.length === 0) {
      setAssetsById({});
      return;
    }
    let cancelled = false;
    Promise.all(topicIds.map((id) => listAssets(id).catch(() => [])))
      .then((results) => {
        if (cancelled) return;
        const merged = {};
        for (const assets of results) {
          for (const a of assets) merged[a.asset_id] = a;
        }
        setAssetsById(merged);
      })
      .catch(() => {
        if (!cancelled) setAssetsById({});
      });
    return () => {
      cancelled = true;
    };
  }, [entries]);

  async function handleDelete(entry) {
    try {
      await deleteContent(entry.creative_id);
      setEntries((prev) => prev.filter((e) => e.creative_id !== entry.creative_id));
      setSelected((prev) => (prev?.creative_id === entry.creative_id ? null : prev));
      setToast(`Deleted ${entry.template_name}.`);
    } catch (err) {
      setToast(`Failed to delete: ${err.message}`);
    }
    setTimeout(() => setToast(null), 3000);
  }

  function handleRename(updatedEntry) {
    setEntries((prev) => prev.map((e) => (e.creative_id === updatedEntry.creative_id ? updatedEntry : e)));
    setSelected((prev) => (prev?.creative_id === updatedEntry.creative_id ? updatedEntry : prev));
  }

  async function handleEdit(entry) {
    // The card that was clicked can be a stale copy -- e.g. after saving
    // inside a previous edit session and leaving via "Back to Library"
    // (which doesn't itself refetch the list). Re-fetching here means Edit
    // always opens on what's actually saved, not whatever was last in
    // memory, regardless of how that staleness happened.
    let fresh = entry;
    try {
      fresh = await getContent(entry.creative_id);
    } catch {
      // Fall back to the given entry rather than blocking Edit entirely.
    }
    setEditingEntry(fresh);
    setNewContentChannel(fresh.channel);
    setView("create");
  }

  async function handleSelect(entry) {
    // Same staleness risk as handleEdit -- View should never show
    // content that's out of date with what was last saved.
    let fresh = entry;
    try {
      fresh = await getContent(entry.creative_id);
    } catch {
      // Fall back to the given entry rather than blocking View entirely.
    }
    setSelected(fresh);
  }

  async function handleDuplicate(entry) {
    try {
      const copy = await duplicateContent(entry.creative_id);
      setEntries((prev) => [copy, ...prev]);
      setToast(`Duplicated "${entry.template_name}" as a new draft.`);
    } catch (err) {
      setToast(`Failed to duplicate: ${err.message}`);
    }
    setTimeout(() => setToast(null), 3000);
  }

  return (
    <div className="page">
      <Header />

      <main className="page__content">
        <div className="view-tabs">
          <div className="view-tabs__links">
            <button
              className={`view-tab-link ${view === "browse" ? "view-tab-link--active" : ""}`}
              onClick={() => setView("browse")}
            >
              Browse Library
            </button>
            <button
              className={`view-tab-link ${view === "usage" ? "view-tab-link--active" : ""}`}
              onClick={() => setView("usage")}
            >
              Usage
            </button>
            <button
              className={`view-tab-link ${view === "leads" ? "view-tab-link--active" : ""}`}
              onClick={() => setView("leads")}
            >
              Leads
            </button>
          </div>
          <button
            className="new-content-btn"
            onClick={() => {
              if (view === "create") {
                setEditingEntry(null);
                // Whether or not anything was actually saved this session,
                // the list should reflect it -- cheap, and avoids exactly
                // the staleness handleEdit's own re-fetch otherwise has to
                // work around.
                setRefreshToken((t) => t + 1);
                setView("browse");
              } else {
                setShowChannelPicker(true);
              }
            }}
          >
            {view === "create" ? "← Back to Library" : "+ New Content"}
          </button>
        </div>

        {showChannelPicker && (
          <ChannelPickerModal
            onCancel={() => setShowChannelPicker(false)}
            onContinue={(pickedChannel) => {
              setEditingEntry(null);
              setNewContentChannel(pickedChannel);
              setShowChannelPicker(false);
              setView("create");
            }}
          />
        )}

        {view === "usage" && <UsagePage />}

        {view === "leads" && <LeadsPage />}

        {view === "create" && newContentChannel && (
          <GenerateWorkspace
            channel={newContentChannel}
            editingEntry={editingEntry}
            onChangeChannel={() => setShowChannelPicker(true)}
            onDone={() => {
              setEditingEntry(null);
              setRefreshToken((t) => t + 1);
              setView("browse");
            }}
          />
        )}

        {view === "browse" && (
          <>
            <FilterBar
              topics={topics}
              selectedTopicIds={selectedTopicIds}
              onToggleTopic={toggleTopicFilter}
              onClearTopics={clearTopicFilters}
              channel={channel}
              onChannelChange={setChannel}
            />

            {loading && <div className="state-message">Loading content&hellip;</div>}
            {error && <div className="state-message state-message--error">{error}</div>}
            {!loading && !error && entries.length === 0 && (
              <div className="state-message">No content found. Use "+ New Content" to generate some.</div>
            )}

            {!loading && !error && entries.length > 0 && (
              <div className="content-grid">
                {entries.map((entry) => (
                  <ContentCard
                    key={entry.creative_id}
                    entry={entry}
                    topicName={topicsById[entry.topic_id]}
                    onSelect={handleSelect}
                    onDelete={handleDelete}
                    onRename={handleRename}
                    onEdit={handleEdit}
                    onDuplicate={handleDuplicate}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>

      <DetailPanel
        entry={selected}
        onClose={() => setSelected(null)}
        onRename={handleRename}
        assetsById={assetsById}
        businessName={selected ? topicsById[selected.topic_id] : null}
      />

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
