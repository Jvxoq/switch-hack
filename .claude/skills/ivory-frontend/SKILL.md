---
name: ivory-frontend
description: "Use when building, changing, or reviewing any frontend UI that should follow the Ivory Editorial design system — new pages, landing pages, article/launch pages, components, layouts, forms, tables, benchmark charts, dark mode, black-and-white sites, or design-token setup. Encodes Ivory Editorial (warm ivory paper, near-black ink, serif display over a clean sans UI, a single clay accent, pill controls, hairline 1px rules, a measured word-reveal and drift motion budget) plus its Mono theme (the same layout and motion in pure black-and-white dark mode) as a non-negotiable token contract, plus a UX rule layer (access, interaction, forms, motion discipline, layout, navigation, charts) and production frontend standards for React/TypeScript: structure, state, accessibility, forms, data fetching, performance, and a per-frame motion QA harness. Load BEFORE writing UI code, not after a review finds the design drifted."
---

# Ivory Frontend

Build UI that reads like a well-edited magazine launch page: warm paper, dark ink, serif headlines,
quiet sans UI, one warm accent, and motion that arrives softly and then gets out of the way.

This skill has two halves:

1. **The design system** — Ivory Editorial. A fixed token contract. Never improvise values.
   It ships in two themes that share every layout, type, and motion rule:
   - **Ivory** (default) — warm light paper, clay accent.
   - **Mono** — pure black-and-white dark mode. Pick it when the user asks for b/w, monochrome,
     black-and-white, or dark mode. See §3b.
2. **The engineering standards** — how to structure, fetch, validate, and ship the code that renders those tokens.

Read Part 1 before writing any markup. Read Part 2 before deciding where files go or how state flows.

> **Brand boundary.** This system captures a *style* (palette, type roles, rhythm, motion). It does not
> include any company's logo, wordmark, product names, proprietary fonts, or photography. Never paste
> in a real company's name, logo, or imagery to make a page "look right". Use the open-licence fonts
> below and the user's own brand and content.

---

## Design values

Eight rules decide every trade-off here. When two rules clash, the higher one wins.

1. **Calm is a budget, not a style.** One idea on screen at a time. Every animation spends from that budget.
2. **Readable on the first frame.** Content never waits for motion, a font, or a fetch to become legible.
3. **Respond in 100ms.** A press, a toggle, or a route answers the hand before the eye starts to doubt.
4. **No surprise physics.** Native scroll stays native. No hijack, no lock, no easing the user did not ask for.
5. **Soft in, quiet out.** Entrances are slow and few. Exits are shorter and plain.
6. **Motion explains, never decorates.** If a move shows no cause and effect, it goes.
7. **Verify, do not assume.** Smoothness is measured per frame, not judged by feel on a fast laptop.
8. **Respect the body.** Reduced motion, keyboard, zoom, slow devices, and small screens are the default case.

---

# Part 1 · Ivory Editorial design system

## AI Build Instructions

> **Read this section before writing any code.** The rules below are non-negotiable. Every value used in
> the UI must come from this file's token block — never substitute, approximate, or invent new colors,
> fonts, radii, shadows, durations, or easings. If a value is missing, ask the user before adding one.

> **One source of truth.** Values are written in exactly two places and they must match:
> the `yaml` block below (the spec you read) and `styles/globals.css` (the file you ship).
> Every other section in this document refers to roles by name and never repeats a hex, a radius,
> or a duration. If you change a value, change it in both places in the same commit. A third copy
> is a bug waiting to drift.

### 1 · Your role

You are building UI for a project that has adopted **Ivory Editorial** as its design system. Treat this
file as the single source of truth. Translate the user's product requirements into components and pages
that look like they were designed by the same person who authored this file.

### 2 · Token compliance

- Pull every color, font family, radius, shadow, spacing, duration, and easing from the token block below.
- Use semantic roles (`ink`, `canvas`, `muted`, `accent`) — never hard-code hex values that bypass the system.
- Declare tokens once as CSS variables in the global stylesheet and reference them everywhere downstream.
- Add the Google Fonts `<link>` from the Typography section to `<head>` before any component renders.

### 3 · Source tokens

```yaml
name: "Ivory Editorial"
description: "Warm ivory paper, near-black ink, serif headlines over a quiet sans UI, one clay accent."
tags: [editorial, warm, serif, minimal, light-with-dark-hero]
colors:
  ink:            "#141413"   # primary text, borders, table rules
  ink-soft:       "#3d3d3a"   # secondary headings on light
  muted:          "#5e5d59"   # captions, figcaptions, meta (AA on canvas)
  faint:          "#87867f"   # disabled text and decorative marks only. Never a label users must read or click.
  hairline:       "#d1cfc5"   # dividers, subtle cell fill, neutral highlight
  canvas:         "#faf9f5"   # page background
  surface:        "#f0eee6"   # cards, wells, alt sections
  surface-strong: "#e8e6dc"   # pressed/hover fill on light
  night:          "#0f0f0e"   # dark hero / footer stage
  night-raised:   "#262624"   # pill buttons + chips on dark
  night-ink:      "#faf9f5"   # text on dark
  night-eyebrow:  "#f2ede4"   # eyebrow + TOC text on dark hero
  accent:         "#d97757"   # clay — rules, highlight borders, chart focus. Never body text.
  accent-strong:  "#c6613f"   # clay for interactive fills / large text
  accent-tint:    "#ebc9b7"   # highlighted table column / selected row fill
  on-accent-tint: "#141413"   # text on accent-tint
  night-hover:    "#30302e"   # hover fill for on-dark pills
  focus:          "#2c84db"   # focus ring only
  error:          "#bf4d43"
  # supporting illustration palette — charts and spot illustrations only, never UI chrome
  olive: "#788c5d"
  sky:   "#6a9bcc"
  fig:   "#c46686"
  oat:   "#e3dacc"
  cactus: "#bcd1ca"
  heather: "#cbcadb"
typography:
  display: "Source Serif 4"   # stand-in for a warm editorial serif
  body:    "Source Serif 4"   # long-form article prose
  ui:      "DM Sans"          # nav, buttons, tabs, tables, labels, eyebrows, captions
  mono:    "JetBrains Mono"   # code, TOC numerals "(1)", data ids
radius:
  none: 0px      # tables, article media, section blocks
  xs:   4px      # small chips, inline code wells
  sm:   8px      # icon buttons ("corner-small")
  md:   12px     # inputs, small cards
  lg:   16px     # cards, popovers, cookie/consent sheets
  full: 999px    # pill buttons ("corner-full")
buttons:
  primary:     # pill on light
    background: "#141413"
    color: "#faf9f5"
    border: none
    shape: pill
    padding: 8px 16px
    font: ui / 400 / 13px / 0.01em
  secondary:   # pill on light, quiet
    background: "#f0eee6"
    color: "#141413"
    border: 1px solid #d1cfc5
    shape: pill
    padding: 8px 16px
    font: ui / 400 / 13px / 0.01em
  on-dark:     # pill on the night hero / nav over hero
    background: "#262624"
    color: "#faf9f5"
    border: none
    shape: pill
    padding: 8px 12px 8px 16px   # trailing chevron variant
    font: ui / 400 / 13px / 0.01em
  ghost:       # inline text action
    background: transparent
    color: "#141413"
    border: none
    padding: 0
    font: ui / 500 / inherit
    hover: underline (1px, offset 0.18em)
  icon:
    background: "#262624" on dark, "#f0eee6" on light
    shape: small (8px radius)
    padding: 8px
    size: 32px
  shared:      # every variant, no exceptions
    min-height: 44px
    hit-area: 44x44 minimum, even when the visual box is 32px
    press: scale .98 for 100ms
    focus: 2px solid focus, offset 2px
charts:
  variant: flat-ruled       # 1px ink rules, no gridline noise
  highlight: one            # the subject column/series in accent-tint with accent border
  neutral_highlight: "#d1cfc5"   # a competitor's best score
fonts_url: "https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=JetBrains+Mono:wght@400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap"
dependencies: ["lucide-react"]
```

### 3b · Mono theme (black-and-white dark mode)

Mono is the same system with the color layer swapped for pure neutral grays on black. Layout, type
scale, fonts, radii, spacing, components, and **all motion** stay exactly as written for Ivory. Only the
tokens below change. Every role keeps its name, so components never branch on theme.

