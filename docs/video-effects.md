# Video Effects, Styles & Settings

## Motion Effects (Hiệu ứng)

Controls how images animate during display and transition between each other.

### Base Motion (applied during image display)

| Effect | Description |
|--------|-------------|
| `ken_burns` | Slow zoom + pan across image (classic documentary style) |
| `slide_lr` | Horizontal pan left-to-right |
| `slide_ud` | Vertical pan top-to-bottom |
| `bounce_zoom` | Pulsing zoom in/out (rhythmic) |
| `zoom_center` | Steady zoom into center |
| `parallax` | Foreground/background move at different speeds (2.5D depth) |
| `shake` | Random camera shake |
| `rotate_tilt` | Gentle rotation oscillation |
| `crossfade` | Blend between current and next image |
| `none` | Static image, no motion |

### Transition Effects (applied between image switches)

| Effect | Description |
|--------|-------------|
| `whip_pan` | Horizontal motion blur swipe (mimics fast camera pan) |
| `glitch_trans` | RGB channel split + horizontal slice displacement |
| `shutter` | White flash burst between images |
| `zoom_through` | Zoom into current image → zoom out of next (fly-through) |
| `split_reveal` | Image splits horizontally from center, revealing next underneath |
| `velocity` | Variable timing (first/last slow, middle rapid-fire) + zoom-through transitions |
| `circle_iris` | Circle wipe expanding from center |
| `slip` | Image slides down revealing next behind |
| `scroll_h` | Horizontal scroll — img1 exits left, img2 enters right |
| `scroll_v` | Vertical scroll — img1 exits up, img2 enters below |
| `rotate_wipe` | Rotating pie-slice mask reveal |
| `zoom_in` | img2 grows from center point over img1 |
| `shooting_frame` | Frame border shrinks in revealing next image |
| `countdown` | Flash to black then reveal (countdown feel) |
| `switch_on` | TV switch on — horizontal line expands to full |
| `switch_off` | TV switch off — shrinks to line then reveals next |

> Transition effects use `ken_burns` as base motion during display, with the transition firing during the 4-frame (~0.17s) image switch.

### Beat Sync (automatic)

When background music is present, a white flash (25% opacity) + 5% zoom burst is applied on detected beat frames. This works on top of any effect. Beat timestamps are cached per music file in `music/.beats/`.

## Visual Styles (Phong cách)

Applied as a post-processing layer on top of the motion effect.

| Style | Description |
|-------|-------------|
| `none` | No style filter |
| `vignette` | Dark edges, bright center (cinematic) |
| `soft_glow` | Gaussian blur blend (dreamy) |
| `sepia` | Warm brown tone (vintage) |
| `grayscale` | Black and white |
| `color_tint` | Warm orange overlay (15%) |
| `color_pop` | Only red tones in color, rest grayscale |
| `saturation` | Boosted color saturation (1.8×) |
| `contrast` | Increased contrast (1.5×) |
| `flash` | Periodic white flash pulses |
| `glitch` | Random horizontal slice displacement + RGB offset |
| `pixelate_reveal` | Starts pixelated, gradually reveals full image |
| `before_after` | Split-screen wipe comparing two images |
| **Light / Particle** | |
| `halo` | Animated circular halo glow at top |
| `scanning_light` | Horizontal light bar scanning down the frame |
| `light_leak` | Animated warm light leak from corner |
| `sparkles` | White sparkle particles scattered across frame |
| `gold_sparkles` | Gold-toned sparkle particles |
| `snowfall` | Falling snow particles with drift |
| `glitter_bomb` | Multi-color glitter burst |
| `starlights` | 4-point star shapes scattered |
| `neon_glow` | Bright areas emit colored neon glow |
| `shockwave` | Expanding circular ring from center |
| `star_power` | Cross-shaped star highlights |
| `rainbow_heart` | Multi-color heart shapes |
| `pink_hearts` | Pink floating hearts |
| **Color / Noise** | |
| `chromatic` | RGB channel split (color fringe) |
| `club_mood` | Cycling RGB color overlay (nightclub) |
| `cyberpunk` | High contrast + purple tint + scanlines |
| `negative` | Inverted colors |
| `black_noise` | Dark film grain noise |
| `film_grain` | Classic film grain overlay |
| `x_signal` | VHS signal tear + color offset |
| `flash_2` | Rapid double flash pulses |
| `black_flash` | Periodic black flash pulses |
| `camera_focus` | Center sharp, edges blurred (rack focus) |

## Subtitle Styles

