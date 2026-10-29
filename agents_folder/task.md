# i-Netra Verbatim UI Port — Task List

Source of truth for the UI port from `demo_ui/` (Milestone 1 clickable
prototype) into the React app (`frontend/`). Mark each task ✅ when done and
date it. Work screen-by-screen; every screen must be visually identical to the
prototype before being marked complete.

Prototype reference assets:
- `frontend/public/prototype/i-netra.html` — verbatim prototype (embedded, tab "i-Netra (Demo UI)")
- `frontend/prototype/unpacked-tpl/` — extracted per-screen templates + controller (`.unpacked` in /tmp/opencode/unpacked2 if present)
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
- ☐ 2.2 **Live view** (`live`): 1 + 5 layout, area tabs, camera picker,
  latest-events rail, detection boxes, full-screen wall + page cycling.
- ☐ 2.3 **Search** (`search`): Cards / List / Timeline / Calendar views remembered
  per person, camera + type filters, time strip picker, recent searches,
  select-all per hour.
- ☐ 2.4 **Cameras** (`cameras`): picture grid, list + areas views, add cameras
  flow (`addcams`), remove/confirm flows.
- ☐ 2.5 **Clip player** (`search` single-clip state): player strip, Copy link,
  full size, keyboard shortcuts (Space, arrows, F, 1 2 4 8).
- ☐ 2.6 **Settings** (`settings` sections storage / space / capacity / users /
  about), disk-full and refused flows.
- ☐ 2.7 **Onboarding / Get cameras working** flow (scan, add, checklist).
- ☐ 2.8 **Access denied / offline / disk full / session expired overlays**.

## Phase 3 — Shared components

- ☐ 3.1 `components/ui/` primitives extracted as screens are ported: Buttons,
  Chips/Badges, Dialog, Dropdown/Menu, Toast, Tabs, Toggle, Card.
- ☐ 3.2 Charts + timeline components (spans, lane chart, hour strip).
- ☐ 3.3 Event card / camera tile / person chip components.

## Phase 4 — Cleanup

- ☐ 4.1 Retire the "i-Netra (Demo UI)" iframe tab once all screens verbatim.
- ☐ 4.2 Remove prototype bundles from `public/prototype/` if no longer needed.
- ☐ 4.3 Keep `Prototype controls` panel out of final UI (dev-only or removed).

---

### Notes
- Backend wiring is explicitly deferred; every interaction uses `invr-data.js`
  sample data so all screens/states stay clickable.
- Visual acceptance: side-by-side against `All screens board.html` states.
