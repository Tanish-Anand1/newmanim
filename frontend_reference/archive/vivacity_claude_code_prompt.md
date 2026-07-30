# VIVACITY — Claude Code Prompt
# Research & Educational Video Generation Tool
# v2.0 — Complete Rewrite

---

> PASTE THIS INTO CLAUDE CODE. BUILD IN PHASES, NOT ALL AT ONCE.
> This is a serious research tool, not a consumer product.
> Aesthetic reference: Perplexity, Cursor, Linear, arxiv-sanity — not Framer, Loom, or Lovable.

---

## WHAT THIS IS

**Vivacity** is a Manim-based AI video generation engine for researchers, students, and educators. You give it a mathematical or scientific concept — it returns a precisely animated explanation video. Think computational notebook meets 3Blue1Brown.

The brand identity:
- Logo: the letter **V.** (capital V, followed by a period) set in **GeistPixelSquare**, white on black. That's it. No icon, no gradient, no border.
- Name: **vivacity** — always lowercase in body text. Only the logo uses the pixel font.
- Tone: a research tool. Spare. Precise. Zero decoration.

---

## HARD RULES — CLAUDE CODE MUST FOLLOW EVERY ONE

**NEVER:**
- Use emojis anywhere. Not one. Zero.
- Use purple, teal, blue, or any gradient accent color
- Use rounded-full on anything except pill tags and the one CTA button
- Add floating blobs, particle effects, gradient orbs, or any background decoration
- Use Inter, Roboto, or any "safe" font for headings — GeistPixelSquare is the display font
- Generate bento grid layouts with icon + title + short description cards
- Write marketing copy ("Revolutionize", "Powerful", "Seamless", "Next-gen")
- Add hover animations to more than 3 elements on the page
- Center every heading — left-aligned headings feel more editorial and serious
- Add more than 2 images/illustrations — this site is type-driven

**MUST:**
- Use `GeistPixelSquare` for the logo (V.) and ALL section headings
- Use `GeistMono` for labels, metadata, code, timestamps, tags, nav links
- Use `GeistSans` for body text only
- The page should feel like a tool someone would open in a research session, not a product someone would screenshot for Twitter
- Every section has maximum 2 lines of body copy — no walls of text
- Mobile responsive at 375px minimum
- `prefers-reduced-motion` must disable all animation

---

## FONT SETUP (CRITICAL — DO THIS FIRST)

```tsx
// app/layout.tsx
import { GeistSans } from "geist/font/sans"
import { GeistMono } from "geist/font/mono"
import { GeistPixelSquare } from "geist/font/pixel"

// Apply all three as CSS variables
<html className={`
  ${GeistSans.variable}
  ${GeistMono.variable}
  ${GeistPixelSquare.variable}
`}>
```

```css
/* globals.css — map to CSS custom properties */
:root {
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
  --font-pixel: var(--font-geist-pixel-square);
}
```

```js
// tailwind.config.js
fontFamily: {
  sans: ["var(--font-geist-sans)"],
  mono: ["var(--font-geist-mono)"],
  pixel: ["var(--font-geist-pixel-square)"],
}
```

Usage in components:
- `font-pixel` → logo, all H1/H2 headings, section labels
- `font-mono` → nav links, tags, metadata, timestamps, pricing amounts, code
- `font-sans` → body text, descriptions, FAQ answers, footer paragraphs

---

## DESIGN SYSTEM

```css
:root {
  /* Backgrounds */
  --bg:         #080808;   /* page base */
  --bg-1:       #0F0F0F;   /* cards, panels */
  --bg-2:       #141414;   /* hover states, inputs */
  --bg-3:       #1A1A1A;   /* active/selected */

  /* Text */
  --t-1:        #EDEDED;   /* primary — headings, important labels */
  --t-2:        #888888;   /* secondary — body text, descriptions */
  --t-3:        #444444;   /* tertiary — disabled, timestamps, dividers */

  /* Accent — ONE accent, used sparingly */
  --accent:     #E8E0D0;   /* warm off-white — NOT lime, NOT neon */
  /* The accent is barely-off-white. This creates a paper-on-dark-room feeling. */
  /* Use ONLY on: active nav state, hovered links, one CTA button border */

  /* Borders */
  --border:     rgba(255,255,255,0.06);
  --border-2:   rgba(255,255,255,0.10);

  /* Radius — MINIMAL. Research tools don't have bubbly corners */
  --r:          6px;    /* base radius */
  --r-lg:       10px;   /* cards */
  --r-pill:     999px;  /* tags only */
}
```

