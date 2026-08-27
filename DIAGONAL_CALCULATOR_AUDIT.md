# Diagonal Calculator — Build Audit

Self-review of the Diagonal Calculator feature and its three custom map
components (`utils/shape_georeferencer/`, `utils/map_traverse_sketch/`,
`utils/image_traverse_sketch/`), covering everything built across this
feature's development: the base calculator, the drag-to-georeference map,
the click-to-sketch map, the image/PDF trace tool, scale-based accurate
distances, and the trace→Sketch transfer + segment labels.

Findings below come from an 8-angle review pass (line-by-line diff,
removed-behavior audit, cross-file tracing, duplication scan,
simplification scan, efficiency scan, altitude/depth scan, project-convention
check) and are organized by what to **fix now**, what to **merge**, and
what to **adjust** later.

**Status: all sections (§1, §2, §3) are done and verified live.**

---

## 1. Fix now (real regressions / bugs)

### 1.1 ✅ `expanded=True` on the georeference picker leaks into Manual Entry tab

`pages/diagonal_calculator.py:506` flips `_render_georeference_picker`'s
expander to `expanded=True`. That function is called from
`_render_legs_editor_and_result()` any time `origin_latlon is None` and
4+ legs exist — which includes the **Manual Entry tab** whenever someone
fills in the bearing/distance table but leaves the optional GPS fields
blank (the normal case). A full interactive Leaflet map now force-opens
there on every rerun (every table edit), which was never the intent — the
fix was aimed only at the Upload-tab fallback flow.

This was added as a belt-and-suspenders fix alongside the `ResizeObserver`
(§1.2) for a component-height bug. Since the `ResizeObserver` is the real,
general fix, **`expanded=True` should be reverted** back to the default
(collapsed) — that removes the Manual Entry regression and resolves the
redundancy noted in §1.2 at the same time.

### 1.2 ✅ `ResizeObserver` fix confirmed working — keep it, and add a change guard

The `ResizeObserver` added to all three components (`shape_georeferencer`,
`map_traverse_sketch`, `image_traverse_sketch`) correctly fixes the
original bug (iframe stuck at height 0 inside a collapsed `st.expander`,
reproduced and verified). Two follow-ups:

- It posts `setFrameHeight()` on **every** observed resize with no
  comparison against the last value sent — including resizes it
  indirectly causes itself (e.g. §1.3's label redraw changes body size,
  which re-triggers the observer, which posts again). Add a `lastHeight`
  cache and only post when the height actually changed:
  ```js
  let lastHeight = 0;
  function setFrameHeight() {
    const height = document.documentElement.scrollHeight;
    if (height === lastHeight) return;
    lastHeight = height;
    window.parent.postMessage({ isStreamlitMessage: true, type: "streamlit:setFrameHeight", height }, "*");
  }
  ```
- The comment in `shape_georeferencer/frontend/index.html` justifies the
  fix by citing the picker's "collapsed by default" — which §1.1's revert
  restores as true, but only *after* that revert. Until then the comment
  and the code disagree (worth fixing in the same pass as §1.1).

### 1.3 ✅ Segment labels redraw on every drag tick, not just drag end

`shape_georeferencer/frontend/index.html`'s `redrawSegmentLabels()` runs
inside `redrawPolygon()`, which runs on every `drag` event — i.e. many
times per second while dragging. Each call destroys and recreates one
`L.divIcon` marker per edge. For a plot with more than a handful of
corners this is visible lag while dragging, compounded by §1.2's
observer re-firing on the same DOM churn.

Fix: update each existing label's position/text in place instead of
destroy-and-recreate, or only do the full rebuild on `dragend` and just
reposition existing labels during `drag`.

### 1.4 ✅ No way to redo a confirmed "Sketch it on a real map" attempt

