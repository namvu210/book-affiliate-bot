# videogen module

## Current state (validated)

- Veo 3 image-to-video works via `google-genai` SDK (same API key as Gemini)
- Mock provider works for testing without API calls
- Full pipeline: storyboard → TTS → video clips → stitch → final mp4

## Providers

| Provider | Status | Model ID |
|----------|--------|----------|
| Veo 3 | Working | `veo-3.0-generate-001` |
| Veo 3 Fast | Not tested | `veo-3.0-fast-generate-001` |
| Mock (ffmpeg zoompan) | Working | N/A |
| Seedance 2.0 (Fal.ai) | Not built | `bytedance/seedance-2.0/reference-to-video` |
| Kling | Stub only | N/A |

## Cost analysis (per 16s ad creative)

| Approach | Cost |
|----------|------|
| PIL-only (storyboard grid + effects) | ~1,500đ |
| Veo 3 Fast × 2 clips | ~10,500đ |
| Veo 3 × 2 clips | ~21,000đ |
| Seedance 2.0 (Fal.ai) | ~99,000-122,000đ |

## TODO

- [ ] Test Veo 3 Fast quality (`veo-3.0-fast-generate-001`)
- [ ] Test Veo 3 with storyboard grid image as input (does it follow frame sequence?)
- [ ] Build storyboard grid image generator (Gemini: 3x2 grid, consistent characters/product)
- [ ] Build Seedance 2.0 provider (Fal.ai) for when budget allows
- [ ] Add tiered cost strategy: product price → auto-select provider
- [ ] PIL storyboard pipeline for < 5,000đ budget (animated stills with story)
