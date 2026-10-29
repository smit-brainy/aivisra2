# i-Netra Milestone 1 prototype (verbatim UI source)

These are the verbatim self-extracting prototype HTML files (UI only — fictional
sample data, no backend needed). They are embedded full-screen in the app from
`src/pages/inetra/IIntraPrototype.jsx` (tab "i-Netra (Demo UI)").

- `i-netra.html`   — entry prototype (sign-in → all screens, prototype controls)
- `colour-roles.html` — the design-system colour reference page

Fonts in `/public/fonts/*.woff2` and the design tokens in
`src/styles/fonts.css` + `src/styles/foundations.css` were extracted from this
prototype (IBM Plex family, `--ink/--paper/--blue`… tokens).

## Ongoing port plan
Move from the verbatim iframe into real React screens screen-by-screen into
`src/pages/` (auth, home, search, cameras, settings, clip) while keeping
reusable pieces in `src/components/`. Keep this folder as the visual
source-of-truth until a screen is fully ported, then remove that screen's
dependency.
