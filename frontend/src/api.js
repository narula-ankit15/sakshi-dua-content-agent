// "??" (not "||") so an explicitly empty VITE_API_BASE -- meaning "call the
// API on this same origin," used in production where one server serves both
// the built frontend and the API -- doesn't fall back to the dev default.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8123";

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export function listContent({ topicIds = [], channel } = {}) {
  const params = new URLSearchParams();
  topicIds.forEach((id) => params.append("topic_id", id));
  if (channel && channel !== "all") params.set("channel", channel);
  return request(`/content-library?${params.toString()}`);
}

export function getContent(creativeId) {
  return request(`/content-library/${encodeURIComponent(creativeId)}`);
}

export function deleteContent(creativeId) {
  return request(`/content-library/${encodeURIComponent(creativeId)}`, { method: "DELETE" });
}

export function renameContent(creativeId, templateName) {
  return request(`/content-library/${encodeURIComponent(creativeId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_name: templateName }),
  });
}

export function runCampaign(brief) {
  return request("/campaigns/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(brief),
  });
}

export function listAssets(topicId) {
  return request(`/assets?${new URLSearchParams({ topic_id: topicId }).toString()}`);
}

export function listTopics() {
  return request("/topics");
}

export function getInsights(topicId) {
  return request(`/insights?${new URLSearchParams({ topic_id: topicId }).toString()}`);
}

export function getUsage() {
  return request("/usage");
}

export function setUsageCap(dailyCap) {
  return request("/usage/cap", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ daily_cap: dailyCap }),
  });
}

function postJson(path, payload) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function putJson(path, payload) {
  return request(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function generateCampaign(payload) {
  return postJson("/campaigns/generate", payload);
}

export function reviseEmail(payload) {
  return postJson("/campaigns/revise/email", payload);
}

export function reviseWhatsapp(payload) {
  return postJson("/campaigns/revise/whatsapp", payload);
}

export function reviseBrochure(payload) {
  return postJson("/campaigns/revise/brochure", payload);
}

export function generateMoreSubjectLines(payload) {
  return postJson("/campaigns/generate-more-subject-lines", payload);
}

export function saveEmail(payload) {
  return postJson("/content-library/email", payload);
}

export function saveWhatsapp(payload) {
  return postJson("/content-library/whatsapp", payload);
}

export function saveBrochure(payload) {
  return postJson("/content-library/brochure", payload);
}

export function updateEmail(creativeId, payload) {
  return putJson(`/content-library/email/${encodeURIComponent(creativeId)}`, payload);
}

export function updateWhatsapp(creativeId, payload) {
  return putJson(`/content-library/whatsapp/${encodeURIComponent(creativeId)}`, payload);
}

export function updateBrochure(creativeId, payload) {
  return putJson(`/content-library/brochure/${encodeURIComponent(creativeId)}`, payload);
}

export function duplicateContent(creativeId) {
  return request(`/content-library/${encodeURIComponent(creativeId)}/duplicate`, { method: "POST" });
}

export function saveGeneratedAsset(payload) {
  return postJson("/assets/generated", payload);
}

export function uploadAsset(topicId, file, tags = []) {
  const form = new FormData();
  form.set("topic_id", topicId);
  form.set("tags", tags.join(","));
  form.set("file", file);
  return request("/assets/upload", { method: "POST", body: form });
}

export function suggestOverlayText(payload) {
  return postJson("/assets/suggest-overlay-text", payload);
}

export function sendEmail(payload) {
  return postJson("/send-email", payload);
}

export function getEmailSenders() {
  return request("/email-senders");
}

export function getEmailSends(creativeId) {
  return request(`/content-library/${encodeURIComponent(creativeId)}/sends`);
}

export function listLeads({ search } = {}) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  const qs = params.toString();
  return request(`/leads${qs ? `?${qs}` : ""}`);
}

export function createLead(payload) {
  return postJson("/leads", payload);
}

export function updateLead(leadId, payload) {
  return putJson(`/leads/${encodeURIComponent(leadId)}`, payload);
}

export function deleteLead(leadId) {
  return request(`/leads/${encodeURIComponent(leadId)}`, { method: "DELETE" });
}

export function importLeadsCsv(file) {
  const form = new FormData();
  form.set("file", file);
  return request("/leads/import", { method: "POST", body: form });
}

export function listLeadImportHistory(limit = 20) {
  return request(`/leads/import-history?limit=${limit}`);
}

export function leadImportReportUrl(batchId) {
  return `${API_BASE}/leads/import-history/${encodeURIComponent(batchId)}/report`;
}

export function leadImportTemplateUrl() {
  return `${API_BASE}/leads/import-template`;
}
