# VocalGrid marketing site

A standalone, dependency-free landing page matching the existing orange translator UI. Uses the current working brand and links to the deployed Modal prototype. No interpreter, GPU, microphone or external script is started by this page.

Preview from the repository root:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory frontend/site
```

Open http://127.0.0.1:4173. The existing FastAPI/Modal static mount can also serve `/static/site/index.html` after these assets are included in a deployment. This change does not replace the app root or deploy anything.

Checks:

```sh
node tests/site/check.cjs
node --check frontend/site/site.js
```

The retained fal plate is `tests/site/abstract-source.mp4`; the renderer extracts frames automatically.

Re-render the silent 36-second product concept film on macOS (Swift, CoreGraphics and FFmpeg):

```sh
swift -module-cache-path /tmp/lingosync-swift-cache tests/site/render-film.swift
```

Film: `assets/conversation-film.mp4`, 1280×720, 24fps, H.264, no audio, with matching poster and captions. It shows the meeting scenarios and a live language-routing preview as labelled product concepts, not fabricated live translation recordings. Private podcast/test recordings are not used.

The fit-check dialog assesses the initial language/setup and creates a downloadable text brief locally. It submits no leads, books no meetings and collects no payment. Connect an approved booking/lead destination before using it as a public acquisition funnel. The $149 offer is the proposed guided pilot, subject to configuration validation.

Validation completed: Chrome desktop and 390/360px mobile layouts; no horizontal overflow at 360px; fit outcomes, download, Escape dismissal, motion pause, FAQ and video playback. Native reduced-motion CSS and JS preference handling are included. All content remains visible if JavaScript is unavailable. No speech models or interpreter GPU resources were launched during website development. One paid fal background-generation request was authorized for the film; see tests/site/film-production.md for the cost record.

September 27 enhancement: textured surfaces and scroll-linked diagram motion; three scenario cards; European language positioning with tested/roadmap distinctions; recognition WER and latency from 14 recorded-input simulation clips. Metrics are development results, not service guarantees. German, French and shared-session fit requests correctly remain subject to validation.

September 27 (later): hero device cycles through European language pairs (Italian, German, French, Swedish, Danish, Spanish, Dutch and Portuguese to English; English to Italian, German and French) with a per-letter roll transition. Tap ▶ or a language tag to skip; hovering pauses; it stops when motion is paused. Only Italian → English is labelled as tested. Also added: one-time multilingual intro curtain, sticky glass nav with scroll progress, word-by-word headline reveals, hero tilt/glare/glow following the pointer, scroll parallax, magnetic buttons, card spotlights, counting benchmark figures, an interactive greeting in the language section and a bouncing footer word. SEO: descriptive title and meta description, Open Graph/Twitter cards (`assets/og-image.jpg`), JSON-LD, manifest, apple-touch icon and `robots.txt`. Canonical URL, absolute og:url/og:image and a sitemap still need the production domain. Fixed an older override that made the hero illustration and the sticky story panel `position:relative`.

September 27 (v3, illoca direction): after reviewing Awwwards Sites of the Day (illoca by Unseen Studio, Cerebrium, Moto Finance, L.I.S.A., Aspen Search, Realevate), the site was rebuilt on illoca's system: cream grid paper, floating pill nav, Instrument Sans/Serif, JetBrains Mono labels and Caveat handwritten notes (self-hosted in `assets/fonts`, OFL, no Google requests), tile buttons with a sliding fill, framed "stage" panels, a pinned three-step story (Listen → Translate → Hear) with a hold-to-play sample, Cerebrium-style scroll-filled statement text, and three-tier pricing (pilot $149 proposed; Team and Organisation without prices until pricing is agreed). Gimmicky effects from v2 (magnetic buttons, cursor spotlights, bouncing footer, greeting chips) were removed. All copy comes from `COPY.md`, which the film also uses. The previous version is not kept in the repo.

## Audience motion and language editions

The handwritten hero rotates through agencies/consultancies, independent consultants,
import/export teams, sharing ideas, and exploratory teaching use cases. It pauses on
hover/focus, when offscreen, when the tab is hidden, and with Pause motion or reduced-motion
preferences. There is no extra control or description in the hero; a left-to-right handwritten reveal preserves its original spacing. Audience claims remain separate from tested
product capabilities.

Local editions: `/` (English), `/it/`, `/de/`, `/fr/`. These are localized landing pages
with the same design, use cases, pilot scope and benchmark limitations, not complete copies
of every interactive English section. Film and fit assessment remain in English, labelled
before navigation. Copy is maintained in the `locale-copy` JSON block in `COPY.md`.

```sh
python3 tests/site/build-locales.py
python3 tests/site/check-locales.py
node tests/site/check.cjs
```

No production domain has been selected. The owner wants local review and a naming decision
first. Nothing is deployed. Once a domain is chosen, build with
`python3 tests/site/build-locales.py --base-url https://YOUR-FINAL-DOMAIN`
to produce self-canonicals, reciprocal en/it/de/fr and x-default links, sitemap.xml and
robots.txt. Language codes are region-neutral; do not use a made-up EU hreflang region.
No IP/language redirects, external translation services, cookies or browser-only SEO text.
Guidance: https://developers.google.com/search/docs/specialty/international/localized-versions

Native-language editorial review is recommended before public launch. No claims of EU-only
hosting or legal compliance are implied by translating the marketing pages.

## Screenshot launch checklist

`trust.html` contains linked local-review drafts for privacy, terms, refunds, cookie/storage
information, data requests and business details. It is noindex and is not a published legal
policy. Footer links appear in all four editions (English drafts explicitly identified).
See `tests/site/launch-checklist.md` for all 20 screenshot items and unresolved launch work.

No marketing cookies/storage or trackers; the decorative intro now uses ephemeral page state.
Added original font licence notices. Inactive sample scenes are inert for keyboard navigation;
small muted text and accent text contrast improved. Historical benchmarks are labelled as
belonging to the earlier Nemotron pipeline. Fit buttons do not pretend to submit a waitlist.

Run `node tests/site/check-trust.cjs` alongside existing checks. Browser review on 28 September:
policy desktop/mobile (390px, no horizontal overflow), section anchors, footer links.
No backend restart, cloud deploy, customer-data deletion or paid session was performed.
