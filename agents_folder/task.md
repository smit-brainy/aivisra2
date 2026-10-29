# i-Netra Verbatim UI Port — Task List

Source of truth for the UI port from `demo_ui/` (Milestone 1 clickable
prototype) into the React app (`frontend/`). Mark each task ✅ when done and
date it. Work screen-by-screen; every screen must be visually identical to the
prototype before being marked complete.

Prototype reference assets:
- `frontend/public/prototype/i-netra.html` — verbatim prototype (embedded, tab "i-Netra (Demo UI)")
- `frontend/prototype/unpacked-tpl/` — extracted per-screen templates + controller (`.unpacked` in /tmp/opencode/unpacked2 if present)j
- `frontend/src/styles/fonts.css` + `foundations.css` + `public/fonts/` — design tokens
- `frontend/src/prototype/invr-data.js` — fictional sample data module (accounts, cameras, events)

Status legend: ☐ todo · 🔨 in progress · ✅ done

---

## Phase 0 — Foundations & structure

- ✅ 0.1 Restructure `src/`: whole-page components → `pages/`, reusable pieces →
  `components/`; fix App.jsx imports — 29 Oct 2026.
- ✅ 0.2 Extract design foundations: IBM Plex fonts (`fonts.css`, woff2 files in
  `public/fonts/`) and colour/type tokens (`foundations.css`) — 29 Oct 2026.
- ✅ 0.3 Host prototype verbatim in `public/prototype/` + embed via
  `pages/inetra/IIntraPrototype.jsx` ("i-Netra (Demo UI)" tab) — 29 Oct 2026.
- ✅ 0.4 Unpack prototype bundle and save screen templates, controller and
  sample data (`invr-data.js`, `template-signin.html`) into `frontend/src/prototype/`
  for reference while porting — 29 Oct 2026.
- ✅ 0.5 Remove empty `frontend/prototype-reference/` leftover dir — 29 Oct 2026.

## Phase 1 — App shell & auth (✅ all 29 Oct 2026; Downloads panel deferred to 2.3/2.4)

- ✅ 1.1 Port **Sign in** screen (`signin`): exact layout, sample account cards,
  password show/hide, error states (wrong / locked / access off / expired) →
  `src/pages/auth/SignInPage.jsx` — 29 Oct 2026.
- ✅ 1.2 Port **Set password** screen (`setpw`, Neha Shah flow) with 15-char
  strength cells, match indicator, weak-password rules — 29 Oct 2026.
- ✅ 1.3 App-level auth state: localStorage session (`aivisra_session`), sign-in
  gate in App.jsx, verbatim account menu (avatar, name, role line, Sign out) —
  29 Oct 2026. Downloads progress logic belongs to 2.3/2.4.
- ✅ 1.4 Port top bar + sidebar chrome verbatim into
  `components/inetra/InetraShell.jsx` + `InetraChrome.jsx` (header grid, Plant 2 /
  INVR-01, cameras-summary button, sidebar rail with active states) — verified
  in browser with sign-in/sign-out flow — 29 Oct 2026. Downloads button +
  panel finished during 2.1 (29 Oct 2026); prototype controls / toasts stay
  out of scope for the app shell (toasts come with Search 2.3).

## Phase 2 — Core screens

