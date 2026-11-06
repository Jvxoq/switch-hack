---
name: mono-frontend
description: "Use when building or reviewing any frontend UI — new pages, components, layouts, forms, tables, charts, or design-token setup. Encodes the Mono Brutalist design system (pure black on white, monospace everywhere, zero radius, hard offset shadows) as a non-negotiable token contract, plus generic production frontend standards for React/TypeScript: project structure, state management, accessibility, forms, data fetching, and performance. Load BEFORE writing UI code, not after a review finds the design drifted."
---

# Mono Frontend

Build UI that looks like one person designed it. This skill has two halves:

1. **The design system** — Mono Brutalist. A fixed token contract. Never improvise values.
2. **The engineering standards** — how to structure, fetch, validate, and ship the code that renders those tokens.

Read Part 1 before writing any markup. Read Part 2 before deciding where files go or how state flows.

---

# Part 1 · Mono Brutalist design system

## AI Build Instructions

> **Read this section before writing any code.** The rules below are non-negotiable. Every value used in
> the UI must come from this file's token block — never substitute, approximate, or invent new colors,
> fonts, radii, or shadows. If a value is missing, ask the user before adding one.

### 1 · Your role

You are building UI for a project that has adopted **Mono Brutalist** as its design system. Treat this
file as the single source of truth. Your job is to translate the user's product requirements into
components and pages that look like they were designed by the same person who authored this file.

### 2 · Token compliance

- Pull every color, font family, radius, shadow, and spacing value from the token block below.
- Use semantic roles (e.g. `primary`, `accent`, `muted`) — never hard-code hex values that bypass the system.
- When a token can be expressed as a CSS variable, declare it once in your global stylesheet and
  reference it everywhere downstream.
- The Google Fonts `<link>` is provided in the Typography section. Add it to `<head>` before any
  component renders.

### 3 · Source tokens

```yaml
name: "Mono Brutalist"
description: "Pure black on white. Hard borders, monospace everywhere, zero compromise."
tags: [brutalist, minimal, dark]
colors:
  primary:   "#000000"
  secondary: "#555555"
  tertiary:  "#000000"
  neutral:   "#FFFFFF"
  surface:   "#FFFFFF"
typography:
  display: "JetBrains Mono"
  body:    "JetBrains Mono"
  mono:    "JetBrains Mono"
radius:
  sm: 0px
  md: 0px
  lg: 0px
buttons:
  primary:
    background: "#000000"
    color: "#FFFFFF"
    border: 2px solid #000000
    shape: sharp
    padding: 12px 24px
    font: mono / 700 / 0.08em
    uppercase: true
  secondary:
    background: "#FFFFFF"
    color: "#000000"
    border: 2px solid #000000
    shape: sharp
    padding: 12px 24px
    font: mono / 700 / 0.08em
    uppercase: true
  outline:
    background: transparent
    color: "#000000"
    border: 2px dashed #000000
    shape: sharp
    padding: 12px 24px
    font: mono / 700 / 0.08em
    uppercase: true
  ghost:
    background: transparent
    color: "#000000"
    border: none
    shape: sharp
    padding: 10px 0
    font: mono / 700 / 0.08em
    uppercase: true
    hover: underline
charts:
  variant: flat
  bar_gap: 2px
  highlight: all
fonts_url: "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&display=swap"
dependencies: ["lucide-react"]
```

### 4 · Component recipes

Use these recipes verbatim when building the corresponding component.

#### Buttons

Four variants are defined. Pick one — never blend variants or invent a fifth.

- **Primary** — sharp shape, bg `#000000`, text `#FFFFFF`, border `2px solid #000000`, padding `12px 24px`, weight `700`, uppercased.
- **Secondary** — sharp shape, bg `#FFFFFF`, text `#000000`, border `2px solid #000000`, padding `12px 24px`, weight `700`, uppercased.
- **Outline** — sharp shape, text `#000000`, border `2px dashed #000000`, padding `12px 24px`, weight `700`, uppercased.
- **Ghost** — sharp shape, text `#000000`, padding `10px 0`, weight `700`, uppercased.