```yaml
theme: mono
color-scheme: dark
colors:
  ink:            "#ededed"   # primary text, table rules, primary pill fill
  ink-soft:       "#d4d4d4"   # primary pill hover, secondary headings
  muted:          "#a3a3a3"   # captions, meta
  faint:          "#737373"   # disabled text and decorative marks only. Never a label users must read or click.
  hairline:       "#2e2e2e"   # dividers, input borders, neutral highlight
  canvas:         "#0a0a0a"   # page background
  surface:        "#141414"   # cards, wells, alt sections
  surface-strong: "#1f1f1f"   # hover / pressed fill
  night:          "#000000"   # hero + footer stage (one step darker than canvas)
  night-raised:   "#1f1f1f"   # pills on hero
  night-hover:    "#2a2a2a"
  night-ink:      "#fafafa"
  night-eyebrow:  "#e5e5e5"
  accent:         "#fafafa"   # white replaces clay: subject-column border, chart focus
  accent-strong:  "#ffffff"   # link hover
  accent-tint:    "#fafafa"   # subject column is INVERTED: white fill …
  on-accent-tint: "#0a0a0a"   # … with black text
  focus:          "#ffffff"   # white focus ring
  error:          "#ef6b5f"   # the only non-gray value. Always paired with error text.
  # supporting illustration palette → grays only: #fafafa #a3a3a3 #737373 #3a3a3a
```

Mono-only rules:

- **No hue anywhere** except `error`. Charts use ink shades, with the subject series in `accent` (white)
  and the rest in `#737373` / `#3a3a3a`.
- **Images go grayscale.** Hero media and figures get `filter: grayscale(1) contrast(1.08)`. Do it in
  CSS, not by editing the assets, so Ivory can still show color.
- **The subject column inverts.** White fill, black bold text, 1px white outline. That inversion is the
  b/w version of the clay highlight. A competitor's best score uses `hairline` fill, same as Ivory.
