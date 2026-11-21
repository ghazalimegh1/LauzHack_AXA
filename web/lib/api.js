// Talks to the FastAPI backend (server.py). The website and the API come from the same
// server, so plain relative URLs like "/api/info" work everywhere.

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "The server did not answer. Is it running?");
  return body;
}

export const getInfo = () => getJSON("/api/info");

// The newest finished check, so a run started on one page also shows on the other.
export async function getLatest() {
  const { job_id } = await getJSON("/api/latest");
  if (!job_id) return null;
  const job = await getJSON(`/api/jobs/${job_id}`);
  return job.status === "ok" ? { jobId: job_id, result: job.result } : null;
}

// Asks every second until the check is done. onProgress(step) gets the step the server is
// on ("address", "frames", "privacy", "ai", "plan"), so the page shows real progress.
async function waitFor(jobId, onProgress) {
  for (;;) {
    await sleep(1000);
    const job = await getJSON(`/api/jobs/${jobId}`);
    if (job.stage && onProgress) onProgress(job.stage);
    if (job.status === "ok") return { jobId, result: job.result };
    if (job.status === "error") throw new Error(job.error);
  }
}

async function post(url, body, failMessage) {
  const res = await fetch(url, { method: "POST", body });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || failMessage);
  return data;
}

// Uploads the video. The server answers at once with a job id because a check takes 5-60 s.
export async function runCheck(formData, onProgress) {
  const { job_id } = await post("/api/analyze", formData, "The upload did not work. Please try again.");
  return waitFor(job_id, onProgress);
}

// Same check again with the video the server already has (no second upload).
export async function retryCheck(jobId, onProgress) {
  const { job_id } = await post(`/api/jobs/${jobId}/retry`, null, "Please upload the video again.");
  return waitFor(job_id, onProgress);
}

// Swiss addresses matching what was typed; [] if the search is unavailable.
export async function suggestAddresses(text) {
  if (text.trim().length < 3) return [];
  const { suggestions } = await getJSON(`/api/address?q=${encodeURIComponent(text)}`).catch(() => ({}));
  return suggestions || [];
}

export const frameUrl = (jobId, n) => `/api/jobs/${jobId}/frame/${n}.jpg`;
export const cropUrl = (jobId, id) => `/api/jobs/${jobId}/crop/${id}.jpg`;
export const stripUrl = (jobId) => `/api/jobs/${jobId}/strip.png`;
export const videoUrl = (jobId) => `/api/jobs/${jobId}/video`;

// Next storm at the site, from the live weather forecast: { ok, storm, hours, source }.
export const getForecast = (jobId) => getJSON(`/api/jobs/${jobId}/forecast`);
