// Control panel: guide-vocal volume (how loud the original singer plays along).
// The host's own value is remembered on this laptop (until moved: the Settings page default).
// A singer may choose a volume for their song on their phone: that wins while it plays, and
// moving the slider then changes only this song — the host's remembered value stays as it was.
// Needs common.js; the page has #voc, #guide, #guide-value and #guide-note.
const Guide = (() => {
  let songValue = null;   // the playing song's own volume, or null = the host's value
  const hostValue = () => Number(store("guideVolume") ?? Settings.get("guide_default", 20));

  function show(v) {
    $("voc").volume = v / 100;
    $("guide").value = v;
    $("guide-value").textContent = `${v}%`;
    $("guide-note").classList.toggle("hidden", songValue === null);
  }

  return {
    // A song starts or its singer changed their choice (entry.guide: 0-100 or null)
    forEntry(entry) {
      songValue = Number.isFinite(entry?.guide) ? entry.guide : null;
      show(songValue ?? hostValue());
    },
    moved(v) { // the host dragged the slider
      if (songValue !== null) songValue = v;
      else store("guideVolume", String(v)); // this laptop keeps its own value
      show(v);
    },
    refresh() { show(songValue ?? hostValue()); }, // the Settings page default changed
  };
})();
Settings.onChange(Guide.refresh);
$("guide").oninput = (e) => Guide.moved(Number(e.target.value));
