// Shared plumbing for PlotProof's static Streamlit map components
// (utils/shape_georeferencer, utils/map_traverse_sketch,
// utils/image_traverse_sketch) - see DIAGONAL_CALCULATOR_AUDIT.md section 2
// for why this exists: three components independently duplicated the same
// postMessage protocol boilerplate, the same ResizeObserver height fix,
// and (in two of them) the same bearing/distance math - one real bug (a
// missing isStreamlitMessage flag, silently dropped by Streamlit with no
// error) and one latent inconsistency (mismatched bearingDistance()
// calling conventions between the two files that had it) already slipped
// through that duplication before this file existed.
//
// Copied into each component's frontend/ directory at Python import time
// (see utils/_shared_map_component/__init__.py's sync_into()) rather than
// referenced by a relative path - Streamlit serves each
// declare_component() directory in isolation, so there's no way to load a
// file living outside it directly.
(function () {
  const METERS_PER_DEG_LAT = 111320.0;
  let lastHeight = 0;

  function postToStreamlit(payload) {
    window.parent.postMessage(Object.assign({ isStreamlitMessage: true }, payload), "*");
  }

  function sendReady() {
    postToStreamlit({ type: "streamlit:componentReady", apiVersion: 1 });
  }

  function setValue(value) {
    postToStreamlit({ type: "streamlit:setComponentValue", value: value, dataType: "json" });
  }

  function setFrameHeight() {
    const height = document.documentElement.scrollHeight;
    // Skip redundant posts - observeHeight()'s ResizeObserver fires on any
    // observed resize, including ones a component's own drag/label updates
    // cause, so without this guard a single interaction can post the same
    // unchanged height more than once.
    if (height === lastHeight) return;
    lastHeight = height;
    postToStreamlit({ type: "streamlit:setFrameHeight", height: height });
  }

  function observeHeight() {
    // A one-shot setFrameHeight() right after init reads a stale, often-
    // zero height if a component is rendered inside something that starts
    // hidden (e.g. a collapsed st.expander) and only becomes visible
    // later - nothing would ever correct it otherwise. This ResizeObserver
    // on <body> catches the moment a hidden ancestor's collapse actually
    // changes the component's real size (expander opening, markers/labels
    // added or removed, map height itself changing) and reports it fresh.
    new ResizeObserver(() => setFrameHeight()).observe(document.body);
  }

  // Real bearing/distance between two points, using the flat-earth
  // approximation utils/traverse.py's Python side also uses (see that
  // module's own _METERS_PER_DEG_LAT). Accepts either a plain [lat, lon]
  // array or a {lat, lng|lon} object - shape_georeferencer keeps its shape
  // state as arrays, map_traverse_sketch works directly with Leaflet
  // LatLng objects, and normalizing both here (rather than requiring
  // every caller to convert first) is what prevents the silent-NaN risk
  // the two previously-separate copies of this function had.
  function bearingDistance(from, to) {
    const fromLat = Array.isArray(from) ? from[0] : from.lat;
    const fromLng = Array.isArray(from) ? from[1] : (from.lng !== undefined ? from.lng : from.lon);
    const toLat = Array.isArray(to) ? to[0] : to.lat;
    const toLng = Array.isArray(to) ? to[1] : (to.lng !== undefined ? to.lng : to.lon);
    const metersPerDegLon = METERS_PER_DEG_LAT * Math.cos(fromLat * Math.PI / 180);
    const dNorthing = (toLat - fromLat) * METERS_PER_DEG_LAT;
    const dEasting = (toLng - fromLng) * metersPerDegLon;
    const distance = Math.sqrt(dNorthing * dNorthing + dEasting * dEasting);
    let bearing = Math.atan2(dEasting, dNorthing) * 180 / Math.PI;
    bearing = (bearing + 360) % 360;
    return { bearing: bearing, distance: distance };
  }

  // Whole-circle degrees to the plan's own "52°30'" convention - same
  // formula as utils/traverse.py's format_bearing() (kept in sync by hand;
  // there is no shared source between Python and JS).
  function formatBearing(deg) {
    let whole = Math.floor(deg);
    let minutes = Math.round((deg - whole) * 60);
    if (minutes === 60) { whole += 1; minutes = 0; }
    if (whole >= 360) whole -= 360;
    return whole + "°" + String(minutes).padStart(2, "0") + "'";
  }

  // A small pill-shaped map label (see shared.css's .pp-seg-label) for a
  // segment's live bearing/distance readout.
  function segLabelIcon(text) {
    return L.divIcon({ className: "", html: '<div class="pp-seg-label">' + text + "</div>", iconSize: null });
  }

  window.PPMapComponent = {
    sendReady: sendReady,
    setValue: setValue,
    setFrameHeight: setFrameHeight,
    observeHeight: observeHeight,
    bearingDistance: bearingDistance,
    formatBearing: formatBearing,
    segLabelIcon: segLabelIcon,
  };
})();
