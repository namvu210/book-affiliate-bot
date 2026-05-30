# PRD: Movie Ad Generator

## Problem Statement

Current product review videos are narration-over-slideshow format — functional but not engaging enough for competitive short-form platforms (TikTok, Reels). Users need cinematic 16-second product ads that tell a short story featuring KOL characters, creating emotional connection and higher engagement rates.

## Solution

A new "Movie Ad" flow that generates short cinematic product ads using:
1. **Gemini Image** — multi-reference scene generation (KOL photos + product → scene image)
2. **Veo 3** — image-to-video (scene image as start frame → 8s motion clip)
3. **2 × 8s clips** = 16 seconds of body content + intro/outro

## User Stories

### US-1: KOL Management
> As a content creator, I want to save KOL character profiles with multi-angle reference photos so I can reuse them across multiple ad projects.

**Acceptance criteria:**
- Upload 3-6 turnaround images per KOL (front, side, back angles on solid background)
- Name and describe each KOL ("Cô gái trẻ năng động, tóc dài, mặc áo thun trắng")
- List, view, and delete KOL profiles
- Reference images served for preview

### US-2: Screenplay Generation
> As a content creator, I want AI to generate a 2-scene creative screenplay for my product ad, so I get an engaging story without manual scriptwriting.

**Acceptance criteria:**
- Input: product info + selected KOL(s) + optional story template
- Output: 2-scene screenplay with visual description, shot type, motion prompt, dialogue per scene
- Can choose from preset story styles (competition, discovery, transformation, unboxing)
- Can manually edit any field before proceeding
- Can regenerate screenplay with different parameters

### US-3: Scene Image Generation
> As a content creator, I want to see AI-generated scene images that maintain my KOL's visual identity alongside the product, before committing to video generation.

**Acceptance criteria:**
- Each scene produces a preview image using KOL reference photos + product images
- KOL character identity is visually consistent across scenes
- Can regenerate individual scene images
- Product is visibly placed per screenplay's product_placement instruction

### US-4: Video Clip Generation
> As a content creator, I want to generate 8-second video clips from my approved scene images, with option to use draft quality (fast) or final quality.

**Acceptance criteria:**
- Generate Veo 3 clip from scene image + motion prompt
- Optional dialogue adds character speech ("She says '...'")
- Draft mode (Veo Omni Flash) for quick preview
- Final mode (Veo 3) for production quality
- Can regenerate clips individually

### US-5: Assembly & Export
> As a content creator, I want to combine my clips with narration, music, and intro/outro into a final publishable video.

**Acceptance criteria:**
- Concat 2 clips + optional intro/outro
- Add TTS narration (Edge TTS / ElevenLabs)
- Add background music
- Handle narration/video duration mismatch with user-chosen resolution
- Export final MP4 for download or direct publish

### US-6: Duration Mismatch Resolution
> As a content creator, when my narration doesn't match the 16s video duration, I want clear options to resolve it without losing quality.

**Acceptance criteria:**
- Detect mismatch (narration too long or too short vs. video)
- Offer options: speed adjust, music bridge, extend outro, regenerate narration
- Preview result before finalizing

---

## Technical Specification

### Architecture

```
movie/
├── __init__.py
├── models.py          # KOLProfile, MovieScene, MovieScreenplay, MovieProject
├── screenplay.py      # Gemini screenplay generation
├── scene_image.py     # Multi-ref image generation
├── clip.py            # Veo 3 image-to-video
├── assemble.py        # FFmpeg concat + audio mix
└── project.py         # Project CRUD, state persistence

kol_manager.py         # KOL profile CRUD (filesystem)
routers/movie.py       # REST API (/api/movie/ prefix)
templates/movie.html   # Dedicated page
static/js/movie/*.js   # Frontend modules
prompts/movie_*.yaml   # Prompt templates
```

### Data Models

```python
@dataclass
class KOLProfile:
    id: str                       # uuid4
    name: str
    description: str
    turnaround_images: list[str]  # file paths
    created_at: str               # ISO datetime

@dataclass
class MovieScene:
    scene_number: int             # 1 or 2
    visual_description: str
    shot_type: str                # wide | medium | close-up
    motion_prompt: str            # Veo 3 motion instruction
    dialogue: str | None
    duration_s: int = 8

@dataclass
class MovieScreenplay:
    title: str
    story_hook: str
    scenes: list[MovieScene]      # exactly 2
    product_placement: str
    kol_ids: list[str]

@dataclass
class MovieProject:
    id: str                       # config.make_ts()
    product_title: str
    product_url: str | None
    product_images: list[str]
    screenplay: MovieScreenplay | None
    scene_images: list[str]
    video_clips: list[str]
    final_video: str | None
    narration_path: str | None
    status: str                   # draft | generating | complete | error
    created_at: str
```

### API Contract

**Base:** `/api/movie/`

