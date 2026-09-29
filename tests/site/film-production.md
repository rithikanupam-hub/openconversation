# LingoSync product concept film — 27 September 2026

Audience: founders and delivery leads at small agencies and consultancies with recurring cross-language client-project meetings.
Value: hear feedback, follow decisions and stay involved without asking a bilingual colleague to relay every point.
Look: graphite, ivory, burnt orange; fine grid, tactile material, restrained signal curves; editorial typography matched to the existing product.
Delivery: 30 seconds, 16:9, 1280×720, 24fps, silent, captioned. Original schematic UI; not a recording of working integrations.

| Time | Beat | Visible action | Status |
|---|---|---|---|
| 0–6s | Good ideas. Across languages. | Orange signal filaments; editorial title settles in; animated waveform | European language vision; Italian → English prototype |
| 6–12s | Your client call. Hear the detail. | Four-person call illustration and translated sentence | Google Meet routing planned |
| 12–18s | In the room. In the conversation. | Laptop on meeting table; waveform; headphone listening label | Microphone prototype, room pilot evaluation |
| 18–24s | Different languages. Shared momentum. | Four listening-language nodes connected to a shared center | Shared sessions planned |
| 24–30s | Your expertise. Their language. | Signal material returns; pilot proposition and fit CTA | Proposed $149 / 30 days / 4 listener-hours |

Transitions: eased title entrances/exits; constant grid and signal geometry; restrained motion. No fabricated live speech, performance timing, customer logos or testimonials. No private test audio.

Paid generation: user authorized $3 maximum, aiming around $1. One fal Wan 2.2 A14B text-to-video job, 81 frames at 16 source fps, 720p. Pricing endpoint returned $0.08 per generated second; expected cost $0.405. Request ID: 01a0e41a-3f68-7021-a4c3-b374fa0a8cd8. No automatic retries. Generation completed successfully; output retained as tests/site/abstract-source.mp4. Final billing settlement is not independently verified. Keys are read outside the repository and never included in site files.

The generated asset supplies abstract material only. Exact type, meeting illustrations, disclosures and captions are composed locally using the existing Swift/CoreGraphics renderer and FFmpeg.

Requested taste/brag/drag/Recordly skills were not installed in the searched local skill locations. Used the available video-creator skill and existing native film renderer; no claim that missing tools ran.

## Re-render — 27 September 2026 (premium transitions pass)

Rewrote `tests/site/render-film.swift` to use five distinct eased transitions (orange iris wipe, diagonal slide with motion-blur trails, staggered venetian-blind reveal, zoom-through crossfade, horizontal split-shutter), continuous parallax/floating/waveform motion, a vignette and fixed-seed film grain, and added a new sixth scene: a language-routing beat cycling "Italiano → English" through Deutsch, Français, Svenska, Dansk, Español, Nederlands, Português → English and finally English → Italiano, via a vertical slot-roll, with the note "Italian → English tested today · other directions in validation". Same retained plate (`tests/site/abstract-source.mp4`), no new paid generation — $0. Runtime grew from 30s to 36s (864 frames @ 24fps) to fit the new beat; output is 1280×720 H.264, ~4.0 MB. Poster and captions (`film.vtt`) regenerated to match the new scene timings.

## Restyle — 27 September 2026 (light "paper" rebrand, matches site COPY.md)

Rewrote `tests/site/render-film.swift` again to drop the dark olive/ink look entirely and match the site's new illoca-style direction: paper `#f5f3ec` background with a faint 24px grid (`#e6e3d6`), ink `#24271f` text, one orange `#fc602f` accent, subtle grain, and illustrated device/laptop/meeting panels sitting inside a bordered "stage" rectangle (1px ink border, small radius). Registered and used the real brand fonts from `tests/site/fonts/` via `CTFontManagerRegisterFontsForURL(scope: .process)` — PostScript names printed and verified at render time (`InstrumentSans-Regular/Medium/SemiBold`, `InstrumentSerif-Italic`, `JetBrainsMono-Regular/Medium`, `Caveat-SemiBold`); dropped Helvetica/Georgia entirely. The dark abstract provider plate (`tests/site/abstract-source.mp4`) is no longer decoded or referenced anywhere — no paid generation, $0.

Replaced the five mismatched transitions with one signature family: a stage push (content slides left/right with easeInOutCubic, slight 0.97→1 scale, short orange progress line under the stage) for scene-to-scene cuts, plus a single iris wipe reserved for the final logo reveal. Headline/accent/label text now rises in via an independent masked line-by-line reveal (staggered ~80ms per line, easeOutExpo) so panel transitions and sentences never splice mid-word.

Rebuilt all 6 scenes to match `frontend/site/COPY.md` exactly — titles, orange accent half-lines and labels — including the laptop/meeting card with the Italian line "Possiamo condividere l'idea venerdì.", a phrase-by-phrase flip-chip translation scene, a headphones scene with "We can share the idea on Friday." and the consent note, the existing 9-pair language slot-roll (recolored light/dark), and a clean centered-asterisk finale ("lingosync ✳ / Still connected."). Added Caveat hand notes with wobbly hand-drawn arrows ("just talk normally", "phrase by phrase, not word by word", "only with their consent").

Output: 36.0s exactly, 1280×720, 24fps, H.264 yuv420p, faststart, crf 21, no audio, 795 KB (well under the 6 MB budget). Verified by extracting ~20 frames (every scene hold, every transition midpoint, and each of the 9 language-pair labels individually) and reading them — confirmed accented characters (ì, ç, ñ, ê) render correctly, no clipped/overlapping/off-frame text, and no leftover dark/olive/Helvetica material. Poster (`film-poster.jpg`) regenerated from a fully-settled scene-1 frame; captions (`film.vtt`) rewritten to 6 cues of 6s each, matching the new scene timings, with cue text set to each scene's on-screen title + accent line.