Reach for **primary** as the single dominant CTA per screen. **Secondary** for the supporting action.
**Outline** for tertiary actions in toolbars. **Ghost** for inline links and table actions.

#### Cards

- Background: `#FFFFFF`
- Radius: `radius.lg` (`0px`)
- Internal padding: `20px` for compact cards, `24–28px` for content cards.

#### Tabs

Variant: `brutalist`. Hard rectangular tabs with thick borders. Active tab is fully filled in the
primary color. Tabs are uppercased with `0.1em` tracking.

#### Charts

- Bar/line variant: `flat`
- Highlight strategy: `all` — emphasize a single bar/point per chart.

#### Typography pairings

- **Display (`JetBrains Mono`)** — h1, h2, hero headlines, brand wordmarks.
- **Body (`JetBrains Mono`)** — paragraphs, labels, button text, form inputs.
- **Mono (`JetBrains Mono`)** — code, eyebrows, metadata, numerals in tables.

### 5 · Hard constraints

Never do any of the following without explicit instruction from the user:

- Introduce a new color, font, radius, or shadow that isn't declared above.
- Mix this system with another (e.g. don't paste in Material or Bootstrap defaults).
- Use generic gradient defaults (purple→blue, peach→pink) — they break the system's voice.
- Reach for emoji icons. Use a consistent icon library and size icons in line with body type.
- Add motion that exceeds the system's restraint — keep transitions short (≤200ms) and subtle.

### 6 · Before you finish — verify

Run through this checklist for every screen you produce:

- [ ] Every color used appears in the Colors table below.
- [ ] Headlines use the display font; body copy uses the body font.
- [ ] Buttons match one of the declared variants exactly (shape, padding, weight).
- [ ] Border-radius values come from `radius.sm` / `radius.md` / `radius.lg` / `radius.pill`.
- [ ] Cards and dividers use the declared border + shadow tokens.
- [ ] No values were invented; if you needed something missing, you stopped and asked.

---

## Overview

Raw, uncompromising, system-font monospace. No color, no curves, no shadow. Structure and typography
do all the work.

## Colors

- **Primary #000000** — pure black. Borders, text, fills.
- **Secondary #555555** — only for de-emphasized meta.
- **Neutral / Surface #FFFFFF** — pure white.

## Typography

**JetBrains Mono** at every level. Use weight (400/500/700/800) and uppercase for hierarchy.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&display=swap" rel="stylesheet">
```

## Spacing

8px grid. Sections 80px. Tight, deliberate.

## Components

Hard 2px black borders. Zero border-radius. Zero shadows at rest. Buttons uppercase.

## Icons

`lucide-react` with stroke width 2. Always black.

## Do's and Don'ts

- ✅ Use uppercase for buttons and labels.
- ✅ Keep borders crisp at 2px.
- ❌ No rounded corners, anywhere.
- ❌ No grays except #555 for meta.

---

## Tokens

> Generated from the same source the live preview renders from.
> Treat the values below as the contract — never substitute approximations.

### Colors

| Role      | Value |
|-----------|-------|
| primary   | `#000000` |
| secondary | `#555555` |
| tertiary  | `#000000` |
| neutral   | `#FFFFFF` |
| surface   | `#FFFFFF` |

### Typography

- **Display:** JetBrains Mono
- **Body:** JetBrains Mono
- **Mono:** JetBrains Mono

### Radius

- sm: `0px`
- md: `0px`
- lg: `0px`

### Buttons

Four variants, each fully tokenized. The preview renders from these exact values.

#### Primary

| Property | Value |
|----------|-------|
| shape | `sharp` |
| background | `#000000` |
| color | `#FFFFFF` |
| border | `2px solid #000000` |
| padding | `12px 24px` |
| fontFamily | `mono` |
| fontWeight | `700` |
| tracking | `0.08em` |
| uppercase | `true` |

#### Secondary

| Property | Value |
|----------|-------|
| shape | `sharp` |
| background | `#FFFFFF` |
| color | `#000000` |
| border | `2px solid #000000` |
| padding | `12px 24px` |
| fontFamily | `mono` |
| fontWeight | `700` |
| tracking | `0.08em` |
| uppercase | `true` |

#### Outline

| Property | Value |
|----------|-------|
| shape | `sharp` |
| background | `transparent` |
| color | `#000000` |
| border | `2px dashed #000000` |
| padding | `12px 24px` |
| fontFamily | `mono` |
| fontWeight | `700` |
| tracking | `0.08em` |
| uppercase | `true` |

#### Ghost

| Property | Value |
|----------|-------|
| shape | `sharp` |
| background | `transparent` |
| color | `#000000` |
| border | `none` |
| padding | `10px 0` |
| fontFamily | `mono` |
| fontWeight | `700` |
| tracking | `0.08em` |
| uppercase | `true` |
| hoverHint | `underline` |

### Charts

| Property | Value |
|----------|-------|
| variant | `flat` |
| barGap | `2px` |
| highlight | `all` |

---

## Pro tokens

> Production-fidelity tokens. States, density, motion, elevation, content rules and a measured WCAG
> contract — derived from the resting tokens unless explicitly authored.

### States

#### Button

- **hover** — shadow: `4px 4px 0 0 #000000`, transform: `translate(-2px, -2px)`
- **focus** — outline: `2px solid #000000`, outline-offset: `3px`
- **active** — shadow: `none`, transform: `translate(0, 0)`
- **disabled** — opacity: `0.4`, filter: `grayscale(0.4)`
- **loading** — opacity: `0.6`
- **selected** — bg: `#000000`, color: `#FFFFFF`

#### Input

- **hover** — border: `2px solid #000000`
- **focus** — border: `2px solid #000000`, shadow: `4px 4px 0 0 #000000`
- **disabled** — bg: `rgba(0, 0, 0, 0.05)`, opacity: `0.4`
- **error** — border: `2px solid #B91C1C`, shadow: `4px 4px 0 0 #B91C1C`

#### Card

- **hover** — shadow: `6px 6px 0 0 #000000`, transform: `translate(-3px, -3px)`
- **selected** — border: `3px solid #000000`
- **dragging** — shadow: `8px 8px 0 0 #000000`, transform: `rotate(-1deg) scale(1.02)`

#### Tab

- **hover** — bg: `rgba(0, 0, 0, 0.08)`
- **focus** — outline: `2px solid #000000`, outline-offset: `2px`
- **selected** — bg: `#000000`, color: `#FFFFFF`

### Density

| Mode | padding × | row × | body | radius × | Use for |
|------|-----------|-------|------|----------|---------|
| compact | 0.72 | 0.78 | 0.8125rem | 0.85 | Information-dense — tables, IDEs, dashboards |
| comfortable | 1 | 1 | 0.9375rem | — | Default — most product UI |
| spacious | 1.35 | 1.3 | 1rem | 1.15 | Editorial — marketing, long-form, settings |

### Motion

**Signature — Hard cut.** No animation. Transitions are cuts — the state switches, the eye follows.
Brutalism means no softening.

```css
transition: none;
```

| Token | Value |
|-------|-------|
| duration.instant | `0ms` |
| duration.fast | `50ms` |
| duration.base | `100ms` |
| duration.slow | `150ms` |
| easing.standard | `linear` |
| easing.decelerate | `linear` |
| easing.accelerate | `linear` |
| easing.spring | `steps(3, end)` |

### Elevation

Five-level scale, system-specific recipe.

| Level | Shadow | Recipe |
|-------|--------|--------|
| level0 | `none` | Flat — the border carries the separation. |
| level1 | `2px 2px 0 0 #000000` | Hard offset 2/2, no blur. |
| level2 | `4px 4px 0 0 #000000` | Hard offset 4/4 — cards. |
| level3 | `6px 6px 0 0 #000000` | Hard offset 6/6 — dialogs. |
| level4 | `8px 8px 0 0 #000000` | Hard offset 8/8 — modals, thicker border. |

### Content

- **measure:** `64ch` (max line length for body prose)
- **paragraph spacing:** `1.2em`
- **list indent:** `1.5em`
- **list gap:** `0.5em`
- **link:** color `#000000`, underline `always`
- **blockquote:** border `4px solid #000000`, padding `0.8em 1em`
- **code:** background `#000000`, color `#FFFFFF`

### Accessibility (WCAG 2.1)

**Overall:** AAA

| Pair | Ratio | Required | Grade | Suggested fix |
|------|-------|----------|-------|---------------|
| Body text on surface | 21:1 | AA | AAA | — |
| Body text on canvas | 21:1 | AA | AAA | — |
| Muted text on surface | 7.46:1 | AA | AAA | — |
| Accent on surface | 21:1 | AA-Large | AAA | — |
| Accent on canvas | 21:1 | AA-Large | AAA | — |

---

# Part 2 · Engineering standards

Generic production practices. They apply regardless of which design system is loaded — but the
examples below are written in Mono Brutalist so you can copy them directly.

## Token wiring — do this first

Declare tokens **once** as CSS custom properties, then never write a raw hex in a component again.
Every rule in Part 1 is enforceable only if there is a single place the values live.

```css
/* app/globals.css — the only file with literal token values */
:root {
  /* color */
  --color-primary:   #000000;
  --color-secondary: #555555;
  --color-tertiary:  #000000;
  --color-neutral:   #ffffff;
  --color-surface:   #ffffff;
  --color-danger:    #b91c1c;      /* error state only — from Pro tokens */

  /* type */
  --font-display: "JetBrains Mono", ui-monospace, monospace;
  --font-body:    "JetBrains Mono", ui-monospace, monospace;
  --font-mono:    "JetBrains Mono", ui-monospace, monospace;
  --tracking-ui:  0.08em;
  --tracking-tab: 0.1em;

  /* radius */
  --radius-sm: 0px;
  --radius-md: 0px;
  --radius-lg: 0px;

  /* space — 8px grid */
  --space-1: 8px;  --space-2: 16px; --space-3: 24px;
  --space-4: 32px; --space-6: 48px; --space-10: 80px;   /* section rhythm */

  /* border */
  --border: 2px solid var(--color-primary);

  /* elevation */
  --level-0: none;
  --level-1: 2px 2px 0 0 var(--color-primary);
  --level-2: 4px 4px 0 0 var(--color-primary);
  --level-3: 6px 6px 0 0 var(--color-primary);
  --level-4: 8px 8px 0 0 var(--color-primary);

  /* motion — hard cut */
  --duration-fast: 50ms;
  --duration-base: 100ms;
  --easing: linear;
}
```

Rules:

- A literal hex outside this file is a bug. Grep for `#[0-9a-fA-F]{6}` in `src/` before you ship.
- If a value you need has no token, **stop and ask** — do not add one silently.
- Tailwind users: map these into `theme.extend` in `tailwind.config.ts` so utilities resolve to the
  same variables. Do not use Tailwind's default palette (`gray-500`, `blue-600`) — it is a second,
  competing design system.

## Project structure

Organize by **feature**, not by file type. `components/`, `hooks/`, `utils/` as top-level buckets stop
scaling the moment there are more than ~20 files.

```
src/
  app/                    # routes / pages — thin, composition only
  features/
    checkout/
      components/         # feature-local UI
      hooks/              # feature-local state + effects
      api.ts              # network calls for this feature
      types.ts
      index.ts            # public surface — import from here, never deeper
  components/ui/          # cross-feature primitives: Button, Card, Tabs, Input
  lib/                    # framework-agnostic helpers, api client, formatters
  styles/globals.css      # the token file above
```

- **Import discipline** — features import from `components/ui` and `lib` freely; a feature must never
  reach into another feature's internals. Cross-feature needs get lifted to `components/ui` or `lib`.
- **One component per file**, named the same as the file. Colocate the test as `Button.test.tsx`.
- **Barrel files only at feature boundaries** (`features/*/index.ts`) — barrels everywhere else wreck
  tree-shaking and create import cycles.

## Components

Write primitives once, in `components/ui`, driven by a variant prop. Do not restyle a button inline.

```tsx
// components/ui/Button.tsx
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";

const button = cva(
  // shared: sharp, uppercase, mono, hard-cut transition
  "inline-flex items-center justify-center gap-2 font-mono font-bold uppercase " +
    "tracking-[var(--tracking-ui)] rounded-none transition-none " +
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[3px] " +
    "focus-visible:outline-[var(--color-primary)] " +
    "disabled:opacity-40 disabled:grayscale-[0.4] disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--color-primary)] text-[var(--color-neutral)] border-2 border-[var(--color-primary)] px-6 py-3 " +
          "hover:shadow-[var(--level-2)] hover:-translate-x-0.5 hover:-translate-y-0.5 " +
          "active:shadow-none active:translate-x-0 active:translate-y-0",
        secondary:
          "bg-[var(--color-surface)] text-[var(--color-primary)] border-2 border-[var(--color-primary)] px-6 py-3 " +
          "hover:shadow-[var(--level-2)] hover:-translate-x-0.5 hover:-translate-y-0.5 " +
          "active:shadow-none active:translate-x-0 active:translate-y-0",
        outline:
          "bg-transparent text-[var(--color-primary)] border-2 border-dashed border-[var(--color-primary)] px-6 py-3",
        ghost:
          "bg-transparent text-[var(--color-primary)] border-none px-0 py-2.5 hover:underline",
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

Principles this encodes, which apply to every primitive you write:

- **Variants, not props soup.** No `isBig`, `isDark`, `hasBorder`. One `variant` union that maps to the
  declared set. A fifth variant requires the user's sign-off.
- **Forward the ref and spread the rest.** Primitives must be composable with focus management,
  tooltips, and form libraries.
- **Extend the native element's props type** so `type="submit"`, `aria-*`, and `onClick` just work.
- **Style via `className`, never inline `style`,** except for genuinely dynamic values.
- **Never accept a `color` prop.** That is how a design system leaks.

## State management

Pick the smallest tool that works, in this order:

1. **Local `useState`** — state one component owns.
2. **Lift to the nearest common parent** — state two siblings share.
3. **URL search params** — filters, tabs, pagination, sort. Anything a user should be able to link to
   or refresh into. This is the most under-used option; reach for it before context.
4. **Context** — genuinely app-wide and rarely-changing (theme, auth session, locale). Split
   fast-changing values into their own provider so you don't rerender the tree on every keystroke.
5. **A store (Zustand/Jotai)** — only when several distant subtrees write to the same state.

Server data is **not** client state. It's a cache. Use TanStack Query (or the framework's data layer)
and stop copying fetched data into `useState`.

```tsx
const { data, isPending, error } = useQuery({
  queryKey: ["orders", { status }],   // every input in the key
  queryFn: () => api.listOrders({ status }),
  staleTime: 30_000,
});
```

- **Derive, don't sync.** If a value is computable from props or existing state, compute it during
  render. An effect that mirrors one state into another is almost always a bug.
- **Effects are for external systems** — subscriptions, timers, imperative DOM, analytics. Not for
  transforming data.
- Always render all three states: pending, error, empty. A screen that only handles the happy path
  is unfinished.

## Data fetching and errors

- One typed API client in `lib/api.ts`. Components never call `fetch` directly.
- Validate untrusted responses at the boundary with a schema (Zod). Parse once, then trust the type.
- Every mutation reports outcome: disable the trigger, show `aria-busy`, surface failures inline.
  Silent failure is the worst outcome.
- Wrap each route in an error boundary with a real recovery action.
- Abort in-flight requests on unmount / superseded input (`AbortController`) so stale responses can't
  overwrite fresh ones.

```ts
// lib/api.ts
export async function apiFetch<T>(path: string, schema: ZodSchema<T>, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return schema.parse(await res.json());
}
```

## Forms

- Use a controlled form library (React Hook Form) with schema validation (Zod) — one schema, shared
  with the API types.
- Validate on blur, revalidate on change **after** the first error. Never validate on every keystroke
  from the start.
- Every input has a real `<label>` (not a placeholder). Placeholders disappear and fail low-vision users.
- Errors are wired with `aria-invalid` + `aria-describedby`, and use the declared error tokens:
  `2px solid #B91C1C` border with `4px 4px 0 0 #B91C1C` shadow.
- Disable the submit button while submitting; never on invalid — the user needs the errors.

## Accessibility

Non-negotiable, checked per screen:

- **Semantic HTML first.** `<button>`, `<a href>`, `<nav>`, `<main>`, one `<h1>`, no skipped heading levels.
- **Keyboard complete.** Every interactive element reachable by Tab, operable by Enter/Space, in a
  logical order. Tabs use arrow keys. Modals trap focus and restore it on close.
- **Visible focus always.** This system's focus ring (`2px solid #000000`, offset `3px`) is part of the
  design — never `outline: none` without an equal replacement.
- **Hit targets ≥ 44×44px**, including icon buttons. Pad rather than scale.
- **Icons need labels.** Icon-only controls get `aria-label`; decorative icons get `aria-hidden="true"`.
- **Respect `prefers-reduced-motion`.** Trivial here — the system is already `transition: none` — but
  any exception you add must be gated.
- Contrast is already AAA per the table above. Keep it that way: `#555555` is for de-emphasized meta
  only, never body copy on a non-white surface.

## Performance

Correctness first, then measure. In practical priority order:

1. **Ship less JS.** Route-level code splitting; dynamic-import heavy dependencies (charts, editors,
   date pickers). Check bundle size before adding a dependency.
2. **Stable lists.** Keys are stable IDs, never array indices for reorderable/filterable lists.
3. **Virtualize long lists** (>100 rows) with TanStack Virtual. Do this before micro-optimizing renders.
4. **Memoize only after profiling.** `useMemo`/`useCallback`/`memo` on everything adds cost and noise.
   Find the actual rerender in React DevTools Profiler first.
5. **Images:** explicit `width`/`height` to prevent layout shift, modern formats, lazy-load below the fold.
6. **Fonts:** `preconnect` + `display=swap` (already in the font link) and subset if you control hosting.
   JetBrains Mono at four weights is the whole type budget — don't add a fifth.

## TypeScript

- `strict: true`. No `any` — use `unknown` and narrow. No non-null `!` without a comment justifying it.
- Model props as discriminated unions so impossible states don't typecheck:
  `{ status: "loading" } | { status: "error"; error: Error } | { status: "ready"; data: T }`.
- Derive types from schemas (`z.infer`) rather than hand-writing a parallel interface that will drift.
- Export component prop types when a component is meant to be wrapped.

## Testing

- **React Testing Library**, queried by role and accessible name — `getByRole("button", { name: /save/i })`.
  If a query is hard to write, the markup is probably inaccessible.
- **Never** test implementation details (state internals, class names, token hexes). Test what the user
  sees and can do.
- Mock at the network boundary (MSW), not by stubbing your own modules.
- Cover the three states you rendered: pending, error, empty — plus one keyboard-only path per flow.

## Definition of done

A screen isn't done until:

- [ ] Part 1's verify checklist passes — no invented values, all four button variants correct.
- [ ] No literal hex outside `globals.css`.
- [ ] Pending, error, and empty states all render.
- [ ] Full keyboard traversal works, with a visible focus ring on every stop.
- [ ] Typechecks and lints clean; tests cover the primary flow.
- [ ] Responsive from 360px to wide — nothing scrolls horizontally that shouldn't.