**Spacing system:** Use multiples of 8px everywhere. Section padding: 96px vertical. Content max-width: 1080px centered. Text columns: 600px max for readability.

**Visual character of this site:**
Dense but breathable. Lots of whitespace between sections, but within sections the type sits close together like a research paper. Think NYT Technical Docs or Anthropic's own Claude.ai UI — not an agency portfolio.

---

## TECH STACK

```
Next.js 15 (App Router)
TypeScript
Tailwind CSS v4
geist (npm package) for all three font families
Framer Motion — whileInView reveals ONLY. No other motion.
shadcn/ui — Accordion (FAQ only)
```

**Install:**
```bash
npx create-next-app@latest vivacity --typescript --tailwind --app
npm install geist framer-motion
npx shadcn@latest init
npx shadcn@latest add accordion
```

---

## FILE STRUCTURE

```
app/
  layout.tsx              ← fonts, global metadata
  page.tsx                ← landing (all sections)
  docs/
    layout.tsx            ← docs shell (sidebar + content)
    page.tsx              ← Introduction doc
    [slug]/page.tsx       ← other doc pages
  pricing/page.tsx        ← standalone pricing (mirrors landing section)

components/
  Nav.tsx
  Hero.tsx
  Marquee.tsx
  AppShot.tsx             ← the dashboard mockup
  ExampleVideos.tsx
  Pricing.tsx
  FAQ.tsx
  Footer.tsx
  docs/
    Sidebar.tsx
    DocContent.tsx

lib/
  fonts.ts
  data/
    faq.ts
    pricing.ts
    marquee-items.ts
    docs-nav.ts
```

---

## PAGE 1 — LANDING (`app/page.tsx`)

---

### NAV (`components/Nav.tsx`)

Height: 48px. Position: fixed top. Full width.
Background: `rgba(8,8,8,0.92)` with `backdrop-blur-sm`.
Bottom border: `1px solid var(--border)`.

**Left:**
Logo mark: `V.`
Font: `font-pixel`, 20px, color `var(--t-1)`.
No link styling. Just the text.

**Right (nav links):**
Font: `font-mono`, 12px, color `var(--t-2)`.
Links: `docs` · `pricing` · `examples` · `sign in`
Separator between links: a single `·` character in `var(--t-3)`.
On hover: color transitions to `var(--t-1)` in 120ms. No underline. No border.

One button — `start building` — no border, no background, no padding except `px-3 py-1`.
On hover: `var(--t-1)` text, and a `1px solid var(--border-2)` border appears with `border-radius: var(--r)`.
This is the quietest possible CTA button.

---

### HERO (`components/Hero.tsx`)

Min-height: `100vh`. Display: flex, column, centered vertically and horizontally.
Background: `var(--bg)`. Zero decoration. No gradients.

**Eyebrow label:**
`VIVACITY / 0.1 BETA`
Font: `font-mono`, 11px, color `var(--t-3)`, letter-spacing 0.12em.
Margin-bottom: 24px.

**Main heading:**
```
Mathematical
reasoning,
made visible.
```
Font: `font-pixel`, `clamp(48px, 7vw, 88px)`, color `var(--t-1)`, line-height 0.95, letter-spacing -0.02em.
Left-aligned. NOT centered.
This heading should feel like a research paper title dropped into a terminal.

**Body line (one sentence max):**
`Type a concept. Get a Manim animation. Built for researchers, not presentations.`
Font: `font-sans`, 15px, color `var(--t-2)`, max-width 480px.
Margin-top: 20px.