The method-switch cleanup used to clear `_diag_upload_manual_editor_sketch_result`
so switching methods and back gave a fresh sketch session. That clear was
removed so a completed trace could survive switching to Sketch (the
feature the user asked for) — but as a side effect, **`_render_map_sketch_picker()`
now has no reset path at all**. Once confirmed, `already = session_state.get(result_key)`
returns immediately forever for that file; there's no "start over" button
(unlike the trace picker's "Retrace from scratch").

Failure scenario: click the wrong corners while sketching, confirm anyway,
try to redo it — nothing lets you, short of re-uploading the file.

Fix: give `_render_map_sketch_picker()` the same "Start over" affordance
`_render_image_trace_picker()` already has.

### 1.5 ✅ A trace permanently hijacks "Sketch it on a real map," with no way back

Related to §1.4: once any trace exists for the uploaded file, the Sketch
radio option **always** shows the transferred trace (`if trace_points:` at
`diagonal_calculator.py`), never the live click-to-build map. The only way
to reach the actual click-to-sketch tool again is to switch to the Trace
tab and click "Retrace from scratch" — not discoverable from the Sketch
tab itself, and it destroys the trace to do it.

Fix: add a small "Sketch from scratch instead" link/button inside the
`if trace_points:` branch that clears just `trace_points` (not a full
retrace) and reruns, letting the transfer be undone without losing the
Trace tab's other inputs.

### 1.6 ✅ `formatBearing()` doesn't wrap 360° back to 0°

```js
let whole = Math.floor(deg);
let minutes = Math.round((deg - whole) * 60);
if (minutes === 60) { whole += 1; minutes = 0; }   // no wrap at 360
```
A bearing near due north (e.g. 359.98°) rounds to `whole=359, minutes=60`
→ bumped to `whole=360` → displays **"360°00'"** instead of **"0°00'"**.
Present in both `shape_georeferencer` and `map_traverse_sketch` (copied).
Fix: `if (whole >= 360) whole -= 360;` after the bump, in both files.

### 1.7 ✅ Confirmed map position goes stale if scale/paper size changes afterward

`_render_georeference_picker()` returns its cached `confirmed` dict
immediately once set, ignoring the freshly-recomputed `polygon_en`/`labels`
passed in on later runs. Since the scale/paper-size inputs live in the
Trace expander (not gated by the method-switch reset), a user can confirm
a map position, then go back and tweak the scale — the legs table updates
with new distances, but the confirmed shape on the map stays frozen at the
old (pre-scale-change) geometry. Table and map silently disagree.

Fix: include a hash/fingerprint of the input shape in the cache key (or
just clear `confirmed_key` whenever `_compute_trace_rows()`'s inputs
change), so a scale edit invalidates a stale confirmation the same way a
method switch does.

---

## 2. ✅ Merge (consolidation opportunities)

**Done.** Consolidated into `utils/_shared_map_component/` (`shared.js` +
`shared.css`), copied into each component's `frontend/` directory at
Python import time (`sync_into()`, called from each `__init__.py`) since
Streamlit serves each `declare_component()` path in isolation - there's
no way to reference a file outside it directly. The copies themselves are
gitignored; only the shared source is tracked.

Consolidated: the componentReady/setComponentValue/setFrameHeight
postMessage helpers, the `ResizeObserver` height fix (with the `lastHeight`
change-guard from §1.2), `bearingDistance()` (now genuinely unified - one
implementation that accepts either a plain `[lat, lon]` array or a
`{lat, lng|lon}` object, removing the silent-`NaN` risk the two
previously-separate copies had), `formatBearing()` (with §1.6's wraparound
fix), and `segLabelIcon()`/`.pp-seg-label`. `image_traverse_sketch` (no
Leaflet, no bearing labels) only pulls in the protocol/height helpers, not
the CSS.

Verified: all three components individually (each still renders, computes,
and returns correctly) and the full upload → trace → transfer-to-Sketch →
position → confirm flow end-to-end, with no console errors.

All three components (`shape_georeferencer`, `map_traverse_sketch`,
`image_traverse_sketch`) are independent static `frontend/index.html`
files with **zero shared code** — by design, to avoid a React/webpack
build step (see each `__init__.py`'s docstring). That trade-off is sound
for a single component, but three of them now duplicate real logic:

| Duplicated piece | Files | Risk if left as-is |
|---|---|---|
| Streamlit postMessage protocol (componentReady handshake, `streamlit:render` listener, `setFrameHeight`) | all 3 | Any future protocol fix (this session already found one real bug here — the missing `isStreamlitMessage` flag) needs manual propagation to 3 files |
| `ResizeObserver` fix (§1.2) | all 3 | Same — a 4th component would need the same paste-in |
| `bearingDistance()` | `shape_georeferencer`, `map_traverse_sketch` | **Already inconsistent** — one takes `[lat, lon]` arrays, the other `{lat, lng}` Leaflet objects, despite a comment claiming "same convention." A copy-paste between the two files would silently produce `NaN` |
| `formatBearing()`, `segLabelIcon()`, `.pp-seg-label` CSS | `shape_georeferencer`, `map_traverse_sketch` | Byte-for-byte duplicates; §1.6's bug had to be fixed in both places by hand |

**Suggestion:** pull the protocol boilerplate + `ResizeObserver` +
`bearingDistance`/`formatBearing`/`segLabelIcon`/`.pp-seg-label` into one
shared static file (e.g. `utils/_map_component_shared.js` +
`_map_component_shared.css`), and `<script src="../../_map_component_shared.js">`
it from each component's `index.html`. Streamlit's static component
serving is per-`declare_component`-directory, so this needs either:
- a small script that copies/symlinks the shared file into each
  component's `frontend/` directory at declare-time, or
- serving it from one of the three components' own directory and
  referencing it by relative path from the other two (fragile — breaks if
  any one component's directory is ever removed).

Given the added complexity either way, this is worth doing only once a
**4th** component is added (the "rule of three" already crossed) or the
next time one of the duplicated pieces needs a real fix — not urgent on
its own, but flagged now since the pattern will keep repeating otherwise.

---

## 3. ✅ Adjust (simplification, minor cleanups)

- **`pages/diagonal_calculator.py`, "Sketch it on a real map" branch** —
  the `if trace_points: ... else: sketch = ...; if sketch: ...` nesting
  (4-5 levels deep inside `tab_upload`) duplicates the same
  `_render_legs_editor_and_result(...)` call with slightly different
  inputs in both branches. Flattening to "compute `rows`/`origin_latlon`
  in the if/else, one shared render call at the end" would remove the
  duplication and the extra nesting level in one move.
- **Scale/paper-size keys read via hardcoded strings** — the Sketch branch
  reconstructs `_diag_upload_manual_editor_trace_scale` /
  `_trace_paper_w` / `_trace_paper_h` by hand rather than through any
  shared naming helper with `_render_image_trace_picker()`, which is what
  actually creates those keys. A rename in one place silently breaks the
  other (falls back to defaults, no error). Worth a small shared
  `_trace_widget_keys(key_prefix)` helper returning the three key names.
- **`trace_points` fetched unconditionally** at the top of the fallback
  block even though only the Sketch branch uses it — move the lookup
  inside `elif method == "Sketch it on a real map":` so it reads as
  scoped to where it's consumed.
- **Method-switch invalidation is currently a no-op on new-file-upload** —
  harmless today only because the new-upload handler already clears
  everything unconditionally elsewhere; if that earlier clear is ever
  trimmed, the method-switch block won't catch it (it only fires on an
  actual method change, not a same-method re-upload). Low priority, but
  worth a comment noting the dependency so it isn't trimmed by accident.

---

## Suggested order of work

1. §1.1 + §1.2's comment fix (revert `expanded=True`, fix the now-true
   comment) — one small change, removes a real regression.
2. §1.6 (`formatBearing` wraparound) — trivial, two-line fix in two files.
3. §1.4 + §1.5 (redo/escape affordances for Sketch) — restores behavior
   the earlier cleanup-removal cost, without giving up the trace-transfer
   feature itself.
4. §1.2's `lastHeight` guard + §1.3 (label redraw throttling) — performance,
   not correctness; worth doing together since they compound.
5. §1.7 (stale confirmation on scale change) — edge case, lower priority.
6. §2 (shared JS module) — defer until a real trigger (4th component, or
   next bug in the duplicated code) per the reasoning above.
7. §3 items — cheap cleanups, fine to bundle into whichever of the above
   PRs touches that code anyway.

None of this blocks using the feature as-is today — everything above is
either a rough edge in an already-working flow or a maintenance-cost
observation, not a crash or data-loss bug in the main path (upload →
extract → trace/sketch → position → diagonal).
