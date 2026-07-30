# VIVACITY — Complete Strategy Document (VERIFIED)

---

## 1. COST PER VIDEO

**[PROJECTED — No cost-logging system exists for render compute]**

The template pipeline (heuristic planner) makes **zero LLM calls** per render. All completed jobs in the DB show `estimated_cost_usd=0.0` because:
- `RENDER_COMPUTE_USD_PER_HOUR=0` (env var not set — render compute is not tracked)
- The heuristic planner generates scenes deterministically without calling any LLM
- `cost_breakdown` exists in code with buckets for `anthropic`, `openai`, `gemini`, `openai_tts`, `render_only`, `render_compute` — but ALL show 0 calls and 0 cost

**LLM costs DO exist** for topic-based storyboard generation (when not using direct storyboard). Real logged data from the database:

| Job ID | LLM | Calls | Input Tokens | Output Tokens | Cost USD | Cost INR |
|---|---|---|---|---|---|---|
| `2e2452e0..` | Gemini | 4 | 6,366 | 2,810 | $0.0089 | ₹0.74 |
| `c1fa12f7..` | Gemini | 3 | 4,260 | 2,328 | $0.0071 | ₹0.59 |
| `5b58e0d6..` | Gemini | 3 | 5,937 | 2,489 | $0.0080 | ₹0.66 |

**[VERIFIED — cost logging code exists at pipeline.py:510-570]**

**Cost per video estimates (unverified — based on token pricing, not measured):**

| Quality | Complexity | LLM Cost | Render Cost | **Total** |
|---|---|---|---|---|
| 720p30 (min) | Simple | ₹0.05 | [PROJECTED] | **₹0.07** |
| 720p30 | Medium | ₹0.12 | [PROJECTED] | **₹0.20** |
| 4K90 (max) | Complex | ₹0.50 | [PROJECTED] | **₹4.50** |

---

## 2. PRICING PLANS [PROJECTED — no payment system implemented yet]

All pricing tiers are placeholders. No payment integration exists. Current state: **₹0 for everyone, always.**

### Proposed tiers for YC application:

| Tier | Price | Current Status |
|---|---|---|
| **Free** | ₹0/mo | ✅ All users are on this tier |
| **Student** | ₹99/mo | ❌ Not implemented |
| **Pro** | ₹299/mo | ❌ Not implemented |
| **Institution** | Custom | ❌ Not implemented |

**[PROJECTED — no Stripe/Razorpay integration, no usage tracking, no billing system]**

---

## 3. LAUNCH TIMELINE

### Current Status [VERIFIED — all checked with real test output]

| Item | Status | Evidence |
|---|---|---|
| **Rendering pipeline** | ✅ VERIFIED | 232/232 tests pass |
| **Frontend — all 9 integrations** | ✅ VERIFIED | 9/9 points verified live (with valid storyboard input) |
| **Video editor** | ✅ VERIFIED | Endpoints exist: `GET /api/jobs/{id}/beats`, `POST /api/jobs/{id}/beats/{n}/regenerate`, `PATCH /api/jobs/{id}/beats/{n}/params`. Editor HTML at `editor.html`. Regeneration confirmed working for complete jobs |
| **Multi-scene stitching** | ✅ VERIFIED | Template pipeline produces multi-beat videos (6 beats verified) |
| **Render acceptance checks** | ✅ VERIFIED | `run_render_acceptance()` passes at end of construct() |
| **Custom Manim scenes** | ⚠️ PARTIAL | Files exist (taylor_pro, fourier_laplace, taylor_portrait). Excluded from compliance suite because they use raw Scene. Video files exist. NOT VivacityScene-compliant |
| **S3 env vars on Render** | ❌ NOT SET | Code exists in `storage.py` (lines 301-325). Falls back to local /outputs/ |
| **Deployed to Render** | ❌ NOT DONE | Dockerfile and compose.production.yml are ready |
| **Prerequisite data** | ❌ NOT AUTHORED | Stub only |
| **Real student testing** | ❌ ZERO SESSIONS | No students have watched a video |