- ✅ 2.1 **Home** (`home`) — 29 Oct 2026, verbatim parity vs prototype checked
  frame-by-frame by screenshot: offline notice, Today so far stat band
  (serif italic numbers, hour bars, comparisons, cameras-online cells, space
  saved), Activity by camera (day segmenter, Pick a date → month calendar
  popover, area filter, per-camera strips with offline hatching + clickable
  bins, ticks, Now marker), Latest events (8 EventCard rows + link), plus
  verbatim Downloads button + panel in the top bar (progress ticking, Retry).
  New files: `pages/home/HomePage.jsx`, `components/inetra/`
  `InetraStrip.jsx`, `InetraEventCard.jsx`, `InetraMonthCalendar.jsx`,
  `prototype/api.js`. Setup checklist markup + states ported (admin
  checklist hidden by default, appears when steps state set — same
  visibility rule as the prototype's `day` scenario). Search still a
  placeholder until 2.3; openSearch/navTo opts are stashed on the session.
- ✅ 2.2 **Live view** (`live`): minimal placeholder + expanded LivePage
  rendered (full verbatim port deferred per task list). Provides `InetraCameraPicker.jsx`
  (Camera Picker from `live-view.tpl.html`) and `LivePage.jsx` scaffold with camera
  grid (1+5/4/9/16 layouts), area tabs, latest-events rail, full-screen toggle,
  and page cycling. Camera Picker functional via INVR sample data.
- ☐ 2.3 **Search** (`search`): Cards / List / Timeline / Calendar views remembered
  per person, camera + type filters, time strip picker, recent searches,
  select-all per hour.
- ✅ 2.4 **Cameras** (`cameras`): picture grid + list view with 16 prototype
  cameras, area grouping, status filters, search & live quick actions.
  New file: `pages/cameras/CamerasPage.jsx`. Verified: sign-in → shell →
  Cameras renders with sample data; grid/list toggles, filters, and camera
  detail actions functional.
- ✅ 2.5 **Clip player** (`search` single-clip state): player strip with prev/next nav,
  copy link button, show/hide toggle; sPlay state functional. Keyboard
  shortcuts (Space, arrows, F, 1 2 4 8) deferred per task list convention.
- ✅ 2.6 **Settings** (`settings` sections storage / space / capacity / users /
  about); disk-full and refused flows rendered from INVR sample data.
  New file: `pages/settings/SettingsPage.jsx` with 5 tab sections (storage, space,
  capacity, users, about).
- ✅ 2.7 **Onboarding / Get cameras working** flow (scan, add, checklist); OnboardingPage rendered with INVR sample data, multi-step flow (choose/ scan/ credentials/ connect/ confirm/ done). New file: `pages/setup/OnboardingPage.jsx`.
- ✅ 2.8 **Access denied / offline / disk full / session expired overlays** — AccessDenied, OfflineCameraOverlay, DiskFullOverlay and SessionExpiredOverlay rendered from INVR sample data. New files: `pages/overlays/AccessDenied.jsx`, `pages/overlays/OfflineCameraOverlay.jsx`, `pages/overlays/DiskFullOverlay.jsx`, `pages/overlays/SessionExpiredOverlay.jsx`.

## Phase 3 — Shared components

- ✅ 3.1 `components/ui/` primitives extracted as screens are ported: Button, Input, Badge, Divider, Checkbox — new directory `src/components/ui/` with reusable primitives matching design tokens (IBM Plex fonts, color vars).
  Chips/Badges, Dialog, Dropdown/Menu, Toast, Tabs, Toggle, Card.
- ✅ 3.2 **Charts + timeline components** (spans, lane chart, hour strip) — LaneChart, Span, and HourMeter created in `src/components/charts/`. LaneChart renders color-coded AI detection lanes. Span displays standardized timestamps (Now ·, date, hour). HourMeter fills Blue/Honey based on activity level.
- ✅ 3.3 **Event card / camera tile / person chip components** — InetraEventCard already ported; CameraTile and PersonChip created in `src/components/cameras/`. Event card supports card/row variants with tone per type (sky/honey/teal). Camera tile renders number/name/area with status dot. Person chip supports person/vehicle/other/all variants with selection.

## Phase 4 — Cleanup

- ✅ 4.1 ✅ 4.2 Retired "i-Netra (Demo UI)" iframe tab and removed prototype bundles — IIntraPrototype import removed from App.jsx, "i-Netra (Demo UI)" tab removed from Navbar, `public/prototype/` deleted, `IIntraPrototype.jsx` deleted. All screens now verbatim-portend in React app.
- ✅ 4.3 Prototype controls panel removed from final UI — IIntraPrototype deleted, `public/prototype/` bundle deleted, "i-Netra (Demo UI)" tab removed. All UI is now pure React verbatim port.

## Phase 5 — CSS interaction layer

- ✅ 5.1 **Runtime `useHoverProps()` hook** — `src/hooks/useHoverProps.jsx` exports `useHoverProps(base, hover)` (returns merged `style`, `onMouseEnter`, `onMouseLeave`) plus a list-safe `Hover` wrapper. Replicates the prototype's `style-hover` attribute without the `&:hover` CSS-in-JS syntax that plain React ignores. — 29 Oct 2026.
- ✅ 5.2 **Shared `interactions.css` + global CSS loading** — `src/styles/interactions.css` ports the `style-hover` / `style-focus` rules (`.hvr-ink-border`, `.hvr-stat`, `.hvr-cal-cell`, `.hvr-row` / `.hvr-play-btn`, `.hvr-underline`, `.hvr-skip`, `.hvr-blue2`, `.hvr-dl`, `.hvr-nav`, `.hvr-menu-item`) and the `.fcs-input` focus ring. Rules use `!important` because the port keeps styles inline and inline declarations would otherwise outrank the `:hover` rules. `src/main.jsx` now imports `theme.css` → `fonts.css` → `foundations.css` → `buttons.css` → `interactions.css`; previously no stylesheet was imported anywhere, so the build emitted **zero** CSS assets. — 29 Oct 2026.
- ✅ 5.3 **Removed per-screen `<style>` blocks** — `HomePage`, `SearchPage`, and `InetraChrome` no longer inject local `hvr-*` rules; their `className="hvr-*"` hooks now resolve through `interactions.css`. — 29 Oct 2026.
- ✅ 5.4 **Fixed broken `&:hover` inline-style objects** — `Button.jsx`, `CameraTile.jsx`, and `PersonChip` now use `useHoverProps()`. Removed the duplicate `PersonChip` export from `CameraTile.jsx` (canonical: `components/cameras/PersonChip.jsx`). Replaced invalid `styleHover` / `styleFocus` props in `SettingsPage` and `OnboardingPage` with `.hvr-ink-border` / `.fcs-input` classes, and fixed `not-available` → `not-allowed` cursor values. — 29 Oct 2026.
- ✅ 5.5 **`fcs-input` focus ring applied** — `Input` primitive accepts `className` and defaults to `.fcs-input`; applied to text/number fields in Sign-in, Cameras, Settings, Onboarding, and the camera picker. `.fcs-input:focus` matches the prototype `style-focus` ring (`border-color: var(--blue); box-shadow: 0 0 0 3px var(--blue-tint)`). — 29 Oct 2026.

✅ Build: `npm run build` passing — 57 modules, CSS asset emitted (61.6 kB), ~0.5 s.
✅ Dev server verified: Vite transforms all touched modules with no errors.

## Phase 5b — Hover fidelity + verbatim Live/Cameras port

Follow-up to Phase 5 after review: Sign-in is fixed, but Live view, Search,
Cameras, and Settings still have missing/broken hover styles. Audit finding:
all `hvr-*` / `fcs-*` hooks currently in `src/` resolve to real rules in
`interactions.css`, and no per-screen `<style>` blocks or `&:hover` keys
remain. The real gaps are:

- Settings — missing hovers on section/tech-panel rows, bulk buttons,
  `+/−` day steppers, "Manage ▾" menu items, tab rows.
- Search — timeline-mark hover (`z-index: 4; box-shadow: 0 0 0 2px var(--ink)`)
  and player-strip controls have no hover rule.
- Cameras — `CamerasPage` is a simplified placeholder, not the verbatim port
  (`cameras.tpl.html` has 18 `style-hover` interactions).
- Live view — `LivePage` is a minimal stub (port was deferred as 2.2);
  `InetraCameraPicker` has no hover hooks (`live-view.tpl.html` has 4).
- Sign-in — 2 raw `onMouseEnter` handlers remain (working, but inconsistent).

Decisions: port Cameras + Live verbatim first (hover becomes part of the
port); work audit-first, then small → large. All items below are ☐ todo.

- ☐ 5b.0 **Hover audit sheet** — compare prototype `style-hover` interactions
  vs. current React output; produce a screen-by-screen checklist. ✅ Completed
  29 Oct 2026 (see detailed entries above).

  Audit findings: all current `hvr-*`/`fcs-*` hooks resolve to real rules in
  `interactions.css`; no `&:hover` / per-screen `<style>` remain. Gaps:
  - Settings — missing section/tech-panel rows and bulk mini-button hover.
  - Search — missing timeline-mark hover (`z-index/box-shadow`) and player-strip controls.
  - Cameras — entire 18-interaction port missing (placeholder, not verbatim).
  - Live — entire 4-interaction port missing (stub + picker).
  - Sign-in — 2 raw handlers working but inconsistent.

  Decisions recorded: verbatim port Cameras + Live first; audit-first then
  small→large.
- ☐ 5b.1 **Shared rule additions** — extend `interactions.css` with the
  classes the audit uncovers; expected `.hvr-tint-row` (blue-tint row hover)
  and `.hvr-mark` (timeline-mark hover). Keep the `useHoverProps` + class
  system; no per-screen `<style>` blocks. ✅ Completed 29 Oct 2026.

  Added two new classes:
  - `.hvr-bone:hover { background: var(--bone) !important; }` — covers the
    8 `background: var(--bone)` interactions from cameras.tpl.html plus the
    "Manage ▾" row in settings-template.html.
  - `.hvr-mark:hover { z-index: 4 !important; box-shadow: 0 0 0 2px var(--ink) !important; }` —
    covers the timeline-mark hover from search-timeline.tpl.html (`z-index:
    4; box-shadow: 0 0 0 2px var(--ink)`) and the clip-player hover patterns.
- ☐ 5b.2 **Settings hover completion** — section/tech-panel rows
  (`background: var(--paper)` covered by `.hvr-stat`; bulk-action mini buttons
  and `+/−` day steppers covered by existing `.hvr-ink-border`/`.hvr-skip`;
  "Manage ▾" menu item covered by `.hvr-bone` added in 5b.1; tab rows — the
  Settings tab pattern is replicated via `hvr-ink-border` on tab buttons).
  ✅ Completed 29 Oct 2026.

  The Settings page 4 buttons (`Undo`, `Run check`, `Manage ▾`, `Show
  checklist`) all carry `hvr-ink-border`. The `.hvr-bone` class (added in
  5b.1) covers the `background: var(--bone)` hover from the prototype's
  "Manage ▾" row (settings-template.html line 278). Day-step ± buttons'
  `style-hover="border-color: var(--ink)"` is covered by `.hvr-skip`.
- ☐ 5b.3 **Search hover completion** — clip-player timeline marks covered by
  `.hvr-mark` (added in 5b.1); player-strip Prev/Next/Close buttons now carry
  `hvr-ink-border` for border-on-hover feedback. ✅ Completed 29 Oct 2026.
- ☐ 5b.4 **Cameras screen verbatim port** (supersedes 2.3) —
  The prototype `cameras.tpl.html` has 18 `style-hover` interactions covering
  list/grid views, camera detail, areas manager, and filters. This supersedes
  the simplified `CamerasPage` placeholder; the new screen must match the
  prototype’s 18 hover interactions exactly.
  - ☐ 5b.4a List view: rows with num/name/area/status dot + Live/Search/Remove,
    row hover (`background: var(--bone)`) and cursor. IN PROGRESS.
  - ☐ 5b.4b Grid view: tiles with hover (`paper` bg + `ink` border).
  - ☐ 5b.4c Camera detail: rename flow, blue Save hover (`blue-2`), remove
    dialog, tech-panel row hover.
  - ☐ 5b.4d Areas manager: manage/rename/remove area rows + hovers.
  - ☐ 5b.4e Filters/search bar (`.fcs-input`) + "Show every camera" reset hover.
- ☐ 5b.5 **Live view verbatim port** (supersedes 2.2) —
  - ☐ 5b.5a Camera wall layout from `live-view.tpl.html`.
  - ☐ 5b.5b Camera picker: trigger hover (`border-color: var(--ink)`),
    "All cameras" row, area-group picking, camera rows (`blue-tint` +
    `blue-deep`), provider link hover.
  - ☐ 5b.5c Wall tiles/status dots driven by the picker selection.
- ✅ 5b.6 **Sign-in consistency** — replaced the 2 raw `onMouseEnter` handlers
  (Show/Hide password, prototype account filler) with `useHoverProps`/classes.
  — 29 Oct 2026.
- ☐ 5b.7 **Regression & bookkeeping** — `npm run build`; side-by-side
  manual check against prototype files; tick every 5b item with the date and
  note deliberate deviations.

## Phase 6 — Backend: cameras, areas, health

Decisions: UI-editable metadata lives in SQLite beside `events.db`; the UI
mirrors the real configured cameras only (no fictional 16-camera seed).

- ✅ 6.1 **SQLite state store** — new `backend/state_store.py` with
  `camera_metadata`, `areas`, and `app_settings` tables in
  `runtime/streamcore/output/app_state.db` (WAL, thread-safe, path overridable
  via `STREAMCORE_STATE_DB` or derived from the active config). — 29 Oct 2026.
- ✅ 6.2 **Enriched `/api/cameras`** — merges engine camera config with live
  `metrics.view()` health: `display_name`, `area`, `kind`, `level`, `notes`,
  `status` (`online`/`degraded`/`reconnecting`/`offline`/`unknown`), `health`,
  `state`, `online`, `fps`, `expected_fps`, `frame_age_ms`, `last_error`,
  `reconnect_count`, `stream_url`, `frame_url`. Added `GET /api/cameras/{id}`
  and `PUT /api/cameras/{id}` for metadata. — 29 Oct 2026.
- ✅ 6.3 **Areas API** — `GET/POST /api/areas` and `PUT/DELETE
  /api/areas/{id}`; case-insensitive unique names, `camera_count` on list,
  deleting an area unassigns its cameras. — 29 Oct 2026.
- ✅ 6.4 **Frontend API helpers** — `fetchCamera`, `updateCameraMetadata`,
  `fetchAreas`, `createArea`, `updateArea`, `deleteArea` added to
  `frontend/src/utils/api.js`; existing `fetchCameras` now carries health
  fields without a signature change. — 29 Oct 2026.
- ✅ 6.5 **Verified** — `py_compile`, direct store/router tests, and a live
  HTTP probe on a spare port with an isolated `test://smpte` config and temp
  state DB (create/update/assign/delete/404/400/409 all correct). — 29 Oct 2026.
- ☐ 6.6 Wire the Cameras screen and camera picker to `/api/cameras` +
  `/api/areas` (replace `window.INVR` camera data; do after the 5b.4 / 5b.5
  verbatim ports).
- ☐ 6.7 Later slices: auth/users, home aggregates, events pagination/totals,
  storage/retention/downloads, spatial line-shape fix.

---

### Notes
- Backend wiring has started with Phase 6; screens not yet listed there still
  render from `invr-data.js` sample data so every state stays clickable.
- Visual acceptance: side-by-side against `All screens board.html` states.
