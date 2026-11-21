// Talking to the Python server. Same address in the demo (port 8000);
// `npm run dev` forwards /api to it.

async function readJson(res) {
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : null;
    const err = new Error(detail || "The server did not answer. Please try again.");
    err.status = res.status;
    throw err;
  }
  return body;
}

export async function getLatest() {
  const res = await fetch("/api/latest", { cache: "no-store" });
  if (res.status === 404) return null;
  return readJson(res);
}

export async function getJob(id) {
  return readJson(await fetch(`/api/jobs/${id}`, { cache: "no-store" }));
}

export async function getInfo() {
  return readJson(await fetch("/api/info", { cache: "no-store" }));
}

export async function getForecast(id) {
  return readJson(await fetch(`/api/jobs/${id}/forecast`, { cache: "no-store" }));
}

export async function suggest(text) {
  const res = await fetch(`/api/suggest?q=${encodeURIComponent(text)}`);
  if (!res.ok) return [];
  const body = await res.json();
  return body.suggestions || [];
}

export async function startCheck({ address, file, keyframes, detector, simulate }) {
  const data = new FormData();
  data.append("address", address);
  data.append("video", file);
  if (keyframes) data.append("keyframes", String(keyframes));
  if (detector !== undefined) data.append("detector", detector ? "true" : "false");
  if (simulate) {
    data.append("sim_hail", String(simulate.hail));
    data.append("sim_water", String(simulate.water));
  }
  let res;
  try {
    res = await fetch("/api/analyze", { method: "POST", body: data });
  } catch {
    throw new Error("We could not reach the server. Please check that it is running and try again.");
  }
  return readJson(res);
}

// Polls a job once a second until it is done or failed.
export function follow(id, onUpdate) {
  let stopped = false;
  async function tick() {
    if (stopped) return;
    try {
      const job = await getJob(id);
      onUpdate(job);
      if (job.status === "done" || job.status === "failed") return;
    } catch (err) {
      onUpdate({ id, status: "failed", error: err.message });
      return;
    }
    setTimeout(tick, 1000);
  }
  tick();
  return () => {
    stopped = true;
  };
}

export const img = {
  keyframe: (job, n, boxes = true) => `/api/jobs/${job}/keyframes/${n}.jpg${boxes ? "" : "?boxes=0"}`,
  crop: (job, id) => `/api/jobs/${job}/crops/${id}.jpg`,
  thumb: (job, i) => `/api/jobs/${job}/thumbs/${i}.jpg`,
  video: (job) => `/api/jobs/${job}/video`,
};