**Input block:**
Margin-top: 40px. Max-width: 580px.

The input:
```
Background:   var(--bg-1)
Border:       1px solid var(--border)
Border-radius: var(--r)        ← NOT rounded-2xl. Just 6px.
Padding:      14px 16px
Font:         font-mono, 14px, var(--t-2)
Placeholder:  "e.g. prove the divergence theorem geometrically"
Placeholder color: var(--t-3)
```

On focus:
```
border-color: var(--border-2)
outline: none
```

Below the input, one line:
`⌘ + Enter to generate  ·  no account needed`
Font: `font-mono`, 11px, color `var(--t-3)`.
This is NOT a CTA. It's a keyboard hint. Keep it small.

**Framer Motion on hero text only:**
Stagger each line of the heading (3 lines) with:
```tsx
initial={{ opacity: 0, y: 12 }}
animate={{ opacity: 1, y: 0 }}
transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: index * 0.08 }}
```

---

### MARQUEE (`components/Marquee.tsx`)

Sits immediately below the hero. Height: 64px. Border-top and border-bottom: `1px solid var(--border)`.
Background: `var(--bg)`.

A single horizontal row of institution names.
Font: `font-mono`, 11px, letter-spacing 0.1em, uppercase, color `var(--t-3)`.
Each item separated by `·` (centered dot, spaced with padding).

Items:
```
IIT BOMBAY · IIT DELHI · IIT KANPUR · IIT MADRAS · IIT ROORKEE · NIT TRICHY · BITS PILANI
· ALLEN · RESONANCE · FIITJEE · MIT · STANFORD · OXFORD · ETH ZURICH · NUS · TORONTO ·
```

**Pure CSS marquee:**
```css
@keyframes scroll {
  0%   { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
.track {
  display: flex;
  width: max-content;
  animation: scroll 40s linear infinite;
}
.track:hover { animation-play-state: paused; }

/* fade both edges */
.marquee-wrapper {
  mask-image: linear-gradient(
    to right,
    transparent 0%,
    black 8%,
    black 92%,
    transparent 100%
  );
}
```

Duplicate the items once inside `.track` so the loop is seamless.

Above the marquee track, NO label. The marquee speaks for itself.

---

### APP SHOT (`components/AppShot.tsx`)

This section shows what the tool looks like from the inside.

Section heading: `The interface.`
Font: `font-pixel`, 36px, color `var(--t-1)`, left-aligned.
Below: one line in `font-mono` 12px `var(--t-3)`: `SPLIT SCREEN · PROMPT LEFT · OUTPUT RIGHT`

A browser-frame mockup. Max-width: 960px. Centered.

**Browser chrome:**
Height: 36px. Background: `var(--bg-2)`. Border-radius: `var(--r-lg) var(--r-lg) 0 0`.
Left: three circles (6px each), colors `#3A3A3A`, `#3A3A3A`, `#3A3A3A` — all same color, dead grey. We're not decorating.
Center: URL bar — `font-mono`, 11px, `var(--t-3)`, text: `app.vivacity.dev/workspace`
URL bar: background `var(--bg-3)`, border-radius `var(--r)`, padding `px-3 py-1`, width 240px, centered.

**Main panel** (below chrome):
Border: `1px solid var(--border)`. Border-radius: `0 0 var(--r-lg) var(--r-lg)`.
No border-top (chrome handles it).

Two-column split inside:

**Left panel — Prompt / History (38% width):**
Background: `var(--bg-1)`.
Border-right: `1px solid var(--border)`.

Top bar inside panel:
- `font-mono` 10px `var(--t-3)` label: `WORKSPACE`
- A small `+` button in `var(--t-3)` right-aligned.

Below: a thread of messages, top-to-bottom:

