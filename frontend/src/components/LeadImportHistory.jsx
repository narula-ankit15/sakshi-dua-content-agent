import { leadImportReportUrl } from "../api";

function formatDateTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function LeadImportHistory({ batches }) {
  if (batches.length === 0) return null;

  return (
    <div className="leads-table-wrap lead-import-history">
      <h3 className="lead-import-history__title">Lead Processing History</h3>
      <table className="leads-table">
        <thead>
          <tr>
            <th>Sr. No.</th>
            <th>Uploaded</th>
            <th>File</th>
            <th>Total Leads</th>
            <th>Imported</th>
            <th>Failed</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((batch, i) => (
            <tr key={batch.id}>
              <td>{i + 1}</td>
              <td className="leads-table__date">{formatDateTime(batch.created_at)}</td>
              <td>{batch.filename}</td>
              <td>{batch.total_rows}</td>
              <td>{batch.imported_count}</td>
              <td className={batch.failed_count > 0 ? "lead-import-history__failed" : ""}>{batch.failed_count}</td>
              <td>
                <span className={`lead-import-status-pill lead-import-status-pill--${batch.status}`}>
                  {batch.status === "success" ? "Success" : "Error"}
                </span>
              </td>
              <td>
                {batch.failed_count > 0 ? (
                  <a className="lead-import-history__download" href={leadImportReportUrl(batch.id)} download>
                    ⬇ Download
                  </a>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
