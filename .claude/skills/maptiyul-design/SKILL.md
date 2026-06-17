---
name: maptiyul-design
description: MapTiyul's "Israeli Warmth" visual design language — palette, type, motion, and component rules. Use whenever building, restyling, or adding UI to index.html so new work matches the house style instead of defaulting to generic AI aesthetics.
---

# MapTiyul — Israeli Warmth design language

The look is **sun-baked, grounded, regional**: Jerusalem-stone and sand tones,
terracotta as the action color, Mediterranean blue for identity, olive for
"nature/active". Warm, mature, with a real sense of place — *not* the cool
teal-on-white glass generic it replaced. All tokens live in `:root` in
`index.html`; prefer the variables over raw hexes.

## Palette (CSS custom properties)

| Token | Value | Use |
|-------|-------|-----|
| `--accent` | `#c1603d` | terracotta — primary action, active state, links, focus |
| `--accent-d` | `#a84e2e` | darker terracotta — pressed/active text, shadows |
| `--sky` | `#1f5a6b` | Mediterranean blue — the **MapTiyul wordmark**, secondary |
| `--olive` | `#6b7340` | nature/"open" green-olive |
| `--amber` | `#cf8a2e` | warm highlight |
| `--plum` | `#8a5a6b` | muted clay-plum |
| `--ink` | `#2c241a` | warm near-black text |
| `--muted` | `#8a7a60` | warm grey-brown secondary text |
| `--panel` | `#fffdf8` | warm white card surface |
| `--panel-2` | `#fbf4e6` | cream — tag/chip fills, hover |
| `--line` | `#e6dbc2` | warm hairline borders |
| `--glass*` | warm-white translucent | frosted sidebar/panels |
| page bg | stone gradient `#efe6d4 → #e3d7bf` | behind map/panels |

**Region colors** (kept in both `:root --r-*` and JS `REGION_META`, must stay in sync):
צפון = olive `#6b7340` · מרכז = sky `#1f5a6b` · ירושלים = plum `#8a5a6b` · דרום = amber `#cf8a2e`.

The GPS "you are here" dot stays **blue** (`#2f6fd0`) — location is a universal
convention, intentionally exempt from the warm palette.

## Type

- Body: **Assistant** (Hebrew + Latin).
- Wordmark "MapTiyul": **Secular One** (single weight, rounded Hebrew display) in `--sky`.
- Popup/card titles: **Heebo 700**.
- Keep weights *light*: prefer 500 for pills/tags/quick-buttons, 600 for badges /
  nav labels / taglines, 700 for titles. Avoid 800/900 — the user finds heavy
  weights "too fat".

## Motion & shadows

- Warm shadows: `0 12px 34px rgba(120,80,40,.16)`; small `rgba(120,80,40,.12)`.
- Gradient accents (FAB, trip planner CTAs, numbered stops, route line) use
  `linear-gradient(135deg, var(--accent), var(--sky))` — terracotta→Mediterranean.
- Hover lifts: `translateY(-1px)` + shadow. Respect `prefers-reduced-motion`.

## Brand buttons (don't bury logos)

Waze and Google Maps nav buttons stay **warm-white cards** with their real brand
SVGs (cyan Waze logo + cyan text; multicolor Google pin + dark text). Never put a
brand logo on a colored fill — it kills recognizability.

## Do / Don't

- **Do** reach for `var(--accent)` / `var(--sky)` before inventing a color.
- **Do** keep RTL logical props in mind (`inline-start` = right).
- **Don't** reintroduce cool teal `#1f7a8c` or purple `#7c3aed` (the old palette).
- **Don't** crank font weights or use pure `#fff` panels — warm white `--panel`.