```
User message:
  "Explain Stokes' theorem with a visual proof"
  Background: var(--bg-2), border-radius: var(--r), padding: 10px 12px
  font-sans 13px var(--t-2), right-aligned in panel

System response:
  "Generating · 3 scenes · ~45s"
  font-mono 12px var(--t-3), left-aligned, no background

Completed response:
  "Done. 4 scenes rendered."
  font-mono 12px var(--t-1), left-aligned
  Below it, a small tag: [2:14] in font-mono 10px var(--t-3) with border 1px solid var(--border)
```

Bottom of left panel: the input field (same style as hero input but 13px, height 40px).

**Right panel — Video output (62% width):**
Background: `var(--bg)`.

A 16:9 aspect-ratio container for the video preview.
Background: `#050505`.
Border: `1px solid var(--border)`.
Border-radius: `var(--r)`.

Inside the 16:9 area — a minimal SVG mathematics visualization:
```svg
<!-- Draw this as an inline SVG — coordinate plane showing Stokes' theorem -->
<!-- White thin axes lines (strokeWidth 0.5, opacity 0.4) -->
<!-- A curved surface in the center — simple bezier paths in var(--t-3) stroke, no fill -->
<!-- A boundary curve along the edge — dashed line, var(--t-1) opacity 0.6 -->
<!-- Two labels: ∂S (boundary) and S (surface) in GeistMono 10px var(--t-2) -->
<!-- Keep it sparse — 5-6 paths maximum -->
```

Below the video area:
A progress scrubber: thin track (2px, `var(--bg-3)`), progress fill (2px, `var(--t-1)`), at 45% position.
Border-radius on track: `var(--r-pill)`.
Right of scrubber: `01:02 / 02:14` in `font-mono` 10px `var(--t-3)`.

Bottom of right panel: three controls in `font-mono` 11px `var(--t-3)`:
`export  ·  share  ·  regenerate`

**Scroll reveal for entire AppShot section:**
```tsx
<motion.div
  initial={{ opacity: 0, y: 32 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: "-60px" }}
  transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
>
```

---

### EXAMPLE VIDEOS (`components/ExampleVideos.tsx`)

Section heading: `What it makes.`
Font: `font-pixel` 36px, left-aligned.

Below heading: `font-mono` 12px `var(--t-3)`: `SAMPLE OUTPUTS · 4 EXAMPLES`

A horizontal-scroll row. `overflow-x: auto`. `scrollbar-width: none` (hide scrollbar).
Gap between cards: 16px.

**Each card** (width: 260px, fixed):

```
Background: var(--bg-1)
Border: 1px solid var(--border)
Border-radius: var(--r-lg)
Overflow: hidden
```

Top area — 16:9 video thumbnail:
```
Background: var(--bg)
No placeholder image — use a CSS-generated visualization:
  Simple line drawing (SVG) of what that topic looks like.
  Centered play button: 32px circle, border 1px solid var(--border-2),
  background transparent, white right-triangle inside (10px)
```

Bottom area — metadata:
```
Padding: 12px
Title:    font-pixel 14px var(--t-1) — the topic name
Duration: font-mono 11px var(--t-3)
Tag:      font-mono 10px var(--t-3), border 1px solid var(--border),
          border-radius var(--r-pill), padding 2px 8px
```

4 cards:
1. `Divergence Theorem` · 2:14 · [vector calculus]
2. `Eigenvalue Decomposition` · 1:58 · [linear algebra]
3. `Maxwell's Equations` · 3:02 · [electrodynamics]
4. `Fourier Transform` · 2:31 · [signal theory]

Each card on hover:
```
border-color: var(--border-2)
transform: translateY(-2px)
transition: all 180ms ease
```

**SVG per card — keep these minimal:**
- Card 1: vector field arrows (small grid of arrows, 8px each, `var(--t-3)`)
- Card 2: a 2x2 matrix notation with one highlighted eigenvalue row
- Card 3: E and B field wave lines, perpendicular, simple sine curves
- Card 4: a time-domain spike on left, frequency bars on right, arrow between them

---

### PRICING (`components/Pricing.tsx`)