### Phase 1 — Technical Completion (estimated: 3-5 days)

| Task | Time | Status |
|---|---|---|
| Set S3 env vars on Render dashboard | 1 hr | ✅ Code ready, just needs config |
| Deploy Docker container to Render | 1 day | ⏳ Dockerfile ready, not deployed |
| Configure domain + SSL | 1 day | ⏳ |
| Point frontend at Render URL | 1 hr | ⏳ |
| Test end-to-end on live deployment | 1 day | ⏳ |

### Phase 2 — Content + Student Validation (estimated: 3-4 weeks)
### Phase 3 — Soft Launch (estimated: 1-2 weeks after Phase 2)

**[PROJECTED — all timelines are estimates, not based on measured velocity]**

---

## 4. MARKETING STRATEGY [PROJECTED — zero marketing activity to date]

No marketing has been executed. No Telegram posts. No educator contacts. No social media presence.

**The single highest-leverage action:** Post 1 free video/week in JEE Telegram groups (50k-500k members each).

**[PROJECTED — no real traction data exists]**

---

## 5. RESOURCE LINKS [VERIFIED]

### Running Services (Local — verified live)
```
Workspace:  http://127.0.0.1:3000/workspace.html
Editor:     http://127.0.0.1:3000/editor.html
Backend:    http://127.0.0.1:8080
```

### Generated Videos (Local — files verified to exist)
```
Latest escape velocity:  /outputs/4cc328dd-d147-47c8-b43c-78bab8517043_LongTest_FINAL.mp4
Taylor Pro (85 anims):   /outputs/taylor_pro/videos/.../TaylorProScene.mp4
Fourier/Laplace (70):    /outputs/fourier_laplace/videos/.../FourierLaplaceScene_CFR.mp4
```

### Key API Endpoints [VERIFIED — all tested against live backend]

| Endpoint | Verified |
|---|---|
| `POST /api/generate` | ✅ Returns job_id |
| `GET /api/jobs/{id}` | ✅ Returns status + video URL |
| `GET /api/jobs/{id}/beats` | ✅ Returns beat array with thumbnails |
| `POST /api/jobs/{id}/beats/{n}/regenerate` | ✅ Creates child job |
| `PATCH /api/jobs/{id}/beats/{n}/params` | ✅ Returns updated job |
| `POST /videos/{id}/recall-response` | ✅ Returns {correct: bool} |
| `GET /health/live` | ✅ Returns 200 |

---

## 6. VERIFICATION SUMMARY

| Section | Status |
|---|---|
| Cost-per-video table | **[PROJECTED — no render compute cost tracking]** |
| Pricing plans | **[PROJECTED — no payment integration]** |
| Launch timeline phases 2-3 | **[PROJECTED — estimates only]** |
| Marketing strategy | **[PROJECTED — zero activity]** |
| YC application numbers | **[PROJECTED — no user data exists]** |
| Frontend 9 integrations | **[VERIFIED — 9/9 working]** |
| Rendering pipeline | **[VERIFIED — 232 tests pass]** |
| Compliance suite | **[VERIFIED — all managed scenes pass]** |
| Custom scenes (taylor_pro, etc.) | **[VERIFIED — files exist, rendered, but exempt from compliance]** |
| Video editor endpoints | **[VERIFIED — all respond correctly]** |
| Running services | **[VERIFIED — all respond to HTTP]** |

---

## 7. IMMEDIATE NEXT STEPS (Priority Order)

| # | Action | Evidence Needed |
|---|---|---|
| 1 | ⬜ Set `RENDER_COMPUTE_USD_PER_HOUR` to a real number | Cost table becomes verifiable |
| 2 | ⬜ Deploy to Render with S3 env vars | Phase 1 complete |
| 3 | ⬜ Author 5 topics with prerequisite data | Phase 2 can begin |
| 4 | ⬜ Get 1 real student to watch a video | First user data point |
| 5 | ⬜ Post 1 video in a Telegram group | First marketing action |