- **The hero still reads as a separate stage.** `night` (#000) sits one step under `canvas` (#0a0a0a).
  Add a `1px solid var(--hairline)` bottom border on the hero so the edge holds.
- **Shadows barely show on black.** Popovers and modals use `level-1` border + the mono shadow values
  in Elevation.
- **Selection:** `::selection { background: var(--ink); color: var(--canvas); }`.

#### Choosing and switching themes

- Set the theme on `<html data-theme="ivory|mono">`. Never on a subtree.
- A site can ship **one** theme (a b/w brand uses Mono only), or **both** as light/dark mode.
- When shipping both, default to the OS setting (`prefers-color-scheme: dark` → Mono), let the user
  override with a toggle, and save the choice in `localStorage` under `theme`.
- Set `data-theme` with a tiny inline script in `<head>`, before CSS paints, so the page never flashes
  the wrong theme (see Token wiring).
- The toggle is an **icon** button (lucide `sun` / `moon`), `aria-pressed`, `aria-label="Dark mode"`.
- Switching uses the **Theme crossfade** motion pattern on `html`: `background-color` and `color` over
  `320ms`. A theme flip is a response, not an entrance. Longer than ~350ms and the interface feels stuck.
  Under reduced motion the switch is instant.

### 4 · Page anatomy

Every marketing or launch page follows this shape. Do not invent a different skeleton.

1. **Nav** — 84px tall, transparent over the hero, wordmark left (the user's own), pill CTA + two
   32px icon buttons right. Turns `canvas` with ink text once the hero scrolls away.
2. **Night hero** — full-bleed `night` stage, at least 100svh. Optional collage or photo layers on the
   sides with slow drift motion. Centered stack: eyebrow (date or category) → display serif title →
   dotted-leader table of contents.
3. **Lede** — first paragraph in serif at 28/36, inside the reading column, on `canvas`.
4. **Article body** — serif 16–17px prose, 720px reading column, `h2` serif 32/40 regular, `h3` serif
   21px semibold.
5. **Data blocks** — tables and charts break out wider than the reading column (up to 1400px container).
6. **Footer** — `night` background, sans link columns in `night-ink`.

### 5 · Component recipes

Use these recipes verbatim when building the corresponding component.

#### Buttons

Five variants. Pick one — never blend variants or invent a sixth. Every variant is at least 44px tall.

- **Primary** — pill, bg `ink`, text `canvas`, padding `8px 16px`, ui 13px regular, `0.01em` tracking.
- **Secondary** — pill, bg `surface`, text `ink`, `1px solid hairline`, same type and padding.
- **On-dark** — pill, bg `night-raised`, text `night-ink`. Use on the hero and dark footer only.
- **Ghost** — text only, ui 500, underline on hover.
- **Icon** — 32×32 visual, 8px radius, padding 8px, 16px lucide icon. Pad the hit area to 44px.

Buttons are **sentence case**. Never uppercase a button. One primary per view.

#### Eyebrow

- ui font, 14px, weight 500, `uppercase`, letter-spacing `0.12em`, line-height 1.
- On the hero: color `night-eyebrow`. On light: color `muted`.

#### Hero title

- display serif, weight 400, `clamp(48px, 7vw, 96px)`, line-height 1.04, letter-spacing `-0.02em`.
- `font-optical-sizing: auto` (Source Serif 4 has an optical-size axis — let it pick the display cut).
- Color `night-ink`. Centered. Reveals word by word (see Motion).

#### Dotted-leader TOC

The signature hero detail. A centered list, max-width ~280px.

```html
<ol class="toc">
  <li><a href="#intro"><span class="n">(1)</span><span class="dots"></span><span>Introduction</span></a></li>
</ol>
```

- `a` is `display:flex; align-items:baseline; gap:6px`.
- `.n` — mono, 11px, `night-eyebrow`.
- `.dots` — `flex:1; border-bottom:1px dotted currentColor; opacity:.5; translate:0 -3px`.
- Label — serif 14px, right-aligned, `night-eyebrow`; hover goes to full `night-ink`.

#### Links in prose

- Color `ink`, underline always, `text-decoration-thickness: 0.08em`, `text-underline-offset: 0.18em`.
- Hover: color `accent-strong`, `transition: color 200ms ease-out`.

#### Tabs

Variant: **text tabs with a sliding indicator**.

- ui 15px, weight 600. Inactive `muted` (6.3:1, passes AA), active `ink`. No background, no border on the tab itself.
- One 2px `ink` indicator bar under the active tab. Animate it with **transform only**: measure the
  target tab, then set `transform: translateX(<x>) scaleX(<w / baseWidth>)` with
  `transform-origin: left`. `250ms` ease-out-quart.
- Never transition `width` or `left` here. They force layout on every frame and stutter on mid-range phones.
- Arrow keys move between tabs.

#### Tables (benchmarks, pricing, comparisons)

- ui 14px / 1.4, cells `padding: 10px 12px`, header weight 600, sub-label in `muted` 12–14px.
- **1px solid `ink` rules** on every cell. Zero radius. Background `canvas`.
- **Subject column** (the thing the page is about): cells filled `accent-tint`, text `on-accent-tint`,
  column outlined `1px solid accent`, bold values. In Mono this renders as an inverted white column.
- **Competitor's best** in a row: fill `hairline`, bold value. Never use red/green for "better/worse".
- Footnote markers are superscript numerals linking to a notes list. A targeted footnote flashes
  `surface` for 3s (see Motion).
- Wide tables scroll horizontally inside their own wrapper, never the page.

#### Cards

- Background `surface`, radius `lg` (16px), no shadow at rest, padding `24px` (md) or `48px` (lg feature).
- Hover on clickable cards: background → `surface-strong`, `200ms ease-in-out`. No lift, no shadow.

#### Blockquote / pull quote

- ui font (not serif) 16–17px, `ink`, curly quotes in the text. Attribution below in `muted` 14px,
  name in weight 600.
- No border bar, no italic, no giant quote glyph. Let whitespace frame it.

#### Figures

- Media zero radius, max-width 880px, max-height 560px.
- `figcaption` ui 14px / 1.4 in `muted`, 12px below the media.

#### Popover / consent sheet

- On dark: bg `night`, `1px solid night-raised`, radius `lg`, padding 24px.
- Buttons inside are full-width pills: one `on-dark` outline (1px `night-ink` border, transparent),
  one solid `canvas` with `ink` text.
- Enters with `opacity + transform 150ms`.

#### Typography pairings

- **Display (Source Serif 4)** — hero title, `h2`, `h3`, lede, article prose.
- **UI (DM Sans)** — nav, buttons, tabs, tables, eyebrows, captions, quotes, forms, footer.
- **Mono (JetBrains Mono)** — code, TOC numerals, commit hashes, model/version ids in data.

Never set UI chrome in the serif. Never set article prose in the sans.

### 6 · Hard constraints

Never do any of the following without explicit instruction from the user:

- Introduce a color, font, radius, shadow, duration, or easing that isn't declared above.
- In Ivory, use pure white `#ffffff` or pure black `#000000` as a page background. The paper is warm.
- In Mono, use any hue besides `error`, or warm grays from Ivory. Mono is neutral gray only.
- Write a component that checks the theme (`if (theme === "mono")`). Themes differ only in tokens.
- In Ivory, use `accent` for body text or small labels (2.96:1 on canvas — fails AA).
- Use the supporting illustration palette for UI chrome (buttons, nav, borders).
- Uppercase anything except eyebrows.
- Add drop shadows to cards or buttons. Separation comes from fills and 1px rules.
- Use gradients in UI. Gradients live only inside hero photography/illustration.
- Use emoji as icons. Use lucide, stroke 1.5, sized to the adjacent text.
- Add motion that is not one of the named patterns in the Motion section, or that ignores
  `prefers-reduced-motion`.
- Use spring physics, GSAP presets, or a custom curve. The Motion tokens are the only curves.
- Lock the page scroll, catch the wheel or touch gesture, or smooth-scroll for the user. Native scroll only.
- Remove or hide a focus ring, or put a feature on hover only. Hover features also work by focus and tap.
- Use `faint` or `accent` for text a user must read or click.
- Autoplay audio, or autoplay video with sound. A muted loop needs a pause control and a reason.
- Replace the system cursor, or hide and restyle the scrollbar until it is unusable.
- Play an entrance animation on a back navigation or a reload inside the same session.

### 7 · Before you finish — verify

- [ ] Every color used appears in the source token block. No literal hex outside `globals.css`.
- [ ] Headlines and prose use the serif. Every control, table, and label uses the sans.
- [ ] Buttons match one declared variant exactly (pill, 13px, sentence case, 44px minimum height).
- [ ] Radii come from `none / xs / sm / md / lg / full`. Tables and media are square.
- [ ] Text contrast is AA or better (see the table). `faint` and `accent` are never small body text.
- [ ] Every animation is a named Motion pattern and is wrapped in `prefers-reduced-motion: no-preference`.
- [ ] The motion budget holds: three entrance ideas on the site, one or two things moving at once.
- [ ] No entrance animation played on a return visit or a back navigation.
- [ ] Every screen looks right in each theme the project ships. Flip `data-theme` and check.
- [ ] No values were invented. If you needed something missing, you stopped and asked.
- [ ] The §8 UX rules pass. Nothing in §9 was pulled in.

### 8 · UX rules

These come from a review of UI/UX Pro Max (`nextlevelbuilder/ui-ux-pro-max-skill`, MIT), filtered so
they never change a token. They decide how the UI behaves, not how it looks. Groups are in priority
order. When two rules clash, the earlier group wins.

**A · Access (blocks shipping)**

- First element in `<body>` is a skip link ("Skip to content"). Sans 13px, hidden until focused, pill
  in `ink` on `canvas`. It targets `<main id="main" tabindex="-1">`.
- The focus ring appears instantly. Never fade it in, never delay it, never animate its offset. It is
  a safety signal, not a flourish.
- The sticky nav must never cover a focused control or an anchor target. Set
  `html { scroll-padding-top: calc(var(--nav-h) + var(--sp-16)); }`.
- Pointer targets are at least 44×44px, with at least 8px between neighbours.
- After a route change, move focus to `<main>` (or its `h1`) and update `document.title`.
- Never use color alone. Selected state gets weight or an indicator, errors get text plus an icon, the
  subject column is bold.
- The current nav item has `aria-current="page"` and a visible mark (`ink` text plus the 2px indicator).
- Anything that moves and carries content (carousel, ticker) has a pause button and stops under reduced
  motion. Ambient drift is decorative, so it is exempt.
- Toasts use `role="status"`, never take focus, and dismiss after 5s. Pause the timer on hover and
  focus. An error that needs action does not auto-dismiss.

**B · Interaction**

- Every clickable element has `cursor: pointer`. Buttons and links get `touch-action: manipulation`.
- Press feedback shows within 100ms (the `scale: .98` active state).
- Async work disables its trigger and sets `aria-busy`. Show a spinner only if the wait passes 300ms, so
  fast calls never flash. Past 1s, show skeleton blocks (see Skeleton pulse).
- Destructive actions either ask for confirmation in a dialog or offer "Undo" in a 5s toast. The button
  names the object ("Delete project"). Style it as the secondary pill with `error` text. No red fills.
- Empty state: one serif sentence plus one action. Error state: cause, fix, and a retry button.
- No gesture-only controls. Every critical action has a visible button.

**C · Forms** (adds to Part 2 Forms)

- Visible label on every field. A placeholder is never the label. Mark required or optional in the
  label text.
- Set the right `type`, `inputmode`, and `autocomplete` on every field (`email`, `tel`,
  `one-time-code`, `current-password`). Allow paste and password managers. Password fields get a
  show/hide icon button with `aria-pressed`.
- After a failed submit with 2+ errors, focus a summary at the top. Each item links to its field. Keep
  the inline errors too. With one error, focus that field.
- Error text says cause plus fix ("Use at least 12 characters"), never "Invalid input".
- Forms longer than one screen save a draft. Closing a modal with unsaved input asks first.
- Multi-step forms show "Step 2 of 4", allow Back, and keep what the user typed.

**D · Motion discipline** (the patterns live in Pro tokens → Motion)

- Animate at most 1–2 things in view at once. The hero title plus drift is the whole budget.
- Every motion shows cause and effect: something enters, leaves, changes state, or guides the eye. No
  decorative loops except drift and the scroll cue.
- Exits are about 65% of the enter time, on `ease-in-quart`.
- Motion never blocks input and is interruptible. Use CSS transitions for state (they retarget
  mid-flight), not keyframes. On rapid toggles set the final state explicitly. Never depend on
  `animationend` for correctness.
- Direction carries meaning. Going deeper enters from below. Going back returns the way it came.
- Animate only `opacity`, `translate`, `scale`, and `filter`. Never `width`, `height`, `top`, `left`,
  `margin`, or `box-shadow`.
- **The one layout exception** is the Height reveal (accordions, "show more"). It animates
  `grid-template-rows: 0fr → 1fr` on a wrapper with `overflow: hidden`, so the browser does one
  contained reflow per frame instead of a full page one. Mark the wrapper `contain: layout`.
  Nowhere else is a layout property allowed.
- Add `will-change` only while a move is running. Set it just before, clear it on `transitionend`.
  A permanent `will-change` on many nodes costs memory and makes the phone slower, not smoother.
- Scroll-linked motion never reads layout inside the scroll handler. Use CSS scroll-driven animations
  where supported, or rAF batching with `getBoundingClientRect` outside the handler. A forced reflow
  in a scroll handler is the most common source of jank on this kind of page.

**E · Layout and type**

- Headings and the lede use `text-wrap: balance`. Prose paragraphs use `text-wrap: pretty`. Both are
  hints, so the layout must still read well without them.
- Text containers that show URLs, ids, or user content use `overflow-wrap: anywhere`. Never
  `word-break: break-all` on prose.
- Full-height sections use `100svh`, never `100vh`. Never disable zoom. Viewport is
  `width=device-width, initial-scale=1`.
- Set `scrollbar-gutter: stable` on `html` so the page does not shift when a scrollbar appears.
  Never hide the scrollbar to make a page look calmer; that removes a progress cue the reader needs.
- Reserve space for anything async (`width`/`height` or `aspect-ratio`) so layout shift stays under 0.1.
- Prefer wrapping to truncating. When you must truncate, the full text is available on expand or focus.
- Use `font-variant-numeric: tabular-nums` on every number column, price, and timer.
- z-index scale: base 0, sticky 10, nav 20, popover 40, modal 100, toast 200. No other values.

**F · Navigation and data**

- Tabs, filters, sort, and pagination live in the URL. Back restores scroll position and filters.
- Use breadcrumbs from the third level down. Primary nav items show icon and label together.
- A chart has a text summary of its key insight (`figcaption` or `aria-label`) and a table
  alternative. Label values directly on the chart when there are 6 items or fewer.
- Tooltip content is reachable by keyboard. Sortable headers set `aria-sort`. Each series differs by more
  than color (label, position, or pattern). More than 5 categories means bars, not pies.
- Loading a chart shows a skeleton. A failed load shows a message plus retry. Entrance animation is off
  under reduced motion.

**G · House taste** (the owner's choices from building the portfolio. Follow them unless told otherwise.)

- Calm and buttery smooth beats clever. One motion idea per page change. No wipes, sweeps, or
  attention loops.
- A click never plays stop-then-go. Never chain two layout moves (something fades while holding
  space, then drops it). Pin whatever leaves, and start the main move at once.
- Things that leave just fade. Only the thing the user picked moves.
- **Native scroll is sacred.** Never lock the page, never catch the wheel, never slow the scroll to
  "reveal" a section. If a section needs a moment, it earns it with a shorter distance, not a lock.
- **Three entrance ideas per site, maximum:** the hero rise, the scroll reveal, and the stage settle.
  If a fourth appears, one of the three goes. This is the whole budget, not a guideline. State
  feedback (hover, tabs, accordions, exits) is not part of this budget. It is required.
- **A page the reader already met arrives at rest.** No entrance animation on back/forward, on a
  reload inside the same session, or on a route the user reached by pressing Back. Check
  `performance.getEntriesByType("navigation")[0].type` and skip the reveal for `"back_forward"`.
- **Reading works without the animations.** Every word of content is in the HTML, selectable and
  visible, before any script runs. Motion is the finishing coat, never the paint.
- Verify smoothness, do not assume it. Sample the moving element's rect every `requestAnimationFrame`
  in a headless browser (a hidden preview pane pauses rAF). Positions must change monotonically,
  with no jump between frames, and x must stay put unless the design moves it. Also diff the
  per-frame step: it must rise and fall as one smooth curve. A step that halves for one frame and
  then recovers is a hitch the eye sees. See **Motion QA** in Part 2 for the harness and the limits.
- Two-stage sites: a still night hero (A) settles into the paper page (B) with the Stage settle
  pattern (sticky hero, native scroll, paper slides over it). No scroll lock, no stolen gesture.
  A shows a glitch pixel name, the role in serif, and the focus line in sans, all centred.
  B shows the name as a small persistent title top-left.
- Reload keeps the reader where they were: the stage and any open section live in `sessionStorage`.
- Dark/light applies to B only. A is the same night in both themes, the mono canvas black `#0a0a0a`: pin its night tokens on the
  night layer. The theme toggle sits top-right on B, centred on the title's line, hidden on A.
- Titles on B use Newsreader (open stand-in for Tiempos). The name title is 600, about 19–21px,
  underlined. Section headings are 400 at `--fs-h2`, `letter-spacing: -0.03em`, underlined.
  The underline is `0.08em` thick with a `0.18em` offset.
- Lists are plain rows: number, serif name, one-line sans summary, link label right. No dotted
  leaders. The block is centred and the rows inside are left-aligned.
- Rejected, do not offer again: a header bar grid for the title, a theme-wipe transition, a
  corner-thread sweep.

### 9 · What not to take from UI/UX Pro Max

- Its style, palette, and font databases (`--design-system`, `style`, `color`, `typography` domains).
  They invent values. Ivory tokens only.
- Spring physics and GSAP presets. Ivory has one curve family, and GSAP adds JS weight.
- Glass, blur, shadow, and gradient styles. Native-app rules (haptics, safe areas, bottom tab bars).
- If its search tool is installed, query only `--domain ux`, `--domain react`, and `--stack react`.
  Treat results as ideas and check each one against §6 before using it.

---

## Overview

Editorial calm. A warm ivory page, near-black ink, and a serif voice for anything you *read*. A neutral
sans carries everything you *operate*. A single clay accent marks "this is the subject". Pages open on a
dark, cinematic hero and then settle into a narrow, generous reading column.

Colour roles are listed once, in the token block at the top of this file. Learn the names —
`ink`, `canvas`, `surface`, `muted`, `hairline`, `night`, `accent` — and never restate a hex.

## Typography

Serif for reading, sans for doing, mono for numbers that are labels.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=JetBrains+Mono:wght@400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
```

Type is **fluid**: sizes scale linearly between a 390px and a 1920px viewport. Use `clamp()` with the
min/max from the scale table below.

| Role | Font | Size (min → max) | Line height | Weight | Tracking |
|------|------|------------------|-------------|--------|----------|
| display-1 (hero) | serif | 48 → 96px | 1.04 | 400 | -0.02em |
| display-2 | serif | 36 → 56px | 1.08 | 400 | -0.015em |
| lede | serif | 22 → 28px | 1.29 | 400 | normal |
| h2 (section) | serif | 26 → 32px | 1.25 | 400 | normal |
| h3 | serif | 19 → 21px | 1.25 | 600 | normal |
| h5 (UI heading) | sans | 19 → 21px | 1.25 | 700 | normal |
| body (prose) | serif | 16 → 17px | 1.53 | 400 | normal |
| body (UI) | sans | 15px | 1.55 | 400 | normal |
| table / caption | sans | 14px | 1.4 | 400 / 600 | normal |
| eyebrow | sans | 14px | 1 | 500 | 0.12em, uppercase |
| button | sans | 13px | 1.54 | 400 | 0.01em |
| mono label | mono | 11px | 1 | 400 | normal |

## Spacing

4px base, 8px rhythm. Scale: `2 4 8 12 16 24 32 48 64 80 96 128 200`.

- Page margin `32px` (desktop) / `16px` (≤567px). Gutter `16–24px`.
- Container max `1400px`. Reading column max `720px` (prose at `640px` measure).
- Section spacing `64px` (lg) / `32px` (sm). Hero-to-lede gap `96–128px`.
- Breakpoints: mobile ≤567px, tablet ≤992px, desktop ≥1024px.

## Components and icons

Pills for actions. Squares for data. 16px corners for cards. 1px ink rules for tables. No shadows at rest.
Icons: `lucide-react`, stroke width 1.5, 16px in buttons, 20px standalone. Colour inherits text.

The full list of bans lives in §6 Hard constraints. Do not keep a second copy of it.

---

## Tokens

> Values live in the source block at the top (the spec) and in `globals.css` (the shipped copy).
> Everything below this line refers to roles by name. If the two copies disagree, the source block
> wins and `globals.css` is the bug.

### Colors

The colour roles and their values are the `colors:` block at the top of this file. That block is
the contract. Do not copy the hexes into a component, a test, or this section again.

Two reminders that the table cannot carry on its own:

- In Ivory, `accent` is a shape colour, never text. `faint` is disabled and decorative only.
- In Mono, `accent` becomes white and the subject column inverts. Nothing else about the layout moves.

### Radius

| Token | Value | Use |
|-------|-------|-----|
| none | `0px` | tables, media, sections |
| xs | `4px` | chips, inline wells |
| sm | `8px` | icon buttons |
| md | `12px` | inputs, small cards |
| lg | `16px` | cards, popovers |
| full | `999px` | pill buttons |

### Borders

| Token | Value |
|-------|-------|
| hairline | `0.5px` |
| sm | `1px` (default — table rules, inputs, dividers) |
| md | `1.5px` |
| lg | `2px` (tab indicator, focus ring) |

---

## Pro tokens

### States

#### Button (pill)

- **hover** — primary bg → `ink-soft`; secondary bg → `surface-strong`; on-dark bg → `#30302e`.
  `transition: background-color 200ms ease-in-out, color 200ms ease-in-out, border-color 200ms ease-in-out, box-shadow 200ms ease-in-out`.
- **focus-visible** — `outline: 2px solid var(--focus)`, `outline-offset: 2px`.
- **active** — `scale: 0.98` (100ms).
- **disabled** — opacity `0.4`, no pointer events.
- **loading** — opacity `0.6`, `aria-busy`.

#### Input

- rest — bg `canvas`, `1px solid hairline`, radius `md`, padding `10px 12px`, min-height 44px, ui 15px (16px at ≤567px, because iOS Safari zooms the page when a focused field is under 16px).
- hover — border `faint`.
- focus — border `ink`, plus focus ring.
- error — border `error`, helper text in `error` 14px below.
- disabled — bg `surface`, text `faint`.

#### Card

- hover (clickable only) — bg `surface-strong`, 200ms ease-in-out.
- selected — `1px solid ink` border.

#### Tab

- hover — color `ink-soft`, 150ms ease-out-quart.
- selected — color `ink`, indicator slides under it.

### Density

| Mode | padding × | body | Use for |
|------|-----------|------|---------|
| compact | 0.75 | 14px sans | tables, dashboards, settings |
| comfortable | 1 | 15px sans / 16px serif | default product UI |
| editorial | 1.25 | 17px serif | launch pages, articles, long-form |

### Motion

**Signature — Soft arrival.** Things fade up out of a slight blur, staggered word by word, on a
fast-out, long-settle curve. Background media drifts very slowly so the page feels alive without
asking for attention. UI state changes are quick (150–250ms) and plain.

| Token | Value | Use |
|-------|-------|-----|
| ease-out-quart | `cubic-bezier(.165, .84, .44, 1)` | **default** — reveals, tabs, height |
| ease-in-out-quart | `cubic-bezier(.77, 0, .175, 1)` | color/bg swaps on theme changes |
| ease-in-quart | `cubic-bezier(.895, .03, .685, .22)` | exits only |
| ease-standard | `cubic-bezier(.4, 0, .2, 1)` | accordions, layout glides |
| ease-snap | `cubic-bezier(.2, .8, .2, 1)` | strips/carousels sliding |
| duration-fast | `150ms` | popovers, tab color |
| duration-base | `200ms` | hover color/bg, links |
| duration-slide | `250ms` | tab indicator, carousels |
| duration-height | `400ms` | accordion open/close |
| duration-reveal | `600ms` | word rise, scroll reveal |
| duration-theme | `320ms` | light/dark flip on `<html>` |
| duration-stage | `600ms` | section background crossfade, stage shift |
| duration-press | `100ms` | press scale, tap feedback |
| duration-exit | `100ms` | popover, menu, toast leaving (65% of 150ms) |
| duration-scroll | `600ms` | scroll reveal, stagger items |
| stagger-step | `40ms` | delay between list/grid items, total capped at 320ms |

**Latency contract.** These are limits, not suggestions. Measure them on a 4× CPU-throttled phone.

| Moment | Dead line |
|--------|-----------|
| press feedback visible | 100ms |
| hover change starts | within the same frame |
| toggle or tab settle | 250ms |
| route change starts | 250ms |
| placeholder → skeleton | 300ms |
| skeleton → content | no extra delay; swap in the same frame the data lands |
| any single entrance | 600ms total, stagger included |

If a move cannot fit its dead line, shorten the distance, not the curve.

**Named patterns** — the only animations allowed.

1. **Word reveal** (hero title only). Split the title into word spans. Each word runs three
   animations with a stagger of 40ms per word, capped at 240ms:

   ```css
   @keyframes fade-in   { from { opacity: 0 } }
   @keyframes word-rise { from { transform: translateY(0.3em) } }
   @keyframes unblur    { from { filter: blur(3px) } }

   @media (prefers-reduced-motion: no-preference) {
     .word {
       display: inline-block;
       animation:
         fade-in   300ms var(--ease-out-quart) var(--delay) backwards,
         word-rise 600ms var(--ease-out-quart) var(--delay) backwards,
         unblur    600ms var(--ease-out-quart) var(--delay) backwards;
     }
   }
   ```

   Set `--delay` per word: `style={{ "--delay": `${Math.min(i, 6) * 40}ms` }}`. Capping the index
   keeps a long headline under the 600ms budget. Eyebrow and TOC use the same rise but with
   `translate: 0 10px` and a delay after the last word.

   Rules that keep the reveal calm:
   - Once per page, hero only. Never on section headings, cards, or body text.
   - One blanket fade first (150ms, whole block) so the title is legible almost at once. The word
     rise is the polish on top, not the only entrance.
   - The text is real text in the DOM from the first frame. No `opacity: 0` waiting on JS. If the
     script fails, the title still reads.
   - Skip the reveal on a return visit in the same session and on back/forward navigation. A page
     the reader has already met arrives at rest. Store one flag in `sessionStorage`.
   - Blur is allowed here and nowhere else. It is the most expensive filter in this file.

2. **Ambient drift** (hero collage/photo layers). Slow, alternating, out of phase. Never on text.

   ```css
   @keyframes drift-x    { from { translate: -12px 0 } to { translate: 12px 0 } }
   @keyframes drift-y    { from { translate: 0 -8px } to { translate: 0 8px } }
   @keyframes drift-zoom { from { scale: 1.02 } to { scale: 1.05 } }

   @media (prefers-reduced-motion: no-preference) {
     .drift-outer { animation: drift-x 18s ease-in-out -4s infinite alternate; }
     .drift-inner { animation: drift-y 23s ease-in-out -7s infinite alternate,
                               drift-zoom 31s ease-in-out infinite alternate; }
   }
   ```

   Use different cycle lengths per layer so they never sync.

3. **Scroll cue** (hero bottom). A small sans "Scroll" label or chevron in `night-eyebrow` at 55%
   opacity, looping `opacity 0 → 1 → 0` over 8s (visible from 56% to 94% of the cycle). Hide it once
   the user scrolls.

4. **Sliding indicator** (tabs, segmented controls). `transform: translateX() scaleX()` from a
   `transform-origin: left`, 250ms ease-out-quart. Transform only, so it stays on the compositor.
   Never animate `width` or `left` for this.

5. **Height reveal** (accordions, "show more"). One wrapper, `grid-template-rows: 0fr → 1fr` with
   `overflow: hidden` and `contain: layout`, 400ms ease-standard, opacity alongside. No JS height
   measuring, no `max-height` guess, no `height: auto` transition. This is the only layout
   animation allowed in the system.

6. **Theme crossfade**. The light/dark flip on `<html>` runs `background-color` and `color` over
   `320ms`. A section that changes tone as it enters view runs `600ms`. Under reduced motion keep
   the color change and drop every transform.

7. **Footnote landing**. When a footnote is the URL `:target`, its background holds `surface` for
   1.2s then fades to transparent over 600ms. Linear is fine here: the eye is only catching a place.

8. **Hover/press**. Hover is color and background only, 150–200ms. Press is `scale: .98` over
   `duration-press`. No lift, no scale above 1.

9. **Exit**. Popovers, menus, toasts, and modals leave in about 65% of their enter time, on
   `ease-in-quart`: `opacity` plus a 4px `translate` only. A 150ms enter leaves in `duration-exit`.

10. **Stagger**. Lists, cards, and grid cells enter with `opacity 0→1` and `translateY(12px)→0`, 600ms
    `ease-out-quart`, `stagger-step` apart. Cap the total at 320ms, so items past the eighth appear
    together. No blur.

11. **Scroll reveal** (below-the-fold sections, cards, figures, not every paragraph). Fires once when
    15% is visible (IntersectionObserver): `opacity 0→1`, `translateY(16px)→0`, 600ms `ease-out-quart`.
    Never repeats. The hidden start state is applied by JS (`.js-reveal`), so content shows without JS.

12. **Route crossfade**. On route change call `document.startViewTransition` where it exists. The old
    page fades out in 150ms and the new one fades in over 250ms `ease-out-quart`. Without support the
    swap is instant. Move focus to `<main>` after the transition ends.

13. **Skeleton pulse**. Loading blocks are `surface` fills pulsing `opacity 1 ↔ .6` over 1.4s on
    `ease-standard`. No gradient shimmer, because gradients are banned in UI. Show only after 300ms.

14. **Stage settle** (a still night hero that gives way to the paper page). Native scroll only.
    The hero is `position: sticky; top: 0; height: 100svh` inside a tall stage section. The paper
    is the next section, opaque `canvas`, `position: relative; z-index: 1`, with a 16px top radius.
    It slides over the hero because the reader scrolls, not because we played a timeline.

    - The hero scales to 0.98 and dims to 60% over the last 40svh of the stage. Drive it with
      `animation-timeline: scroll()` where supported, else one rAF loop that reads scroll once
      per frame. Never read layout inside the scroll handler.
    - **Never lock `overflow`.** Never replace the scroll with a wheel or touch catch. The page
      must answer the first wheel tick and the first swipe, every time. No scroll debts.
    - The "Scroll" affordance is a real anchor to the first paper section. Keyboard, screen
      reader, and reduced-motion users skip the stage entirely.
    - Paper content is in the DOM from the start. It enters with its own 600ms stagger when half
      of it is visible (Scroll reveal), not after a sheet lands.
    - Reverse is free, because there is nothing to reverse. Scroll up and the hero is still there.
    - Reduced motion: no sticky, no scale, no dim. Two plain stacked sections.
    - Verify this one on a throttled phone. Sticky plus a scroll-driven transform is the pattern
      that exposes a bad frame budget first.

15. **Focus disclosure** (a centred stack of headings, each opening its own list). Click a
    heading and it becomes the only thing on the page with its list. Every click is **one move
    that starts in the same frame**. Nothing waits on anything else.
    - Open: measure the other headings, pin them where they stand (`position: fixed` at their
      rect, out of the layout) and fade them in 300ms `ease-out-quart`. Never `ease-in` here: it
      holds the heading for 100ms, then blinks it out, which reads as a jerk. In the same commit, the
      chosen heading glides to its new place in 600ms `ease-standard` (a Motion layout animation,
      so a transform). Its rows rise in on the Stagger pattern after 300ms.
    - Close: the rows fade in 100ms where they stand (`AnimatePresence mode="popLayout"`), riding
      along with the heading as it glides back. The list's gap above is `padding-top`, never
      `margin-top`, or popLayout drops it 48px. The other headings rejoin at once at opacity 0
      and fade in after 450ms, once the glide has passed their spot.
    - Closed, every heading box is as wide as the widest heading (measured from a hidden copy,
      `Math.ceil`, `white-space: nowrap`) and centred, so the stack shares one left edge and moves
      only vertically. Open, the heading shrinks to its own width and centres over its rows. Put
      `layout="position"` on the heading too, so that slide folds into the same glide.
    - The open heading and its list centre as a block in the viewport. The rows are left-aligned.
    - Save the open heading in `sessionStorage`, so a reload comes back to it.
    - Nothing may re-render the moving heading mid-glide. Set `layoutDependency={expanded}` on
      every layout element, skip `LayoutGroup`, and remove the faded headings only after the glide
      lands. A mid-glide re-measure makes one frame run at half speed: a visible 0.1s hitch.

Everything above sits inside `@media (prefers-reduced-motion: no-preference)`. Under `reduce`, content
appears at its final state instantly.

### Elevation

The system is flat. Depth comes from fills and the dark/light section switch.

| Level | Value | Use |
|-------|-------|-----|
| level0 | `none` | everything at rest |
| level1 | `0 0 0 1px var(--hairline)` | inputs, secondary pill border |
| level2 | `0 1px 2px rgb(20 20 19 / .06), 0 4px 16px rgb(20 20 19 / .08)` | popovers, menus, dropdowns only |
| level3 | `0 8px 40px rgb(20 20 19 / .16)` | modals only |

Overlays/scrims: `rgb(20 20 19 / .2)` (`tint-20`).

Mono overrides: `level-2` = `0 0 0 1px var(--hairline), 0 8px 24px rgb(0 0 0 / .6)`,
`level-3` = `0 0 0 1px var(--hairline), 0 16px 48px rgb(0 0 0 / .8)`, scrim `rgb(0 0 0 / .6)`.

### Content

- **measure:** `640px` prose, inside a `720px` reading column.
- **paragraph spacing:** `1.25em`.
- **lists:** indent `1.5em`, gap `0.5em`, serif.
- **link:** `ink`, underline always, 0.08em thick, 0.18em offset, hover `accent-strong`.
- **inline bold lead-ins:** paragraphs may start with a bold serif phrase ending in a period
  ("**Safety.** Text…"). This is the house pattern for feature lists. Do not use bullet lists for them.
- **code:** mono 0.88em, no background, `ink`.
- **numbers in tables:** tabular figures (`font-variant-numeric: tabular-nums`).

### Accessibility (WCAG 2.1)

| Pair | Ratio | Grade | Rule |
|------|-------|-------|------|
| ink on canvas | 17.5:1 | AAA | default text |
| ink on surface | 15.9:1 | AAA | cards |
| ink on accent-tint | 11.9:1 | AAA | highlighted cells |
| night-ink on night-raised | 14.4:1 | AAA | pills on dark |
| night-eyebrow on night | 16.5:1 | AAA | hero text |
| muted on canvas | 6.3:1 | AA | captions, inactive tabs |
| muted on surface | 5.7:1 | AA | captions on cards |
| error on canvas | 4.6:1 | AA | error text |
| accent-strong on canvas | 3.9:1 | AA-Large | large text / UI shapes only |
| faint on canvas | 3.5:1 | Fail for text | disabled and decorative only. Never a clickable label |
| accent on canvas | 3.0:1 | Fail for text | borders and fills only |

Hero text over imagery must sit on a dark area or a `night` scrim so it keeps ≥ 4.5:1.

**Mono theme:**

| Pair | Ratio | Grade | Rule |
|------|-------|-------|------|
| ink on canvas | 16.9:1 | AAA | default text |
| ink on surface | 15.7:1 | AAA | cards |
| on-accent-tint on accent-tint | 19.0:1 | AAA | inverted subject column |
| night-ink on night | 20.1:1 | AAA | hero text |
| night-ink on night-raised | 15.8:1 | AAA | pills on hero |
| ink-soft on canvas | 13.4:1 | AAA | secondary headings |
| muted on canvas | 7.9:1 | AAA | captions |
| muted on surface | 7.3:1 | AAA | captions on cards |
| error on canvas | 6.5:1 | AA | error text |
| faint on canvas | 4.2:1 | Fail for small text | disabled and decorative only |

---

# Part 2 · Engineering standards

Generic production practices. They apply regardless of which design system is loaded, but the examples
below are written in Ivory Editorial so you can copy them directly.

## Token wiring — do this first

Declare tokens **once** as CSS custom properties, then never write a raw hex in a component again.

```css
/* styles/globals.css — the only file with literal token values */
:root,
[data-theme="ivory"] {
  color-scheme: light;
  /* color */
  --ink: #141413;           --ink-soft: #3d3d3a;
  --muted: #5e5d59;         --faint: #87867f;     --hairline: #d1cfc5;
  --canvas: #faf9f5;        --surface: #f0eee6;   --surface-strong: #e8e6dc;
  --night: #0f0f0e;         --night-raised: #262624;
  --night-ink: #faf9f5;     --night-eyebrow: #f2ede4;
  --accent: #d97757;        --accent-strong: #c6613f; --accent-tint: #ebc9b7;
  --on-accent-tint: #141413; --night-hover: #30302e;
  --focus: #2c84db;         --error: #bf4d43;
  --media-filter: none;
  --scrim: rgb(20 20 19 / .2);

  /* type */
  --font-serif: "Source Serif 4", Georgia, "Times New Roman", serif;
  --font-sans:  "DM Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono:  "JetBrains Mono", ui-monospace, monospace;
  --fs-display-1: clamp(48px, 3.14vw + 35.75px, 96px);
  --fs-lede:      clamp(22px, 0.39vw + 20.47px, 28px);
  --fs-h2:        clamp(26px, 0.39vw + 24.47px, 32px);
  --fs-body:      clamp(16px, 0.065vw + 15.75px, 17px);
  --tracking-eyebrow: 0.12em;

  /* radius */
  --r-none: 0; --r-xs: 4px; --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-full: 999px;

  /* space */
  --sp-4: 4px;  --sp-8: 8px;  --sp-12: 12px; --sp-16: 16px; --sp-24: 24px;
  --sp-32: 32px; --sp-48: 48px; --sp-64: 64px; --sp-96: 96px; --sp-128: 128px;
  --page-margin: 32px; --reading-col: 720px; --measure: 640px; --container: 1400px;
  --nav-h: 84px;

  /* elevation */
  --level-1: 0 0 0 1px var(--hairline);
  --level-2: 0 1px 2px rgb(20 20 19 / .06), 0 4px 16px rgb(20 20 19 / .08);
  --level-3: 0 8px 40px rgb(20 20 19 / .16);

  /* motion */
  --ease-out-quart: cubic-bezier(.165, .84, .44, 1);
  --ease-in-out-quart: cubic-bezier(.77, 0, .175, 1);
  --ease-in-quart: cubic-bezier(.895, .03, .685, .22);
  --ease-standard: cubic-bezier(.4, 0, .2, 1);
  --ease-snap: cubic-bezier(.2, .8, .2, 1);
  --dur-fast: 150ms; --dur-base: 200ms; --dur-slide: 250ms;
  --dur-height: 400ms; --dur-reveal: 600ms; --dur-theme: 320ms; --dur-stage: 600ms;
  --dur-press: 100ms; --dur-exit: 100ms; --dur-scroll: 600ms; --stagger-step: 40ms;

  /* z-index scale — no other values */
  --z-sticky: 10; --z-nav: 20; --z-popover: 40; --z-modal: 100; --z-toast: 200;
}
@media (max-width: 567px) { :root { --page-margin: 16px; } }

/* Mono — b/w dark mode. Only color/elevation tokens change. */
[data-theme="mono"] {
  color-scheme: dark;
  --ink: #ededed;           --ink-soft: #d4d4d4;
  --muted: #a3a3a3;         --faint: #737373;     --hairline: #2e2e2e;
  --canvas: #0a0a0a;        --surface: #141414;   --surface-strong: #1f1f1f;
  --night: #000000;         --night-raised: #1f1f1f; --night-hover: #2a2a2a;
  --night-ink: #fafafa;     --night-eyebrow: #e5e5e5;
  --accent: #fafafa;        --accent-strong: #ffffff; --accent-tint: #fafafa;
  --on-accent-tint: #0a0a0a;
  --focus: #ffffff;         --error: #ef6b5f;
  --media-filter: grayscale(1) contrast(1.08);
  --scrim: rgb(0 0 0 / .6);
  --level-2: 0 0 0 1px var(--hairline), 0 8px 24px rgb(0 0 0 / .6);
  --level-3: 0 0 0 1px var(--hairline), 0 16px 48px rgb(0 0 0 / .8);
}

.hero img, .hero video, figure img { filter: var(--media-filter); }
[data-theme="mono"] .hero { border-bottom: 1px solid var(--hairline); }
::selection { background: var(--ink); color: var(--canvas); }

/* UX base (see §8) */
html { scroll-padding-top: calc(var(--nav-h) + var(--sp-16)); scrollbar-gutter: stable; }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
h1, h2, h3, .lede, blockquote { text-wrap: balance; }
.prose p { text-wrap: pretty; }
a, button, [role="button"] { touch-action: manipulation; }
button:not(:disabled), [role="button"], summary, label[for] { cursor: pointer; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.skip-link { position: absolute; left: var(--sp-16); top: -100px; z-index: var(--z-toast);
             padding: var(--sp-8) var(--sp-16); border-radius: var(--r-full);
             background: var(--ink); color: var(--canvas); font: 400 13px/1.54 var(--font-sans); }
.skip-link:focus { top: var(--sp-16); }
@media (max-width: 567px) { input, select, textarea { font-size: 16px; } }

/* Theme crossfade when the user flips the toggle */
@media (prefers-reduced-motion: no-preference) {
  html, body { transition: background-color var(--dur-theme), color var(--dur-theme); }
}

body {
  background: var(--canvas);
  color: var(--ink);
  font: 400 15px/1.55 var(--font-sans);
  -webkit-font-smoothing: antialiased;
}
.prose { font-family: var(--font-serif); font-size: var(--fs-body); line-height: 1.53;
         max-width: var(--measure); margin-inline: auto; }
.prose a { color: inherit; text-decoration-thickness: .08em; text-underline-offset: .18em;
           transition: color var(--dur-base) ease-out; }
.prose a:hover { color: var(--accent-strong); }
```

Rules:

Set the theme before first paint so there is no flash. Put this inline in `<head>`, above the CSS:

```html
<script>
  (function () {
    var t = null;
    try { t = localStorage.getItem("theme"); } catch (e) {}
    if (t !== "ivory" && t !== "mono") {
      t = matchMedia("(prefers-color-scheme: dark)").matches ? "mono" : "ivory";
    }
    document.documentElement.dataset.theme = t;
  })();
</script>
```

A project that ships only one theme hard-codes `<html data-theme="mono">` and skips the script.

- A literal hex outside this file is a bug. Grep for `#[0-9a-fA-F]{3,8}\b` in `src/` before you ship.
- If a value you need has no token, **stop and ask** — do not add one silently.
- Tailwind users: map these into `theme.extend` (colors, fontFamily, borderRadius, transitionTimingFunction)
  and remove the default palette. `gray-500` and `blue-600` are a second, competing design system.

## Project structure

Organize by **feature**, not by file type.

```
src/
  app/                    # routes / pages — thin, composition only
  features/
    launch-page/
      components/         # Hero, Toc, BenchmarkTable — feature-local UI
      hooks/
      content.ts          # copy + data for this page
      index.ts            # public surface — import from here, never deeper
  components/ui/          # cross-feature primitives: Button, Tabs, Card, Input, Eyebrow, WordReveal
  lib/                    # api client, formatters, motion helpers
  styles/globals.css      # the token file above
```

- Features import from `components/ui` and `lib` freely. A feature never reaches into another feature.
- One component per file, named like the file. Colocate the test as `Button.test.tsx`.
- Barrel files only at feature boundaries.

## Components

Write primitives once, in `components/ui`, driven by a variant prop.

```tsx
// components/ui/Button.tsx
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";

const button = cva(
  "inline-flex items-center justify-center gap-1.5 font-sans text-[13px] leading-[1.54] " +
    "tracking-[0.01em] min-h-11 transition-[background-color,color,border-color,box-shadow] " +
    "duration-200 ease-in-out active:scale-[.98] " +
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 " +
    "focus-visible:outline-[var(--focus)] disabled:opacity-40 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary:   "rounded-full px-4 py-2 bg-[var(--ink)] text-[var(--canvas)] hover:bg-[var(--ink-soft)]",
        secondary: "rounded-full px-4 py-2 bg-[var(--surface)] text-[var(--ink)] border border-[var(--hairline)] hover:bg-[var(--surface-strong)]",
        onDark:    "rounded-full py-2 pl-4 pr-3 bg-[var(--night-raised)] text-[var(--night-ink)] hover:bg-[var(--night-hover)]",
        ghost:     "p-0 font-medium text-[var(--ink)] hover:underline underline-offset-[0.18em]",
        icon:      "rounded-[var(--r-sm)] p-2 bg-[var(--surface)] text-[var(--ink)] hover:bg-[var(--surface-strong)]",
      },
    },
    defaultVariants: { variant: "primary" },
  },
);

type Props = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof button> & { loading?: boolean };

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ variant, loading, className, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={button({ variant, className })}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      style={loading ? { opacity: 0.6 } : undefined}
      {...props}
    >
      {children}
    </button>
  ),
);
Button.displayName = "Button";
```

```tsx
// components/ui/WordReveal.tsx — the hero title pattern
type Props = { text: string; as?: "h1" | "h2"; stagger?: number; className?: string };

export function WordReveal({ text, as: Tag = "h1", stagger = 40, className }: Props) {
  const words = text.split(" ");
  const animated = arrivalIsFresh(); // false on back/forward or a repeat visit
  return (
    <Tag className={className} aria-label={text}>
      {words.map((w, i) => (
        <span
          key={i}
          aria-hidden
          className={animated ? "word" : undefined}
          style={animated ? ({ "--delay": `${Math.min(i, 6) * stagger}ms` } as React.CSSProperties) : undefined}
        >
          {w}{i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </Tag>
  );
}
```

```ts
// lib/arrival.ts — decides whether an entrance animation may play
export function arrivalIsFresh(): boolean {
  if (sessionStorage.getItem("seen")) return false;
  const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
  if (nav?.type === "back_forward" || nav?.type === "reload") return false;
  sessionStorage.setItem("seen", "1");
  return true;
}
```

Principles for every primitive:

- **Variants, not props soup.** One `variant` union mapped to the declared set.
- **Forward the ref and spread the rest.**
- **Extend the native element's props type.**
- **Style via `className`,** inline `style` only for dynamic values like `--delay`.
- **Never accept a `color` prop.**

## State management

Pick the smallest tool that works, in this order:

1. Local `useState`.
2. Lift to the nearest common parent.
3. URL search params — tabs, filters, pagination, sort. Benchmark tabs belong here.
4. Context — app-wide, rarely changing (theme, session, locale).
5. A store (Zustand/Jotai) — only when distant subtrees write the same state.

Server data is a cache, not client state. Use TanStack Query (or the framework's data layer).

- **Derive, don't sync.** No effect that mirrors one state into another.
- **Effects are for external systems** — IntersectionObserver for theme crossfade, timers, analytics.
- Always render pending, error, and empty states.

## Data fetching and errors

- One typed API client in `lib/api.ts`. Components never call `fetch` directly.
- Validate untrusted responses at the boundary with Zod.
- Every mutation shows `aria-busy`, disables its trigger, and surfaces failures inline.
- Wrap each route in an error boundary with a real recovery action.
- Abort superseded requests with `AbortController`.

## Forms

- React Hook Form + Zod, one schema shared with the API types.
- Validate on blur, revalidate on change after the first error.
- Real `<label>` on every input, ui 14px weight 500 above the field.
- Errors wire `aria-invalid` + `aria-describedby`, using the `error` token border and helper text.
- Disable submit only while submitting.
- Error summary, `autocomplete`, `inputmode`, and draft saving are in §8 C.

## Accessibility

- Semantic HTML first. One `<h1>`, no skipped levels. If the hero title is drawn in canvas or WebGL,
  keep a real visually-hidden `<h1>` with the same text.
- Keyboard complete. Tabs use arrow keys. Modals trap and restore focus.
- Visible focus always: `2px solid var(--focus)`, offset 2px. The blue ring is the only blue in the UI.
- Hit targets ≥ 44×44px. Pad the 32px icon buttons.
- Icon-only controls get `aria-label`. Decorative icons get `aria-hidden`.
- **Every animation behind `prefers-reduced-motion: no-preference`.** Word reveal, drift, and scroll
  cue must all be off under `reduce`. Pause ambient drift when the hero is off-screen.
- Respect the contrast table. `faint` and `accent` never carry text a user must read or click.
- Skip link, `scroll-padding-top`, focus after route change, and `aria-current` are required. See §8 A.
- Under `prefers-contrast: more`, step `muted` up to `ink-soft` and `hairline` up to `ink`. Do not
  invent a new palette. Under `prefers-reduced-transparency`, replace scrims with a solid `night`.
- At 200% zoom and 320px wide, text wraps and nothing scrolls sideways except wide tables.

## Performance

1. **Ship less JS.** Route-level splitting. Dynamic-import charts and any WebGL hero.
2. **Motion on the compositor.** Animate only `opacity`, `transform`/`translate`/`scale`, and `filter`.
   Blur is costly — keep `unblur` to the hero title, not body text. Never blur a full-screen layer.
3. **Pause off-screen loops.** Drift and scroll cue stop when the hero leaves the viewport
   (`animation-play-state: paused` via IntersectionObserver).
4. **Stable keys,** virtualize lists > 100 rows.
5. **Images:** explicit `width`/`height`, AVIF/WebP, hero images `fetchpriority="high"`, everything else lazy.
6. **Fonts:** three families is the whole budget. Preconnect, `display=swap`, subset if self-hosting.
   Load only the weights in the font URL. Self-host when you can: two fewer DNS trips beats any
   `display=swap` tuning.
7. **Long pages:** put `content-visibility: auto` with `contain-intrinsic-size` on below-the-fold
   sections. The browser skips their layout and paint until they near the viewport.
8. **Never read layout in a hot handler.** `getBoundingClientRect`, `offsetHeight`, and
   `getComputedStyle` force a reflow. Read them once before the move, write on rAF, never inside
   `scroll`, `pointermove`, or `resize`.
9. **`will-change` has a lifetime.** Add it on the frame before the move, clear it on
   `transitionend`/`animationend`. A page that sets it on ten nodes at load is slower on mobile.
10. **Isolate what animates.** `contain: layout paint` on the moving wrapper keeps one section's
    reflow from reaching the rest of the page.

## Motion QA

Smoothness is a measurement, not an opinion. Run this before you call a page done.

- Frame budget is 16.7ms at 60Hz and 8.3ms at 120Hz. A frame over about 20ms is a hitch the eye sees.
- On a vertical move, x must not move more than 1px.
- Fail if one frame's step is under 0.35× the median (a stall) or over 2.5× (a jump).
- Test at 4× CPU throttle. Your laptop is not the reader's phone.
- Test at 200% zoom and at 360px wide. Smoothness that breaks the layout is not smoothness.
- A hidden tab and a hidden preview pane both pause rAF. Measure in a visible page.

```ts
// scripts/motion-check.ts — npx tsx scripts/motion-check.ts <url> <selector> [trigger]
import { chromium } from "playwright";

const [url, selector, trigger] = process.argv.slice(2);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const cdp = await page.context().newCDPSession(page);
await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 }); // a mid-range phone
await page.goto(url, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(300); // let any load-time reveal finish

// 1. install the sampler, one rect read per frame
await page.evaluate((sel) => {
  const el = document.querySelector(sel)!;
  const out: Array<{ t: number; x: number; y: number }> = [];
  (window as any).__frames = out;
  const tick = (t: number) => {
    const r = el.getBoundingClientRect();
    out.push({ t, x: r.x, y: r.y });
    if (out.length < 180) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}, selector);

// 2. fire the interaction, then let the move play out
if (trigger) await page.click(trigger);
await page.waitForTimeout(1200);

const frames = (await page.evaluate(() => (window as any).__frames)) as
  Array<{ t: number; x: number; y: number }>;
await browser.close();

const moved = frames.filter((f, i) => i && Math.abs(f.y - frames[i - 1].y) > 0.1);
const steps = moved.slice(1).map((f, i) => Math.abs(f.y - moved[i].y));
const median = [...steps].sort((a, b) => a - b)[Math.floor(steps.length / 2)] || 1;
const xDrift = Math.max(...frames.map((f) => f.x)) - Math.min(...frames.map((f) => f.x));

const report = {
  frames: frames.length,
  xDrift: +xDrift.toFixed(2),
  jump: +(Math.max(...steps) / median).toFixed(2),
  stall: +(Math.min(...steps) / median).toFixed(2),
};

console.table(report);
if (report.xDrift > 1) console.error("FAIL: x moved on a vertical move");
if (report.jump > 2.5) console.error("FAIL: a frame jumped");
if (report.stall < 0.35) console.error("FAIL: a frame stalled");
```

For a move that plays on page load, install the sampler with `page.addInitScript` before `goto` instead.

Run it for the hero reveal, the tab indicator, the accordion, and the stage settle. Those four cover
every motion the system allows.

## TypeScript

- `strict: true`. No `any`. No `!` without a comment.
- Model states as discriminated unions.
- Derive types from Zod schemas with `z.infer`.
- Export prop types for components meant to be wrapped.

## Testing

- React Testing Library, query by role and name.
- Never test class names or token hexes. Test what the user sees and does.
- Mock at the network boundary (MSW).
- Cover pending, error, empty, one keyboard-only path, and one run with `prefers-reduced-motion: reduce`
  mocked to prove content is visible without animation.

## Definition of done

- [ ] Part 1's verify checklist passes.
- [ ] No literal hex outside `globals.css`.
- [ ] Serif/sans split is correct on every element.
- [ ] Pending, error, empty states render.
- [ ] Full keyboard traversal with a visible focus ring.
- [ ] Reduced-motion run shows every piece of content at rest.
- [ ] Each shipped theme checked: no hard-coded color shows up wrong after flipping `data-theme`,
      and the page loads in the saved theme with no flash.
- [ ] Typechecks and lints clean. Tests cover the main flow.
- [ ] Responsive from 360px to wide. Only wide tables scroll sideways, inside their own wrapper.
- [ ] §8 UX rules pass: skip link, no hover-only features, error summary on forms, text alternative on
      every chart, focus moves to `<main>` after a route change.
- [ ] Motion: at most 2 things animate at once, exits are shorter than enters, nothing blocks input.
- [ ] Motion QA ran on the hero reveal, the tab indicator, the accordion, and the stage settle, at
      4× CPU throttle. No stall under 0.35×, no jump over 2.5×, x drift under 1px.
- [ ] Every dead line in the latency contract is met on a throttled phone.
- [ ] Native scroll was not hijacked, locked, or smoothed anywhere.
- [ ] Mobile: inputs are 16px, `100svh` not `100vh`, no horizontal page scroll.
