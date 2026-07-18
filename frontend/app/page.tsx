"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Orientation = "portrait" | "landscape";
type JobStatus = "queued" | "generating_voiceover" | "generating_code" | "rendering" | "retrying" | "muxing" | "complete" | "failed";

type Job = {
  id: string;
  status: JobStatus;
  progress_message: string;
  output_video_url: string | null;
  estimated_cost_usd: number;
  parent_job_id: string | null;
  edited_beat_number: number | null;
  failure_code: string | null;
};

type Beat = {
  beat_number: number;
  start: number;
  end: number;
  on_screen: string;
  vo_text: string | null;
  thumbnail_url: string;
};

type BeatParams = {
  scale: number | null;
  gap: number | null;
  speed: number | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

function outputUrl(path: string | null) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

function sceneNameFromTopic(topic: string) {
  const cleaned = topic.replace(/[^A-Za-z0-9]+/g, " ").trim();
  const words = cleaned ? cleaned.split(/\s+/) : ["Math", "Scene"];
  const base = words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join("");
  return `${base || "Math"}Scene`.replace(/^[^A-Za-z_]+/, "MathScene").slice(0, 90);
}

export default function Home() {
  const [topic, setTopic] = useState("Taylor series");
  const [audience, setAudience] = useState("JEE aspirants");
  const [duration, setDuration] = useState(60);
  const [orientation, setOrientation] = useState<Orientation>("portrait");
  const [sceneName, setSceneName] = useState("TaylorSeriesScene");
  const [job, setJob] = useState<Job | null>(null);
  const [beats, setBeats] = useState<Beat[]>([]);
  const [beatParams, setBeatParams] = useState<Record<number, BeatParams>>({});
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const eventSourceRef = useRef<EventSource | null>(null);

  const currentVideoUrl = useMemo(() => outputUrl(job?.output_video_url ?? null), [job?.output_video_url]);

  useEffect(() => {
    setSceneName(sceneNameFromTopic(topic));
  }, [topic]);

  useEffect(() => {
    return () => eventSourceRef.current?.close();
  }, []);

  async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {})
      }
    });
    if (!response.ok) {
      const text = await response.text();
      let detail = text;
      try {
        const payload = JSON.parse(text) as { detail?: string };
        detail = payload.detail || text;
      } catch {
        // Keep the server's plain-text response when it is not JSON.
      }
      throw new Error(detail || response.statusText);
    }
    return response.json();
  }

  function watchJob(jobId: string) {
    eventSourceRef.current?.close();
    const source = new EventSource(`${API_BASE}/api/jobs/${jobId}/stream`);
    eventSourceRef.current = source;
    source.addEventListener("job", (event) => {
      const nextJob = JSON.parse((event as MessageEvent).data) as Job;
      setJob(nextJob);
      if (nextJob.status === "complete" || nextJob.status === "failed") {
        source.close();
        if (nextJob.status === "complete") loadBeats(nextJob.id);
      }
    });
    source.onerror = () => {
      source.close();
      const poll = window.setInterval(async () => {
        try {
          const nextJob = await api<Job>(`/api/jobs/${jobId}`);
          setJob(nextJob);
          if (nextJob.status === "complete" || nextJob.status === "failed") {
            window.clearInterval(poll);
            if (nextJob.status === "complete") loadBeats(nextJob.id);
          }
        } catch {
          window.clearInterval(poll);
        }
      }, 3000);
    };
  }

  async function loadBeats(jobId: string) {
    const nextBeats = await api<Beat[]>(`/api/jobs/${jobId}/beats`);
    setBeats(nextBeats);
    const entries = await Promise.all(
      nextBeats.map(async (beat) => {
        try {
          const params = await api<BeatParams>(`/api/jobs/${jobId}/beats/${beat.beat_number}/params`);
          return [beat.beat_number, params] as const;
        } catch {
          return [beat.beat_number, { scale: null, gap: null, speed: null }] as const;
        }
      })
    );
    setBeatParams(Object.fromEntries(entries));
  }

  async function generateVideo() {
    setError("");
    setGenerating(true);
    setBeats([]);
    setBeatParams({});
    try {
      const result = await api<{ job_id: string }>("/api/generate", {
        method: "POST",
        body: JSON.stringify({ topic, duration_seconds: duration, audience, scene_name: sceneName, orientation })
      });
      const nextJob = await api<Job>(`/api/jobs/${result.job_id}`);
      setJob(nextJob);
      watchJob(result.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation request failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function regenerateBeat(beat: Beat) {
    if (!job) return;
    setError("");
    try {
      const result = await api<{ job_id: string }>(`/api/jobs/${job.id}/beats/${beat.beat_number}/regenerate`, {
        method: "POST",
        body: JSON.stringify({ on_screen: beat.on_screen, vo_text: beat.vo_text || "(silent)" })
      });
      const nextJob = await api<Job>(`/api/jobs/${result.job_id}`);
      setJob(nextJob);
      setBeats([]);
      setBeatParams({});
      watchJob(result.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Beat regeneration request failed.");
    }
  }

  function updateBeat(index: number, patch: Partial<Beat>) {
    setBeats((current) => current.map((beat) => (beat.beat_number === index ? { ...beat, ...patch } : beat)));
  }

  function updateBeatParam(index: number, key: keyof BeatParams, value: number | null) {
    setBeatParams((current) => ({
      ...current,
      [index]: {
        ...(current[index] || { scale: null, gap: null, speed: null }),
        [key]: value
      }
    }));
  }

  async function applyBeatParams(beat: Beat) {
    if (!job) return;
    const params = beatParams[beat.beat_number];
    if (!params) return;
    setError("");
    try {
      const result = await api<{ job_id: string }>(`/api/jobs/${job.id}/beats/${beat.beat_number}/params`, {
        method: "PATCH",
        body: JSON.stringify(params)
      });
      const nextJob = await api<Job>(`/api/jobs/${result.job_id}`);
      setJob(nextJob);
      setBeats([]);
      setBeatParams({});
      watchJob(result.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Beat parameter edit request failed.");
    }
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <h1 className="brand">Vivacity Studio</h1>
        <p className="subtle">Generate beat-structured Manim videos through the async backend.</p>

        <section className="section">
          <h2>Video Inputs</h2>
          <div className="field">
            <label>Topic</label>
            <input className="input" value={topic} onChange={(event) => setTopic(event.target.value)} />
          </div>
          <div className="field">
            <label>Audience</label>
            <input className="input" value={audience} onChange={(event) => setAudience(event.target.value)} />
          </div>
          <div className="field">
            <label>Duration</label>
            <div className="row">
              {[30, 60, 90].map((value) => (
                <button key={value} className={duration === value ? "segment active" : "segment"} onClick={() => setDuration(value)}>
                  {value}s
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <label>Orientation</label>
            <div className="segmented">
              <button className={orientation === "portrait" ? "segment active" : "segment"} onClick={() => setOrientation("portrait")}>
                Portrait
              </button>
              <button className={orientation === "landscape" ? "segment active" : "segment"} onClick={() => setOrientation("landscape")}>
                Landscape
              </button>
            </div>
          </div>
          <div className="field">
            <label>Scene class</label>
            <input className="input" value={sceneName} onChange={(event) => setSceneName(event.target.value)} />
          </div>
          <button className="primary" onClick={generateVideo} disabled={generating || !topic.trim() || !audience.trim()}>
            {generating ? "Submitting..." : "Generate Video"}
          </button>
        </section>
      </aside>

      <section className="main">
        {error && <div className="status error">{error}</div>}
        {job && (
          <div className={job.status === "failed" ? "status error" : "status"}>
            <strong>{job.status === "failed" ? "Generation failed" : job.status}</strong>
            <div className="subtle">{job.progress_message}</div>
            {job.status === "failed" && (
              <button className="secondary" onClick={generateVideo} disabled={generating}>
                {generating ? "Submitting..." : "Retry Generation"}
              </button>
            )}
          </div>
        )}

        {currentVideoUrl && (
          <section className="section">
            <h2>Rendered Video</h2>
            <video className="video" controls src={currentVideoUrl} />
            {job?.status === "complete" && (
              <div className="render-cost" aria-label="Estimated video generation cost">
                <span>Estimated generation cost</span>
                <strong>${job.estimated_cost_usd.toFixed(4)}</strong>
              </div>
            )}
          </section>
        )}

        {beats.length > 0 && (
          <section className="section">
            <h2>Beat Timeline</h2>
            <div className="timeline">
              {beats.map((beat) => (
                <article className="beat" key={beat.beat_number}>
                  <img src={outputUrl(beat.thumbnail_url) || ""} alt={`Beat ${beat.beat_number}`} />
                  <div className="beat-body">
                    <div className="beat-title">
                      Beat {beat.beat_number} · {beat.start.toFixed(1)}s-{beat.end.toFixed(1)}s
                    </div>
                    <textarea
                      className="input"
                      value={beat.on_screen}
                      onChange={(event) => updateBeat(beat.beat_number, { on_screen: event.target.value })}
                    />
                    <textarea
                      className="input"
                      value={beat.vo_text || "(silent)"}
                      onChange={(event) => updateBeat(beat.beat_number, { vo_text: event.target.value })}
                    />
                    <div className="row">
                      <label className="subtle">
                        Scale
                        <input
                          className="input"
                          type="number"
                          min="0.5"
                          max="2"
                          step="0.05"
                          value={beatParams[beat.beat_number]?.scale ?? ""}
                          onChange={(event) =>
                            updateBeatParam(beat.beat_number, "scale", event.target.value === "" ? null : Number(event.target.value))
                          }
                        />
                      </label>
                      <label className="subtle">
                        Gap
                        <input
                          className="input"
                          type="number"
                          min="-6"
                          max="6"
                          step="0.1"
                          value={beatParams[beat.beat_number]?.gap ?? ""}
                          onChange={(event) =>
                            updateBeatParam(beat.beat_number, "gap", event.target.value === "" ? null : Number(event.target.value))
                          }
                        />
                      </label>
                      <label className="subtle">
                        Speed
                        <input
                          className="input"
                          type="number"
                          min="0.3"
                          max="3"
                          step="0.05"
                          value={beatParams[beat.beat_number]?.speed ?? ""}
                          onChange={(event) =>
                            updateBeatParam(beat.beat_number, "speed", event.target.value === "" ? null : Number(event.target.value))
                          }
                        />
                      </label>
                    </div>
                    <button className="secondary" onClick={() => applyBeatParams(beat)}>
                      Apply Visual Params
                    </button>
                    <button className="secondary" onClick={() => regenerateBeat(beat)}>
                      Regenerate This Beat
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
