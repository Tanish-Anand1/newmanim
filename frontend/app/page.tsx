"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Orientation = "portrait" | "landscape";
type JobStatus =
  | "queued"
  | "generating_voiceover"
  | "generating_code"
  | "rendering"
  | "retrying"
  | "muxing"
  | "complete"
  | "failed";

type Job = {
  id: string;
  status: JobStatus;
  progress_message: string;
  output_video_url: string | null;
  estimated_cost_usd: number;
  parent_job_id: string | null;
  edited_beat_number: number | null;
  failure_code: string | null;
  recall_question: RecallQuestion | null;
};

type RecallQuestion = {
  question_id: string;
  question: string;
  answer: string;
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

type ExamContext = "JEE Main" | "JEE Advanced" | "NEET" | null;
type ConfidenceLevel = 1 | 2 | 3 | 4 | 5;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const PREREQ_OPTIONS = [
  { value: "algebra", label: "Algebra" },
  { value: "trigonometry", label: "Trigonometry" },
  { value: "derivatives", label: "Derivatives" },
  { value: "integration", label: "Integration" },
];

function outputUrl(path: string | null) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

function sceneNameFromTopic(topic: string) {
  const cleaned = topic.replace(/[^A-Za-z0-9]+/g, " ").trim();
  const words = cleaned ? cleaned.split(/\s+/) : ["Math", "Scene"];
  const base = words
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join("");
  return `${base || "Math"}Scene`
    .replace(/^[^A-Za-z_]+/, "MathScene")
    .slice(0, 90);
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

  // NEW: Exam context, student signal, prerequisites
  const [examContext, setExamContext] = useState<ExamContext>("JEE Main");
  const [confidence, setConfidence] = useState<ConfidenceLevel>(3);
  const [weakTopic, setWeakTopic] = useState(false);
  const [prerequisites, setPrerequisites] = useState<string[]>([]);

  // NEW: Recall question state
  const [recallQuestion, setRecallQuestion] = useState<RecallQuestion | null>(null);
  const [recallAnswer, setRecallAnswer] = useState("");
  const [recallFeedback, setRecallFeedback] = useState("");
  const [recallCorrect, setRecallCorrect] = useState<boolean | null>(null);
  const [submittingRecall, setSubmittingRecall] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);

  const currentVideoUrl = useMemo(
    () => outputUrl(job?.output_video_url ?? null),
    [job?.output_video_url]
  );

  useEffect(() => {
    setSceneName(sceneNameFromTopic(topic));
  }, [topic]);

  useEffect(() => {
    return () => eventSourceRef.current?.close();
  }, []);

  // Reset recall when a new job starts
  useEffect(() => {
    if (job?.status === "complete") {
      if (job.recall_question) {
        setRecallQuestion(job.recall_question);
      }
    } else if (job?.status === "queued" || job?.status === "rendering") {
      setRecallQuestion(null);
      setRecallAnswer("");
      setRecallFeedback("");
      setRecallCorrect(null);
    }
  }, [job?.status, job?.recall_question]);

  function togglePrerequisite(value: string) {
    setPrerequisites((prev) =>
      prev.includes(value)
        ? prev.filter((v) => v !== value)
        : [...prev, value]
    );
  }

  async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
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
          const params = await api<BeatParams>(
            `/api/jobs/${jobId}/beats/${beat.beat_number}/params`
          );
          return [beat.beat_number, params] as const;
        } catch {
          return [
            beat.beat_number,
            { scale: null, gap: null, speed: null },
          ] as const;
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
    setRecallQuestion(null);
    setRecallAnswer("");
    setRecallFeedback("");
    setRecallCorrect(null);
    try {
      const body: Record<string, unknown> = {
        topic,
        duration_seconds: duration,
        audience,
        scene_name: sceneName,
        orientation,
        pipeline_profile: "template",
      };
      if (examContext) {
        body.exam_context = examContext;
      }
      if (confidence || weakTopic || prerequisites.length > 0) {
        body.student_signal = {
          self_rated_confidence: confidence,
          flagged_as_weak_topic: weakTopic,
          prior_attempt_count: 0,
          unconfirmed_prerequisites: prerequisites,
        };
      }
      if (prerequisites.length > 0) {
        body.assumed_prerequisites = prerequisites;
      }

      const result = await api<{ job_id: string }>("/api/generate", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const nextJob = await api<Job>(`/api/jobs/${result.job_id}`);
      setJob(nextJob);
      watchJob(result.job_id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Generation request failed."
      );
    } finally {
      setGenerating(false);
    }
  }

  async function submitRecallAnswer() {
    if (!job || !recallQuestion) return;
    const answer = recallAnswer.trim();
    if (!answer) {
      setRecallFeedback("Enter an answer first.");
      return;
    }
    setSubmittingRecall(true);
    setRecallFeedback("Checking...");
    try {
      const result = await api<{ correct: boolean }>(
        `/videos/${job.id}/recall-response`,
        {
          method: "POST",
          body: JSON.stringify({
            student_id: "local-student",
            question_id: recallQuestion.question_id,
            answer_given: answer,
          }),
        }
      );
      setRecallCorrect(result.correct);
      setRecallFeedback(
        result.correct
          ? "Correct. Nice work!"
          : "Not quite. Your answer was recorded for a later recap."
      );
    } catch (err) {
      setRecallFeedback(
        err instanceof Error ? err.message : "Could not submit answer."
      );
    } finally {
      setSubmittingRecall(false);
    }
  }

  async function regenerateBeat(beat: Beat) {
    if (!job) return;
    setError("");
    try {
      const result = await api<{ job_id: string }>(
        `/api/jobs/${job.id}/beats/${beat.beat_number}/regenerate`,
        {
          method: "POST",
          body: JSON.stringify({
            on_screen: beat.on_screen,
            vo_text: beat.vo_text || "(silent)",
          }),
        }
      );
      const nextJob = await api<Job>(`/api/jobs/${result.job_id}`);
      setJob(nextJob);
      setBeats([]);
      setBeatParams({});
      watchJob(result.job_id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Beat regeneration request failed."
      );
    }
  }

  function updateBeat(index: number, patch: Partial<Beat>) {
    setBeats((current) =>
      current.map((beat) =>
        beat.beat_number === index ? { ...beat, ...patch } : beat
      )
    );
  }

  function updateBeatParam(
    index: number,
    key: keyof BeatParams,
    value: number | null
  ) {
    setBeatParams((current) => ({
      ...current,
      [index]: {
        ...(current[index] || { scale: null, gap: null, speed: null }),
        [key]: value,
      },
    }));
  }

  async function applyBeatParams(beat: Beat) {
    if (!job) return;
    const params = beatParams[beat.beat_number];
    if (!params) return;
    setError("");
    try {
      const result = await api<{ job_id: string }>(
        `/api/jobs/${job.id}/beats/${beat.beat_number}/params`,
        {
          method: "PATCH",
          body: JSON.stringify(params),
        }
      );
      const nextJob = await api<Job>(`/api/jobs/${result.job_id}`);
      setJob(nextJob);
      setBeats([]);
      setBeatParams({});
      watchJob(result.job_id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Beat parameter edit request failed."
      );
    }
  }

  function statusClass(): string {
    if (!job) return "";
    if (job.status === "failed") return "status error";
    if (job.status === "complete") return "status complete";
    return "status";
  }

  function stageLabel(): string {
    if (!job) return "";
    const map: Record<string, string> = {
      queued: "● Queued",
      generating_voiceover: "● Generating voiceover",
      generating_code: "● Generating code",
      rendering: "● Rendering",
      retrying: "● Retrying",
      muxing: "● Muxing",
      complete: "✓ Complete",
      failed: "✗ Failed",
    };
    return map[job.status] || job.status;
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <h1 className="brand">Vivacity Studio</h1>
        <p className="subtle">
          Generate beat-structured Manim videos through the async backend.
        </p>

        <section className="section">
          <h2>Video Inputs</h2>
          <div className="field">
            <label>Topic</label>
            <input
              className="input"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
            />
          </div>
          <div className="field">
            <label>Audience</label>
            <input
              className="input"
              value={audience}
              onChange={(event) => setAudience(event.target.value)}
            />
          </div>
          <div className="field">
            <label>Duration</label>
            <div className="row">
              {[30, 60, 90].map((value) => (
                <button
                  key={value}
                  className={
                    duration === value ? "segment active" : "segment"
                  }
                  onClick={() => setDuration(value)}
                >
                  {value}s
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <label>Orientation</label>
            <div className="segmented">
              <button
                className={
                  orientation === "portrait" ? "segment active" : "segment"
                }
                onClick={() => setOrientation("portrait")}
              >
                Portrait
              </button>
              <button
                className={
                  orientation === "landscape" ? "segment active" : "segment"
                }
                onClick={() => setOrientation("landscape")}
              >
                Landscape
              </button>
            </div>
          </div>

          {/* NEW: Exam Context */}
          <div className="field">
            <label>Exam Context</label>
            <select
              className="input"
              value={examContext || ""}
              onChange={(e) =>
                setExamContext(
                  (e.target.value as ExamContext) || null
                )
              }
            >
              <option value="">None</option>
              <option value="JEE Main">JEE Main</option>
              <option value="JEE Advanced">JEE Advanced</option>
              <option value="NEET">NEET</option>
            </select>
          </div>

          {/* NEW: Student Signal */}
          <div className="field">
            <label>Self-Rated Confidence</label>
            <div className="row">
              {([1, 2, 3, 4, 5] as ConfidenceLevel[]).map((level) => (
                <button
                  key={level}
                  className={
                    confidence === level ? "segment active" : "segment"
                  }
                  onClick={() => setConfidence(level)}
                >
                  {level}/5
                </button>
              ))}
            </div>
          </div>

          {/* NEW: Weak topic flag */}
          <div className="field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={weakTopic}
                onChange={(e) => setWeakTopic(e.target.checked)}
              />{" "}
              Flagged as weak topic
            </label>
          </div>

          {/* NEW: Prerequisites */}
          <div className="field">
            <label>Assumed Prerequisites</label>
            <div className="prereq-grid">
              {PREREQ_OPTIONS.map((pr) => (
                <label key={pr.value} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={prerequisites.includes(pr.value)}
                    onChange={() => togglePrerequisite(pr.value)}
                  />{" "}
                  {pr.label}
                </label>
              ))}
            </div>
          </div>

          <div className="field">
            <label>Scene class</label>
            <input
              className="input"
              value={sceneName}
              onChange={(event) => setSceneName(event.target.value)}
            />
          </div>
          <button
            className="primary"
            onClick={generateVideo}
            disabled={generating || !topic.trim() || !audience.trim()}
          >
            {generating ? "Submitting..." : "Generate Video"}
          </button>
        </section>
      </aside>

      <section className="main">
        {error && <div className="status error">{error}</div>}

        {/* Job status display */}
        {job && (
          <div className={statusClass()}>
            <strong>
              {stageLabel()}
              {job.status === "failed" && job.failure_code
                ? ` (${job.failure_code})`
                : ""}
            </strong>
            <div className="subtle">{job.progress_message}</div>

            {/* Render progress bar for active jobs */}
            {(job.status === "queued" ||
              job.status === "generating_voiceover" ||
              job.status === "generating_code" ||
              job.status === "rendering" ||
              job.status === "retrying" ||
              job.status === "muxing") && (
              <div className="progress-mini">
                <div className="progress-mini-track">
                  <div
                    className="progress-mini-fill"
                    style={{ width: `${computeProgress(job.status)}%` }}
                  />
                </div>
              </div>
            )}

            {job.status === "failed" && (
              <button
                className="secondary"
                onClick={generateVideo}
                disabled={generating}
                style={{ marginTop: 10 }}
              >
                {generating ? "Submitting..." : "Retry Generation"}
              </button>
            )}
          </div>
        )}

        {/* Video player */}
        {currentVideoUrl && (
          <section className="section">
            <h2>Rendered Video</h2>
            <video className="video" controls src={currentVideoUrl} />
            {job?.status === "complete" && (
              <div
                className="render-cost"
                aria-label="Estimated video generation cost"
              >
                <span>Estimated generation cost</span>
                <strong>${job.estimated_cost_usd.toFixed(4)}</strong>
              </div>
            )}
          </section>
        )}

        {/* NEW: Recall Question Panel — Point 5 & 6 */}
        {recallQuestion && job?.status === "complete" && (
          <section className="section recall-section">
            <h2>Quick Recall</h2>
            <div className="recall-card">
              <p className="recall-question-text">{recallQuestion.question}</p>
              <div className="recall-input-row">
                <input
                  className="input"
                  placeholder="Your answer..."
                  value={recallAnswer}
                  onChange={(e) => setRecallAnswer(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submitRecallAnswer();
                    }
                  }}
                  disabled={submittingRecall}
                />
                <button
                  className="primary"
                  onClick={submitRecallAnswer}
                  disabled={submittingRecall || !recallAnswer.trim()}
                >
                  {submittingRecall ? "Checking..." : "Check Answer"}
                </button>
              </div>
              {recallFeedback && (
                <p
                  className={`recall-feedback ${
                    recallCorrect === true
                      ? "recall-correct"
                      : recallCorrect === false
                      ? "recall-wrong"
                      : ""
                  }`}
                >
                  {recallFeedback}
                </p>
              )}
            </div>
          </section>
        )}

        {/* Beat Timeline */}
        {beats.length > 0 && (
          <section className="section">
            <h2>Beat Timeline</h2>
            <div className="timeline">
              {beats.map((beat) => (
                <article className="beat" key={beat.beat_number}>
                  <img
                    src={outputUrl(beat.thumbnail_url) || ""}
                    alt={`Beat ${beat.beat_number}`}
                  />
                  <div className="beat-body">
                    <div className="beat-title">
                      Beat {beat.beat_number} · {beat.start.toFixed(1)}s-
                      {beat.end.toFixed(1)}s
                    </div>
                    <textarea
                      className="input"
                      value={beat.on_screen}
                      onChange={(event) =>
                        updateBeat(beat.beat_number, {
                          on_screen: event.target.value,
                        })
                      }
                    />
                    <textarea
                      className="input"
                      value={beat.vo_text || "(silent)"}
                      onChange={(event) =>
                        updateBeat(beat.beat_number, {
                          vo_text: event.target.value,
                        })
                      }
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
                            updateBeatParam(
                              beat.beat_number,
                              "scale",
                              event.target.value === ""
                                ? null
                                : Number(event.target.value)
                            )
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
                            updateBeatParam(
                              beat.beat_number,
                              "gap",
                              event.target.value === ""
                                ? null
                                : Number(event.target.value)
                            )
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
                            updateBeatParam(
                              beat.beat_number,
                              "speed",
                              event.target.value === ""
                                ? null
                                : Number(event.target.value)
                            )
                          }
                        />
                      </label>
                    </div>
                    <button
                      className="secondary"
                      onClick={() => applyBeatParams(beat)}
                    >
                      Apply Visual Params
                    </button>
                    <button
                      className="secondary"
                      onClick={() => regenerateBeat(beat)}
                    >
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

/** Compute a rough progress percentage from the job status */
function computeProgress(status: string): number {
  const map: Record<string, number> = {
    queued: 5,
    generating_voiceover: 20,
    generating_code: 40,
    rendering: 60,
    retrying: 50,
    muxing: 85,
    complete: 100,
    failed: 100,
  };
  return map[status] || 0;
}