| Style | Description |
|-------|-------------|
| `tiktok` | Word-by-word highlight with colored glow border (default) |
| `karaoke` | Highlighted word in accent color, rest in gray |
| `news` | Full-width black bar background |
| `minimal` | Simple white text, no background |

## Video Settings

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| Motion effect | see above | `ken_burns` | Image animation style |
| Visual style | see above | `none` | Post-processing filter |
| Subtitle style | see above | `tiktok` | Word highlight style |
| Aspect ratio | 9:16, 1:1, 16:9 | 9:16 | Video dimensions |
| Music volume | 0-50% | 15% | Background music level |
| Zoom ratio | 5-100% | 15% | Intensity of zoom effects |
| Highlight color | Any hex | #FFD700 (gold) | Subtitle highlight color |
| Show intro | on/off | on | Hook text slide at start (2s) |
| Show outro | on/off | on | CTA text slide at end (2s) |
| Voice speed | 100-200% | 175% | TTS playback speed |
| Music genre | auto | corporate | Background music category |

## Default Configuration

```
Motion:    ken_burns
Style:     none
Subtitle:  tiktok (word-by-word highlight)
Music:     corporate (auto-selected, 15% volume)
Speed:     1.75×
Intro/Outro: on
```

## Trending Rating (TikTok/Reels 2025-2026)

How well each effect matches current viral content patterns:

### Motion Effects

| Effect | Trending | Notes |
|--------|----------|-------|
| `ken_burns` | ⭐⭐⭐ | Safe/universal, but feels "slideshow" — not scroll-stopping |
| `whip_pan` | ⭐⭐⭐⭐⭐ | #1 transition on TikTok product videos — fast, energetic |
| `velocity` | ⭐⭐⭐⭐⭐ | Matches "velocity edit" trend — variable pacing is very 2025-2026 |
| `glitch_trans` | ⭐⭐⭐⭐ | Edgy/youth appeal, great for fashion/tech |
| `shutter` | ⭐⭐⭐⭐ | Clean, punchy — works for any product category |
| `zoom_through` | ⭐⭐⭐⭐ | Premium feel, good for luxury/beauty products |
| `split_reveal` | ⭐⭐⭐ | Modern but less common on TikTok — more CapCut/YouTube |
| `crossfade` | ⭐⭐ | Feels dated — associated with older video editors |
| `slide_lr/ud` | ⭐⭐ | Basic, no energy — fine for calm/wellness products |
| `bounce_zoom` | ⭐⭐⭐ | Good with music, but can feel repetitive |
| `parallax` | ⭐⭐⭐ | Premium but subtle — viewers may not notice |

### Visual Styles

| Style | Trending | Notes |
|-------|----------|-------|
| `none` | ⭐⭐⭐⭐ | Clean/natural is trending — "iPhone photo" aesthetic |
| `vignette` | ⭐⭐⭐ | Subtle cinematic touch, doesn't distract |
| `soft_glow` | ⭐⭐⭐ | Good for beauty/skincare products |
| `color_pop` | ⭐⭐⭐⭐ | Eye-catching in feed — product stands out |
| `sepia/grayscale` | ⭐⭐ | Niche — only for specific aesthetic accounts |
| `saturation` | ⭐⭐⭐ | Vibrant colors perform well in feed |

### Subtitle Styles

| Style | Trending | Notes |
|-------|----------|-------|
| `tiktok` | ⭐⭐⭐⭐⭐ | Standard for all viral content — viewers expect this |
| `karaoke` | ⭐⭐⭐⭐ | Popular for music/lyric videos |
| `news` | ⭐⭐ | Formal — not matching casual product content |
| `minimal` | ⭐⭐⭐ | Clean but less engaging — no highlight = less retention |

### Recommended Presets by Product Category

| Category | Effect | Style | Why |
|----------|--------|-------|-----|
| Fashion/Clothing | `whip_pan` | `none` | Fast energy, clean product colors |
| Beauty/Skincare | `zoom_through` | `soft_glow` | Premium feel, dreamy aesthetic |
| Tech/Electronics | `glitch_trans` | `none` | Edgy, modern, matches tech vibe |
| Kids/Toys | `shutter` | `saturation` | Playful, colorful, energetic |
| Home/Lifestyle | `velocity` | `vignette` | Dynamic pacing, warm cinematic |
| Books/Education | `ken_burns` | `none` | Calm, focused, not distracting |

## Output Specs

| Spec | Value |
|------|-------|
| Resolution | 1080×1920 (9:16), 1080×1080 (1:1), 1920×1080 (16:9) |
| FPS | 24 |
| Video codec | H.264 (libx264) |
| Audio codec | AAC 192kbps |
| Container | MP4 |
