export default function SubjectLinePicker({ subjectLines, selectedIndex, onSelect, onGenerateMore, generating }) {
  return (
    <div className="subject-picker">
      <div className="subject-picker__label">Subject line options</div>
      <div className="subject-picker__chips">
        {subjectLines.map((line, i) => (
          <button
            key={i}
            type="button"
            className={`subject-chip ${i === selectedIndex ? "subject-chip--selected" : ""}`}
            onClick={() => onSelect(i)}
          >
            {i === selectedIndex && <span className="subject-chip__tick">✓</span>}
            {line}
          </button>
        ))}
        {onGenerateMore && (
          <button
            type="button"
            className="subject-chip subject-chip--more"
            onClick={onGenerateMore}
            disabled={generating}
          >
            {generating ? "Generating…" : "+ Generate more options"}
          </button>
        )}
      </div>
    </div>
  );
}
