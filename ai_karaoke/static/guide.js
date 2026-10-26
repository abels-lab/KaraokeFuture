// Control panel: guide-vocal volume (how loud the original singer plays along).
// The host's own value is remembered on this laptop (until moved: the Settings page default).
// A singer may choose a volume for their song on their phone: that wins while it plays, and
// moving the slider then changes only this song — the host's remembered value stays as it was.
// Needs common.js; the page has #voc, #guide, #guide-value and #guide-note.
const Guide = (() => {
  let songValue = null;   // the playing song's own volume, or null = the host's value
  let dragging = false;
  let hostLockedUid = null;
  const hostValue = () => Number(store("guideVolume") ?? Settings.get("guide_default", 20));

  function show(v) {
    const clamped = Math.max(0, Math.min(100, Math.round(Number(v) || 0)));
    const voc = $("voc");
    if (voc) voc.volume = clamped / 100;
    const guide = $("guide");
    if (guide && !dragging) guide.value = clamped;
    const val = $("guide-value");
    if (val) val.textContent = `${clamped}%`;
    const note = $("guide-note");
    if (note) note.classList.toggle("hidden", songValue === null);
  }

  function moved(v) {
    const val = Math.max(0, Math.min(100, Math.round(Number(v) || 0)));
    if (typeof current !== "undefined" && current?.uid) {
      hostLockedUid = current.uid;
      songValue = val;
    } else {
      store("guideVolume", String(val));
    }
    show(val);
  }

  return {
    // A song starts or its singer changed their choice (entry.guide: 0-100 or null)
    forEntry(entry) {
      if (!entry) {
        hostLockedUid = null;
        songValue = null;
        show(hostValue());
        return;
      }
      if (hostLockedUid && hostLockedUid === entry.uid) {
        // Song is host-overridden; preserve the host's slider setting
        show(songValue ?? hostValue());
        return;
      }
      hostLockedUid = null;
      songValue = Number.isFinite(entry.guide) ? entry.guide : null;
      show(songValue ?? hostValue());
    },
    moved,
    setDragging(val) { dragging = Boolean(val); },
    isDragging() { return dragging; },
    isHostLocked(uid) { return Boolean(uid && hostLockedUid === uid); },
    lockHost(uid) { hostLockedUid = uid; },
    refresh() { show(songValue ?? hostValue()); }, // the Settings page default changed
  };
})();

Settings.onChange(Guide.refresh);

(() => {
  const guideInput = $("guide");
  if (!guideInput) return;

  const startDrag = () => {
    Guide.setDragging(true);
  };
  const endDrag = () => {
    if (Guide.isDragging()) {
      Guide.setDragging(false);
      Guide.moved(Number(guideInput.value));
    }
  };

  guideInput.addEventListener("pointerdown", startDrag);
  guideInput.addEventListener("mousedown", startDrag);
  guideInput.addEventListener("touchstart", startDrag, { passive: true });

  guideInput.addEventListener("input", (e) => {
    Guide.setDragging(true);
    const v = Number(e.target.value);
    const clamped = Math.max(0, Math.min(100, Math.round(v)));
    const voc = $("voc");
    if (voc) voc.volume = clamped / 100;
    const val = $("guide-value");
    if (val) val.textContent = `${clamped}%`;
    Guide.moved(v);
  });

  guideInput.addEventListener("change", endDrag);
  guideInput.addEventListener("pointerup", endDrag);
  guideInput.addEventListener("mouseup", endDrag);
  guideInput.addEventListener("touchend", endDrag);
  window.addEventListener("pointerup", endDrag);
  window.addEventListener("mouseup", endDrag);
})();
