import { useRef, useState } from "react";
import { importLeadsCsv, leadImportTemplateUrl } from "../api";

export default function LeadImportModal({ onImported, onCancel }) {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  function pickFile(candidate) {
    if (!candidate) return;
    setError(null);
    setFile(candidate);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const result = await importLeadsCsv(file);
      onImported(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="channel-picker-overlay" onClick={onCancel}>
      <div className="channel-picker-modal lead-import-modal" onClick={(e) => e.stopPropagation()}>
        <div className="channel-picker-modal__header">
          <h3>Bulk Upload Leads</h3>
        </div>

        <div
          className={`lead-import-modal__dropzone ${dragging ? "lead-import-modal__dropzone--active" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="image-picker__upload-input"
            onChange={(e) => pickFile(e.target.files?.[0])}
          />
          {file ? (
            <>
              <div className="lead-import-modal__filename">📄 {file.name}</div>
              <button type="button" className="lead-import-modal__change-link" onClick={() => setFile(null)}>
                Remove &amp; choose a different file
              </button>
            </>
          ) : (
            <>
              <div className="lead-import-modal__dropzone-title">
                Drag &amp; Drop your file /{" "}
                <button type="button" className="lead-import-modal__select-link" onClick={() => fileInputRef.current?.click()}>
                  Select File
                </button>
              </div>
              <div className="lead-import-modal__dropzone-hint">Upload CSV up to 5 MB</div>
            </>
          )}
        </div>

        <a className="lead-import-modal__template-link" href={leadImportTemplateUrl()} download>
          Download Sample Template ⬇
        </a>

        {error && <div className="state-message state-message--error">{error}</div>}

        <div className="channel-picker-modal__actions lead-import-modal__actions">
          <button type="button" className="btn btn--ghost lead-import-modal__cancel" onClick={onCancel} disabled={uploading}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--cta lead-import-modal__upload"
            onClick={handleUpload}
            disabled={!file || uploading}
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