Section heading: `Pricing.`
Font: `font-pixel` 36px, left-aligned.
Below: `font-mono` 12px `var(--t-3)`: `FREE TO START · SCALE WHEN YOU NEED`

Layout: 5 columns desktop, 1 column mobile.
Each card: `border: 1px solid var(--border)`, `border-radius: var(--r-lg)`, `background: var(--bg-1)`, `padding: 24px`.

**Card anatomy:**
- Tier name: `font-pixel` 14px `var(--t-2)` uppercase
- Price: `font-pixel` 28px `var(--t-1)`
- Period: `font-mono` 11px `var(--t-3)` (inline after price or below)
- Divider: `1px solid var(--border)` — 12px margin above and below
- Feature list: `font-mono` 12px `var(--t-2)`, line-height 2.2, no bullets, no icons

**Feature items just sit as lines of text.** No checkmarks. No icons. Researchers read. They don't need icons to communicate "included."

**Tiers:**

Tier 1 — `FREE`
`₹0` / mo
```
5 renders per month
720p output
Watermarked export
Community forum
```
Button: `font-mono` 12px, `var(--t-3)`, text `start free`, border `1px solid var(--border)`, border-radius `var(--r)`, padding `8px 16px`. On hover: border `var(--border-2)`, text `var(--t-2)`.

Tier 2 — `SUPPORTED`
`₹0` / mo
```
15 renders per month
Ad-supported export
1080p output
Email support
```
Button: same ghost style.

Tier 3 — `STUDENT`
`₹329` / mo
```
50 renders per month
No watermark
1080p + download
Priority queue
```
Button: same ghost style.

Tier 4 — `PRO` ← HIGHLIGHTED CARD
```
Background: var(--bg-2)
Border: 1px solid var(--border-2)
```
Above card name, a tag: `MOST USED`
Tag style: `font-mono` 10px `var(--t-3)`, border `1px solid var(--border)`, border-radius `var(--r-pill)`, padding `2px 8px`.

`₹1,579` / mo
```
200 renders per month
4K export
Custom voice model
API access
Priority support
```
Button: `font-mono` 12px, color `var(--bg)`, background `var(--t-1)`, border-radius `var(--r)`, padding `8px 16px`. On hover: `opacity: 0.88`.

Tier 5 — `API`
`usage-based`
```
No monthly cap
Billed post-cycle
Webhook support
SLA guarantee
Dedicated contact
```
Button: `font-mono` 12px, `var(--t-3)`, text `contact us`, border `1px solid var(--border)`, same ghost style.

---

### FAQ (`components/FAQ.tsx`)

Section heading: `Questions.`
Font: `font-pixel` 36px, left-aligned.

Max-width: 680px. Not centered — left-aligned within the content column.

Use `shadcn/ui` Accordion, single type (one open at a time).

**Override accordion styles:**
```css
[data-slot="accordion-item"] {
  border: none;
  border-bottom: 1px solid var(--border);
}
[data-slot="accordion-trigger"] {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--t-2);
  padding: 16px 0;
  letter-spacing: 0;
}
[data-slot="accordion-trigger"]:hover {
  color: var(--t-1);
}
[data-slot="accordion-trigger"][data-state="open"] {
  color: var(--t-1);
}
[data-slot="accordion-content"] {
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--t-3);
  line-height: 1.8;
  padding-bottom: 16px;
}
```

**8 FAQ items:**