| Method | Path | Description | Input | Output |
|--------|------|-------------|-------|--------|
| GET | `/kol/` | List KOL profiles | — | `{profiles: KOLProfile[]}` |
| POST | `/kol/` | Create KOL | multipart: name, description, images[] | `KOLProfile` |
| DELETE | `/kol/{id}` | Delete KOL | — | `{ok: true}` |
| GET | `/kol/{id}/images` | Get reference URLs | — | `{images: string[]}` |
| POST | `/project/create` | New project | JSON: product_title, product_url, product_images, kol_ids | `MovieProject` |
| GET | `/project/{id}` | Get project | — | `MovieProject` |
| GET | `/projects/` | List projects | — | `{projects: MovieProject[]}` |
| POST | `/project/{id}/screenplay` | Generate screenplay | JSON: story_style? | `MovieScreenplay` |
| PUT | `/project/{id}/screenplay` | Edit screenplay | JSON: MovieScreenplay | `MovieScreenplay` |
| POST | `/project/{id}/scene-image/{n}` | Gen scene image | — | `{image_url: string}` |
| POST | `/project/{id}/scene-image/{n}/regen` | Regen scene image | — | `{image_url: string}` |
| POST | `/project/{id}/clip/{n}` | Gen video clip | JSON: model? | `{video_url: string}` |
| POST | `/project/{id}/clip/{n}/regen` | Regen clip | JSON: model? | `{video_url: string}` |
| POST | `/project/{id}/narration` | Gen TTS | JSON: voice_type, voice_id, speed | `{audio_url: string, duration_s: float}` |
| POST | `/project/{id}/assemble` | Final assembly | JSON: mismatch_strategy?, music_path?, intro?, outro? | `{video_url: string}` |
| GET | `/project/{id}/preview` | Get all assets | — | `{scene_images, clips, narration, screenplay}` |

### Storage

- KOL profiles: `kol_profiles/{uuid}/profile.json` + `ref_*.jpg`
- Project state: `movie_projects/{id}.json`
- Generated assets: `output/{id}_scene1.png`, `output/{id}_clip1.mp4`, `output/{id}_movie.mp4`

### Key Technical Decisions

1. **Separate page, not tab** — Movie Ad is a complex wizard flow; cramming into existing SPA would bloat it
2. **Project-based state** — Each movie ad is a "project" with persistent state, allowing resume after browser close
3. **Step-by-step with preview** — User approves each step (screenplay → images → clips → assembly) before proceeding; no blind pipeline
4. **Dual Veo models** — Veo Omni Flash for drafts (fast iteration), Veo 3 for final (quality)
5. **Filesystem storage** — Consistent with existing `batch_jobs/` pattern, no database needed

### Dependencies

- `google-genai` SDK (already in requirements.txt) — Gemini Image + Veo 3
- `ffmpeg` (system dependency, already required) — video concat + audio mix
- Existing modules: `reviewer._get_client()`, `imagegen._resize_for_input()`, `videogen/veo.py`, `tts.py`, `config.py`

---

## UI Wireframes (Text)

### Page Layout
```
┌─────────────────────────────────────────┐
│ 🎬 Movie Ad Generator                  │
├─────────────────────────────────────────┤
│ [Step 1] [Step 2] [Step 3] ...  progress│
├─────────────────────────────────────────┤
│                                         │
│   Step content area                     │
│   (changes per step)                    │
│                                         │
├─────────────────────────────────────────┤
│ [← Back]              [Next Step →]     │
└─────────────────────────────────────────┘
```

### Step 3: Screenplay
```
┌─────────────────────────────────────────┐
│ 📝 Screenplay                           │
│                                         │
│ Story style: [Competition ▾] [🎲 Regen] │
│                                         │
│ ┌─ Scene 1 ─────────────────────────┐  │
│ │ Visual: [editable textarea]        │  │
│ │ Shot: [wide ▾]                     │  │
│ │ Motion: [editable textarea]        │  │
│ │ Dialogue: [optional input]         │  │
│ └────────────────────────────────────┘  │
│                                         │
│ ┌─ Scene 2 ─────────────────────────┐  │
│ │ Visual: [editable textarea]        │  │
│ │ Shot: [close-up ▾]                 │  │
│ │ Motion: [editable textarea]        │  │
│ │ Dialogue: [optional input]         │  │
│ └────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### Step 4: Scene Images
```
┌─────────────────────────────────────────┐
│ 🖼️ Scene Images                        │
│                                         │
│ ┌──────────────┐  ┌──────────────┐     │
│ │              │  │              │     │
│ │  Scene 1     │  │  Scene 2     │     │
│ │  [image]     │  │  [image]     │     │
│ │              │  │              │     │
│ │ [🔄 Regen]  │  │ [🔄 Regen]  │     │
│ └──────────────┘  └──────────────┘     │
│                                         │
│ Status: ✅ Scene 1 ready | ⏳ Scene 2   │
└─────────────────────────────────────────┘
```

---

## Success Metrics

1. **End-to-end completion rate** — % of started projects that produce a final video
2. **Character identity consistency** — visual similarity score across scenes (manual review initially)
3. **Generation time** — total wall clock from screenplay to final video (target: < 10 min)
4. **User iteration count** — avg regenerations per step (lower = better prompts)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Gemini Image loses character identity | Scenes look like different people | Use 4-6 turnaround angles, test prompt ordering |
| Veo 3 rejects generated images | Clip generation fails | Fallback to Veo Omni Flash; test upfront |
| Long generation times | Poor UX, user abandons | Show progress, allow background generation |
| Narration/video mismatch | Awkward final product | Multiple resolution strategies, user picks |
| API rate limits / quota | Generation blocked mid-project | Retry logic, state persistence for resume |

---

## Out of Scope (v1)

- Multi-KOL in same scene (v1 = single KOL per project)
- Storyboard grid input to Veo 3 (test later as optimization)
- Auto-publish from movie flow (manual download first)
- Batch movie generation
- Custom intro/outro templates
