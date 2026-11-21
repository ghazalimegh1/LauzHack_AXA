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

// Uploads the video, then asks every second until the check is done.
// The server answers at once with a job id because a check takes 5-60 seconds.
export async function runCheck(formData) {
  const res = await fetch("/api/analyze", { method: "POST", body: formData });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "The upload did not work. Please try again.");
  for (;;) {
    await sleep(1000);
    const job = await getJSON(`/api/jobs/${body.job_id}`);
    if (job.status === "ok") return { jobId: body.job_id, result: job.result };
    if (job.status === "error") throw new Error(job.error);
  }
}

export const frameUrl = (jobId, n) => `/api/jobs/${jobId}/frame/${n}.jpg`;
export const cropUrl = (jobId, id) => `/api/jobs/${jobId}/crop/${id}.jpg`;
export const stripUrl = (jobId) => `/api/jobs/${jobId}/strip.png`;