```
Q: How does Vivacity generate videos?
A: A prompt enters the pipeline, interpreted by a language model that maps intent to Manim
   scene primitives. The Code2Video framework writes valid Python/Manim code,
   reviewed by a critic model before rendering. WhisperX syncs the voiceover
   to animation keyframes at the phoneme level. End-to-end: under 90 seconds.

Q: What subjects does it cover?
A: Mathematics and physics at undergraduate and competitive exam level.
   Chemistry and computer science are in active development.

Q: Can I use this for teaching at scale?
A: Yes. The Pro and API tiers support bulk generation and LMS embedding.
   Contact us for institutional pricing if you're a coaching institute or university.

Q: Is the output downloadable?
A: Student tier and above produce clean downloads at 1080p or 4K.
   Free and Supported tiers produce watermarked exports.

Q: What is the API tier?
A: Programmatic access to the full pipeline. Billed after your usage cycle.
   No monthly cap. Designed for platforms integrating generated content at scale.

Q: How precise is the audio-visual sync?
A: WhisperX aligns voiceover to animation at phoneme-level precision.
   This is Vivacity's primary technical differentiator — the sync is
   mathematically computed, not approximated.

Q: Is my content private?
A: Paid tier outputs are private by default.
   Free tier outputs may be used to improve the model unless you opt out.

Q: How is this different from using Manim manually?
A: Manim requires Python expertise and hours of per-video coding.
   Vivacity abstracts prompt → scene graph → render → audio sync → export.
   The delta is roughly 4 hours versus 90 seconds for an equivalent 2-minute video.
```

---

### FOOTER (`components/Footer.tsx`)

Border-top: `1px solid var(--border)`. Padding: `64px 0`. Background: `var(--bg)`.

Four columns in a row (desktop), stacked on mobile:

**Col 1 — Brand:**
`V.` in `font-pixel` 20px `var(--t-1)`.
Below: `font-sans` 13px `var(--t-3)`:
`AI video generation for mathematical reasoning.`
Below: `font-mono` 11px `var(--t-3)`:
`© 2025 PaXus Labs.`

**Col 2 — Product:**
Label: `PRODUCT` — `font-mono` 10px `var(--t-3)` uppercase, letter-spacing 0.12em. Margin-bottom 16px.
Links in `font-mono` 12px `var(--t-3)`, hover `var(--t-2)`, line-height 2.4:
```
features
pricing
examples
api
```

**Col 3 — Docs:**
Label: `DOCS`
Links:
```
introduction
quick start
api reference
changelog
```

**Col 4 — Company:**
Label: `COMPANY`
Links:
```
about
research
blog
contact
```

**Wordmark — full width, very bottom:**
Below all columns: 32px margin.
Then the text: `vivacity`
Font: `font-pixel`, `clamp(72px, 14vw, 180px)`, color `rgba(237,237,237,0.03)`.
Letter-spacing: -0.03em.
This is purely atmospheric. No link. Overflow hidden on the container.

---

## PAGE 2 — DOCS (`app/docs/layout.tsx` + `page.tsx`)

---

### DOCS LAYOUT (`app/docs/layout.tsx`)

Two-column. Sidebar: 220px fixed left. Content: fluid right.
No top nav — the docs have their own minimal header.

**Docs header (full width):**
Height: 40px. Border-bottom `1px solid var(--border)`.
Left: `V. docs` — `font-pixel` 14px `var(--t-1)`.
Right: `font-mono` 11px `var(--t-3)` — `v0.1 · vivacity.dev`

**Sidebar (`components/docs/Sidebar.tsx`):**
Position: sticky, top 40px (below header). Height: calc(100vh - 40px). Overflow-y: auto.
Border-right: `1px solid var(--border)`. Background: `var(--bg)`.
Padding: `24px 16px`.
Scrollbar: hidden (`scrollbar-width: none`).

Nav structure — flat tree with section headers:

```
GETTING STARTED           ← font-mono 10px var(--t-3) uppercase, letter-spacing 0.1em
                            NOT a link. Section label only.

  Introduction            ← font-mono 12px var(--t-2), padding 6px 0 6px 8px
  Quick Start
  Architecture

CORE CONCEPTS

  The Prompt Engine
  Manim Pipeline
  Audio Sync (WhisperX)
  Code2Video Framework

API REFERENCE

  Authentication
  POST /generate
  GET /status/:id
  Webhooks
  Error Codes

GUIDES

  Embedding Videos
  Bulk Generation
  Custom Voice
  Rate Limits
```

Active item style:
```css
color: var(--t-1);
background: var(--bg-2);
border-radius: var(--r);
border-left: 2px solid var(--t-1);
padding-left: 10px;
```

