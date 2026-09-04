import { useState } from "react";

const NODE_W = 210;
const NODE_H = 72;

// Coordinates laid out by hand for a fixed 640x680 viewBox: one input node,
// one orchestrator node, a parallel fan-out pair, then a straight chain
// back down to storage -- mirrors the actual shape of
// app/agents/orchestrator.py's LangGraph StateGraph.
const NODES = [
  {
    id: "gate",
    x: 215,
    y: 16,
    label: "Topic Gate",
    sub: ["Pick one workshop", "topic to unlock the app"],
    color: "#1e1b4b",
    description:
      "Every screen is scoped to one topic_id, picked before anything else runs. There's no default topic and no way to skip this — every downstream agent (context, assets, insights) reads/writes against exactly that one topic's data.",
  },
  {
    id: "brief",
    x: 215,
    y: 108,
    label: "Your Campaign Brief",
    sub: ["Key message, tone,", "CTA, channel settings"],
    color: "#4f46e5",
    description:
      "You fill in a key message, audience tone, CTA, and channel-specific settings (email length/imagery, WhatsApp CTA/image requirements — Brochure needs none, its template is fixed) in the New Content form. This is the only input a human provides — everything below is assembled automatically from it.",
  },
  {
    id: "orchestrator",
    x: 215,
    y: 200,
    label: "Orchestrator",
    sub: ["LangGraph StateGraph"],
    color: "#1e1b4b",
    description:
      "A LangGraph state machine coordinates every agent on this page. It fans out to the Topic Context and Asset agents in parallel, waits for both, then routes into whichever channel agent(s) your brief asked for (Email / WhatsApp / Brochure) — and finally the compliance and save steps.",
  },
  {
    id: "context",
    x: 30,
    y: 312,
    label: "Topic Context Agent",
    sub: ["Reads the topic's", "modules/methodology/outcomes"],
    color: "#2563eb",
    description:
      "Reads the topic's topic.json directly — modules, methodology, outcomes, positioning tags. Unlike the real-estate version this replaced, there's no retrieval/RAG step: a workshop topic's structured fields already are the complete context a content agent needs.",
  },
  {
    id: "assets",
    x: 400,
    y: 312,
    label: "Asset Agent",
    sub: ["Photo bank, tag-matched", "or hand-picked"],
    color: "#2563eb",
    description:
      "Searches the topic's photo bank (past workshop runs) for images whose tags best match the key message. If you manually picked images (or built one in the image editor), that explicit choice always overrides the automatic tag search.",
  },
  {
    id: "content",
    x: 215,
    y: 424,
    label: "Content Agent",
    sub: ["Email, WhatsApp, or", "Brochure — calls Gemini"],
    color: "#7c3aed",
    description:
      "Combines the campaign brief, topic content, and candidate photos into a prompt and calls Gemini. Email returns subject-line variants + HTML; WhatsApp returns message variants + CTA + image choice. Brochure only generates Hero/Hook/Closing copy — Modules/Methodology/Outcomes are copied verbatim from the topic — then renders the fixed one-page template to PDF + PNG via headless Chromium (Playwright).",
  },
  {
    id: "compliance",
    x: 215,
    y: 536,
    label: "Compliance Agent",
    sub: ["Checked against", "the real topic content"],
    color: "#d97706",
    description:
      "Checks the draft against the same Topic the content agent was given — flags unverifiable outcome claims not backed by the topic's own outcomes, broken HTML (email), over-length messages (WhatsApp), and — for Brochure — missing trainer/contact branding or content that overflows the fixed one-page layout.",
  },
  {
    id: "library",
    x: 215,
    y: 648,
    label: "Content Library",
    sub: ["Saved to SQLite —", "powers this page"],
    color: "#16a34a",
    description:
      "Once approved, the draft is saved to a SQLite content_library table with a short creative ID (a Brochure's PDF/PNG are written to disk at this point too). It's now browsable in the library — and every composition metric in this homepage's Insights section is computed directly from these saved rows.",
  },
];

const EDGES = [
  ["gate", "brief"],
  ["brief", "orchestrator"],
  ["orchestrator", "context"],
  ["orchestrator", "assets"],
  ["context", "content"],
  ["assets", "content"],
  ["content", "compliance"],
  ["compliance", "library"],
];

export default function ArchitectureModal({ onClose }) {
  const [selectedId, setSelectedId] = useState(null);
  const selected = NODES.find((n) => n.id === selectedId) || null;

  return (
    <div className="channel-picker-overlay" onClick={onClose}>
      <div className="architecture-modal" onClick={(e) => e.stopPropagation()}>
        <div className="channel-picker-modal__header">
          <h3>How this content system works</h3>
          <button className="detail-panel__close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>
        <p className="channel-picker-modal__hint">
          A multi-agent pipeline turns your brief into on-brand, fact-checked content. Click any step below to
          see what it actually does.
        </p>

        <svg className="architecture-diagram" viewBox="0 0 640 736" role="img" aria-label="Content generation architecture diagram">
          <defs>
            <marker id="arch-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#9ca3af" />
            </marker>
          </defs>
          {EDGES.map(([fromId, toId]) => {
            const from = NODES.find((n) => n.id === fromId);
            const to = NODES.find((n) => n.id === toId);
            const x1 = from.x + NODE_W / 2;
            const y1 = from.y + NODE_H;
            const x2 = to.x + NODE_W / 2;
            const y2 = to.y;
            return (
              <line
                key={`${fromId}-${toId}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="#9ca3af"
                strokeWidth="2"
                markerEnd="url(#arch-arrow)"
              />
            );
          })}
          {NODES.map((n) => {
            const active = selectedId === n.id;
            const cx = n.x + NODE_W / 2;
            return (
              <g
                key={n.id}
                className="arch-node"
                onClick={() => setSelectedId(n.id)}
                tabIndex={0}
                role="button"
                aria-pressed={active}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setSelectedId(n.id)}
              >
                <rect
                  x={n.x}
                  y={n.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={12}
                  fill={active ? n.color : "#ffffff"}
                  stroke={n.color}
                  strokeWidth={active ? 0 : 1.75}
                />
                <text x={cx} y={n.y + 28} textAnchor="middle" className="arch-node__label" fill={active ? "#ffffff" : "#1e1b4b"}>
                  {n.label}
                </text>
                {n.sub.map((line, i) => (
                  <text
                    key={i}
                    x={cx}
                    y={n.y + 46 + i * 13}
                    textAnchor="middle"
                    className="arch-node__sub"
                    fill={active ? "#ffffff" : "#6b7280"}
                  >
                    {line}
                  </text>
                ))}
              </g>
            );
          })}
        </svg>

        <div className="architecture-description">
          {selected ? (
            <>
              <h4 style={{ color: selected.color }}>{selected.label}</h4>
              <p>{selected.description}</p>
            </>
          ) : (
            <p className="insights-empty">Click any box above to see what that step does.</p>
          )}
        </div>
      </div>
    </div>
  );
}