Hover style:
```css
color: var(--t-1);
background: var(--bg-1);
border-radius: var(--r);
transition: 120ms ease;
```

**Content area:**
Background: `var(--bg)`. Padding: `40px 64px`. Max-width: 700px.

**Content typography (override prose defaults):**
```css
h1: font-pixel 32px var(--t-1), margin-bottom 8px, line-height 1.1
h2: font-pixel 20px var(--t-1), margin-top 48px, margin-bottom 12px
h3: font-mono 14px var(--t-2), margin-top 32px, text-transform uppercase, letter-spacing 0.06em
p:  font-sans 14px var(--t-2), line-height 1.85, max-width 600px
a:  var(--t-1), text-decoration underline, text-underline-offset 3px, on hover opacity 0.7
li: font-sans 14px var(--t-2), line-height 2

code (inline):
  font-mono 13px
  background: var(--bg-2)
  border: 1px solid var(--border)
  border-radius: var(--r)
  padding: 2px 6px
  color: var(--accent)   ← this is the ONE place accent color appears in docs

pre > code (block):
  font-mono 13px
  background: var(--bg-1)
  border: 1px solid var(--border)
  border-radius: var(--r-lg)
  padding: 20px 24px
  display: block
  overflow-x: auto
  Language label: font-mono 10px var(--t-3), top-right corner, absolute positioned

blockquote:
  border-left: 2px solid var(--border-2)
  padding-left: 16px
  color: var(--t-3)
  font-style: italic
```

**Introduction page content (hardcode this):**

```markdown
# Introduction

Vivacity is a video generation engine for mathematical and scientific concepts.
It accepts a text prompt and returns a Manim-rendered animation with
phoneme-level synchronized audio. The process takes under 90 seconds end-to-end.

## What it is

Vivacity is not a presentation tool.
It generates precise, programmatic animations — the kind you would otherwise spend
4 hours writing in Python. The output is a video file, not a slide.

## Who it's for

- Researchers who need to visualize a proof or derivation
- Educators preparing concept explanations for JEE / NEET / undergraduate coursework
- Platforms integrating AI-generated educational content via API

## The pipeline

Four stages run sequentially per request:

### 1. Prompt interpretation

Your input is parsed by a language model (Claude Opus) that extracts
mathematical intent and maps it to a scene graph: objects, motions, and timing.

### 2. Code generation

The Code2Video framework translates the scene graph to executable Python/Manim code.
A Gemini-based critic reviews the code for validity before it reaches the renderer.

### 3. Rendering

The Manim engine renders your scene frame-by-frame on a GPU cluster.
Render time is typically 30–60 seconds for a 2-minute video.

### 4. Audio-visual sync

WhisperX aligns the AI-generated voiceover to animation keyframes at the phoneme level.
This is Vivacity's primary technical differentiator.

## What Vivacity is not

Vivacity is not a slide-to-video converter.
It does not take PDFs or images as input.
It generates animations from first principles on every request.

## Quick example

```python
# Using the Python SDK
import vivacity

client = vivacity.Client(api_key="...")

video = client.generate(
    prompt="Prove the Cauchy-Schwarz inequality geometrically",
    duration_hint=120,   # target seconds
    resolution="1080p",
)

print(video.url)  # → https://cdn.vivacity.dev/v/abc123.mp4
```
```

---

## PAGE 3 — PRICING (`app/pricing/page.tsx`)

Same as the Pricing section on the landing page but as a standalone page.

Add one thing at the top: a breadcrumb in `font-mono` 12px `var(--t-3)`:
`vivacity / pricing`

And at the bottom, one extra row: a comparison table.

**Comparison table:**
No borders on rows — only border-bottom `1px solid var(--border)` on each row.
Header row: `font-mono` 11px `var(--t-3)` uppercase.
Feature rows: `font-mono` 12px `var(--t-2)`.
Values: `font-mono` 12px — use plain text: `yes` / `no` / `—` (em dash for N/A).

```
Feature           Free   Supported  Student   Pro    API
Monthly renders     5       15        50      200     ∞
Resolution        720p    1080p     1080p     4K      4K
Watermark          yes     yes       no       no      no
Download           no      no        yes      yes     yes
API access         no      no        no       limited  yes
Custom voice       no      no        no       yes     yes
Support          forum   email    email    priority   SLA
```

---

## MOTION SPEC — COMPLETE LIST

Only these 3 animation patterns are permitted. No others.

**1. Hero heading stagger (Framer Motion, animate on mount):**
```tsx
const lines = ["Mathematical", "reasoning,", "made visible."]
lines.map((line, i) => (
  <motion.span
    key={i}
    initial={{ opacity: 0, y: 14 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: i * 0.08 }}
    style={{ display: "block" }}
  >
    {line}
  </motion.span>
))
```

**2. Section scroll reveal (Framer Motion, whileInView):**
```tsx
<motion.div
  initial={{ opacity: 0, y: 20 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: "-80px" }}
  transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
>
```
Apply to: AppShot container, ExampleVideos section, Pricing grid.

**3. Marquee (pure CSS, no JS):**
Already defined above. No JS. No library.

**NOTHING ELSE MOVES.** No nav animations. No card hovers beyond color/border.
No spinning logos. No gradient shifts. No floating anything.

---

## BUILD PHASES

```
Phase 1 — Foundation
  - Next.js 15 + TS + Tailwind v4 setup
  - Install geist, framer-motion, shadcn
  - globals.css with full CSS variable system
  - layout.tsx with all three font variables registered
  - CLAUDE.md with these rules pinned

Phase 2 — Shell
  - Nav.tsx (static, no animation)
  - Footer.tsx (static, including ghost wordmark)
  - Wire app/page.tsx

Phase 3 — Hero (most important)
  - Hero.tsx with three-line pixel heading
  - Input field
  - Framer Motion stagger
  - Test at 375px

Phase 4 — Marquee
  - Pure CSS. Test loop is seamless.
  - Test fade masks.

Phase 5 — AppShot
  - Browser chrome
  - Two-panel split
  - Inline SVG for the math visualization
  - Scroll reveal

Phase 6 — Example Videos
  - Horizontal scroll row
  - 4 cards with SVG thumbnails
  - Hover states

Phase 7 — Pricing
  - 5-column grid
  - Pro card highlighted
  - Responsive stack on mobile

Phase 8 — FAQ
  - shadcn Accordion
  - Custom CSS overrides
  - 8 items

Phase 9 — Docs
  - Sidebar with full nav tree
  - Content area with typography overrides
  - Introduction page hardcoded

Phase 10 — QA
  [ ] Zero emojis anywhere
  [ ] font-pixel used only for logo + headings
  [ ] font-mono used for all labels, metadata, code, nav
  [ ] font-sans used for body text only
  [ ] No color outside the design system variables
  [ ] No border-radius above var(--r-lg) anywhere except tags (var(--r-pill))
  [ ] Marquee loops seamlessly, both edges fade
  [ ] AppShot SVG renders correctly
  [ ] Docs sidebar sticky positioning correct
  [ ] prefers-reduced-motion removes all animation
  [ ] Mobile at 375px: heading wraps correctly, input full-width
  [ ] Pricing table visible on mobile (horizontal scroll)
  [ ] No <form> tags — all handlers via onClick/onChange
  [ ] All Lorem Ipsum replaced with real copy
```

---

## WHAT SUCCESS LOOKS LIKE

Open `localhost:3000` and it should feel like:
- A research tool someone runs in a dark terminal session
- Dense, precise, quiet
- The GeistPixelSquare headings are the only bold aesthetic move — everything else is restrained
- Someone who uses Linear or Cursor or Perplexity would feel at home immediately
- A student at IIT or MIT would screenshot the input box and share it

It should NOT feel like:
- A startup landing page trying to raise a seed round
- Something built on a template
- A product someone made in an afternoon

---

*Built by PaXus Labs. vivacity.dev.*
