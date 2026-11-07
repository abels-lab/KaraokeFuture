// Modal dialog for importing custom / unofficial songs via audio file upload or external link.
// Works across the host app and guest remote.
// Needs common.js (el, api, fail, toast, fmt), auth.js, ui/popup.js.
// CustomSongModal.open({ onQueued, onSaved, defaultUrl, singerName }) -> { close }
const CustomSongModal = (() => {
  function open({ onQueued = null, onSaved = null, defaultUrl = "", singerName = "" } = {}) {
    const root = el("div", "space-y-4");
    root.innerHTML = `
      <!-- Source Tabs -->
      <div class="flex rounded-xl bg-white/5 p-1 text-sm font-semibold">
        <button data-k="tab-file" type="button" class="flex-1 rounded-lg py-2 transition bg-amber-400 text-stone-950 shadow">
          📁 Audio File
        </button>
        <button data-k="tab-link" type="button" class="flex-1 rounded-lg py-2 transition text-stone-300 hover:text-white">
          🔗 Web Link
        </button>
      </div>

      <!-- File Upload Tab -->
      <div data-k="pane-file" class="space-y-3">
        <div data-k="dropzone" class="relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-white/20 bg-black/30 p-6 text-center transition hover:border-amber-400/60 hover:bg-black/50">
          <input data-k="file-input" type="file" accept="audio/*,.mp3,.wav,.flac,.m4a,.ogg,.opus" class="absolute inset-0 cursor-pointer opacity-0">
          <span class="text-3xl mb-1">🎵</span>
          <p data-k="dropzone-text" class="text-sm font-semibold text-stone-200">
            Click or drag & drop audio file here
          </p>
          <p class="mt-1 text-xs text-stone-400">MP3, WAV, FLAC, M4A, OGG, OPUS (up to 100 MB)</p>
        </div>

        <div class="flex items-center justify-between text-xs text-stone-400 px-1">
          <span>Optional lyrics file (.lrc or .txt):</span>
          <label class="cursor-pointer text-amber-400 hover:underline">
            <span>Upload lyrics file</span>
            <input data-k="lyrics-file-input" type="file" accept=".lrc,.txt" class="hidden">
          </label>
        </div>
        <p data-k="lyrics-filename" class="text-xs text-stone-300 hidden px-1"></p>
      </div>

      <!-- Web Link Tab -->
      <div data-k="pane-link" class="space-y-3 hidden">
        <div class="flex gap-2">
          <input data-k="link-url" type="url" placeholder="Paste YouTube, SoundCloud, or direct audio link…"
                 class="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/50 px-4 py-2.5 text-sm outline-none focus:border-amber-400">
          <button data-k="link-probe-btn" type="button" class="rounded-xl bg-white/10 px-4 py-2.5 text-xs font-semibold text-stone-200 hover:bg-white/20">
            Inspect
          </button>
        </div>
        <div data-k="link-preview" class="hidden panel flex gap-3 p-3 items-center">
          <img data-k="link-thumb" src="/static/img/microphone.png" alt="" class="h-16 w-24 shrink-0 rounded-lg object-cover">
          <div class="min-w-0 flex-1 text-xs">
            <p data-k="link-title" class="font-bold text-sm text-stone-100 truncate"></p>
            <p data-k="link-artist" class="text-stone-400 truncate"></p>
            <p data-k="link-dur" class="text-gold mt-1"></p>
          </div>
        </div>
      </div>

      <!-- Shared Song Info -->
      <div class="space-y-3 pt-1 border-t border-white/10">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label class="block">
            <span class="text-xs font-semibold text-stone-400">Song Title *</span>
            <input data-k="title-input" maxlength="150" placeholder="e.g. Bohemian Rhapsody"
                   class="mt-1 w-full rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-sm outline-none focus:border-amber-400">
          </label>
          <label class="block">
            <span class="text-xs font-semibold text-stone-400">Artist / Channel</span>
            <input data-k="artist-input" maxlength="100" placeholder="e.g. Queen"
                   class="mt-1 w-full rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-sm outline-none focus:border-amber-400">
          </label>
        </div>

        <!-- Optional Lyrics accordion -->
        <details data-k="lyrics-details" class="group rounded-xl border border-white/10 bg-black/30 p-2.5">
          <summary class="flex cursor-pointer items-center justify-between text-xs font-semibold text-stone-300">
            <span>📝 Paste Lyrics or LRC Timestamps (optional)</span>
            <span class="text-amber-400 group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div class="mt-2 space-y-1">
            <textarea data-k="lyrics-textarea" rows="4" placeholder="Paste lyrics text here. If LRC timestamps like [01:23.45] are included, they anchor word timing automatically."
                      class="w-full rounded-lg border border-white/10 bg-black/60 p-2 text-xs outline-none focus:border-amber-400"></textarea>
            <p class="text-[11px] text-stone-400">If omitted, AI will transcribe vocals or find lyrics online automatically.</p>
          </div>
        </details>

        <!-- Singer Name (for Queueing) -->
        <label data-k="singer-row" class="block">
          <span class="text-xs font-semibold text-stone-400">Singer Name (when adding to Queue)</span>
          <input data-k="singer-input" maxlength="32" placeholder="e.g. Freddie"
                 class="mt-1 w-full rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-sm outline-none focus:border-amber-400">
        </label>
      </div>

      <!-- Upload Progress -->
      <div data-k="progress-box" class="hidden space-y-1 py-1">
        <div class="flex justify-between text-xs font-semibold">
          <span data-k="progress-status" class="text-amber-400">Uploading audio…</span>
          <span data-k="progress-pct" class="text-stone-300">0%</span>
        </div>
        <div class="h-2 w-full overflow-hidden rounded-full bg-white/10">
          <div data-k="progress-bar" class="h-full w-0 rounded-full bg-gradient-to-r from-amber-400 to-amber-600 transition-all duration-200"></div>
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="flex flex-wrap gap-2 pt-2 justify-end">
        <button data-k="btn-cancel" type="button" class="rounded-xl bg-white/10 px-4 py-2 text-xs font-semibold text-stone-300 hover:bg-white/20">
          Cancel
        </button>
        <button data-k="btn-library" type="button" class="rounded-xl border border-amber-400/40 bg-amber-500/10 px-4 py-2 text-xs font-semibold text-gold hover:bg-amber-500/20">
          📚 Save to Library
        </button>
        <button data-k="btn-queue" type="button" class="btn-gold rounded-xl px-5 py-2 text-xs font-bold">
          🎤 Add to Queue
        </button>
      </div>`;

    const popup = Popup.open({ title: "Custom Song (File / Link)", content: root, size: "md" });
    const part = (k) => root.querySelector(`[data-k="${k}"]`);

    let activeTab = "file";
    let selectedAudioFile = null;
    let selectedLyricsFile = null;

    // Prefill singer name
    const { admin, guest } = Auth.me;
    const initialSinger = singerName || (admin ? store("host_singer") || guest?.name || "" : guest?.name || "");
    part("singer-input").value = initialSinger;

    // Switch Tabs
    function setTab(tab) {
      activeTab = tab;
      const isFile = tab === "file";
      part("tab-file").className = `flex-1 rounded-lg py-2 transition ${isFile ? "bg-amber-400 text-stone-950 shadow" : "text-stone-300 hover:text-white"}`;
      part("tab-link").className = `flex-1 rounded-lg py-2 transition ${!isFile ? "bg-amber-400 text-stone-950 shadow" : "text-stone-300 hover:text-white"}`;
      part("pane-file").classList.toggle("hidden", !isFile);
      part("pane-link").classList.toggle("hidden", isFile);
    }
    part("tab-file").onclick = () => setTab("file");
    part("tab-link").onclick = () => setTab("link");

    // File input selection
    function handleFileSelected(file) {
      if (!file) return;
      selectedAudioFile = file;
      const mb = (file.size / (1024 * 1024)).toFixed(1);
      part("dropzone-text").textContent = `Selected: ${file.name} (${mb} MB)`;
      part("dropzone").classList.add("border-amber-400", "bg-amber-500/10");
      if (!part("title-input").value.trim()) {
        const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ");
        part("title-input").value = cleanName;
      }
    }

    part("file-input").onchange = (e) => {
      handleFileSelected(e.target.files?.[0]);
    };

    // Drag and drop events
    const dropzone = part("dropzone");
    dropzone.ondragover = (e) => { e.preventDefault(); dropzone.classList.add("border-amber-400"); };
    dropzone.ondragleave = () => { dropzone.classList.remove("border-amber-400"); };
    dropzone.ondrop = (e) => {
      e.preventDefault();
      dropzone.classList.remove("border-amber-400");
      if (e.dataTransfer?.files?.length) {
        handleFileSelected(e.dataTransfer.files[0]);
      }
    };

    // Lyrics file
    part("lyrics-file-input").onchange = (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      selectedLyricsFile = file;
      part("lyrics-filename").textContent = `Selected lyrics: ${file.name}`;
      part("lyrics-filename").classList.remove("hidden");
    };

    // Link Probe
    async function probeCurrentLink() {
      const url = part("link-url").value.trim();
      if (!url) return;
      part("link-probe-btn").disabled = true;
      part("link-probe-btn").textContent = "Inspecting…";
      try {
        const info = await api("/api/custom/probe", { method: "POST", body: { url } });
        part("link-preview").classList.remove("hidden");
        part("link-title").textContent = info.title;
        part("link-artist").textContent = info.artist || "Unknown artist";
        part("link-dur").textContent = info.duration ? fmt(info.duration) : "";
        if (info.thumbnail) part("link-thumb").src = info.thumbnail;
        if (!part("title-input").value.trim()) part("title-input").value = info.title;
        if (!part("artist-input").value.trim() && info.artist) part("artist-input").value = info.artist;
      } catch (err) {
        fail(err);
      } finally {
        part("link-probe-btn").disabled = false;
        part("link-probe-btn").textContent = "Inspect";
      }
    }

    part("link-probe-btn").onclick = probeCurrentLink;
    part("link-url").onblur = () => {
      if (part("link-url").value.trim() && part("link-preview").classList.contains("hidden")) {
        probeCurrentLink();
      }
    };

    if (defaultUrl) {
      setTab("link");
      part("link-url").value = defaultUrl;
      probeCurrentLink();
    }

    // Submit Action (target = "queue" | "library")
    async function submit(target) {
      const title = part("title-input").value.trim();
      const artist = part("artist-input").value.trim();
      const lyrics = part("lyrics-textarea").value.trim();
      const singer = part("singer-input").value.trim();

      if (target === "queue" && !singer && !Auth.me.guest && !Auth.me.admin) {
        toast("Please log in or enter a singer name first", false);
        return;
      }

      setSubmitting(true);
      try {
        if (activeTab === "file") {
          if (!selectedAudioFile) {
            toast("Please select an audio file first", false);
            setSubmitting(false);
            return;
          }
          await uploadFile(target, { title, artist, lyrics, singer });
        } else {
          const url = part("link-url").value.trim();
          if (!url) {
            toast("Please enter a web link", false);
            setSubmitting(false);
            return;
          }
          await submitLink(target, { url, title, artist, lyrics, singer });
        }
      } catch (err) {
        setSubmitting(false);
        fail(err);
      }
    }

    function setSubmitting(busy) {
      part("btn-queue").disabled = busy;
      part("btn-library").disabled = busy;
      part("btn-cancel").disabled = busy;
    }

    function uploadFile(target, { title, artist, lyrics, singer }) {
      return new Promise((resolve, reject) => {
        const formData = new FormData();
        formData.append("file", selectedAudioFile);
        if (selectedLyricsFile) formData.append("lyrics_file", selectedLyricsFile);
        if (lyrics) formData.append("lyrics_text", lyrics);
        if (title) formData.append("title", title);
        if (artist) formData.append("artist", artist);
        formData.append("target", target);
        formData.append("singer", singer);

        part("progress-box").classList.remove("hidden");
        part("progress-status").textContent = "Uploading audio file…";

        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/custom/upload");
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            part("progress-pct").textContent = `${pct}%`;
            part("progress-bar").style.width = `${pct}%`;
            if (pct >= 100) part("progress-status").textContent = "Processing audio on server…";
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            const res = JSON.parse(xhr.responseText);
            toast(target === "queue" ? `Queued custom song “${res.title}”!` : `Saved “${res.title}” to library!`);
            popup.close();
            if (target === "queue") onQueued?.(res);
            else onSaved?.(res);
            resolve(res);
          } else {
            let msg = "Upload failed";
            try { msg = JSON.parse(xhr.responseText)?.detail || msg; } catch (_) {}
            reject(new Error(msg));
          }
        };

        xhr.onerror = () => reject(new Error("Network error during file upload."));
        xhr.send(formData);
      });
    }

    async function submitLink(target, { url, title, artist, lyrics, singer }) {
      part("progress-box").classList.remove("hidden");
      part("progress-status").textContent = "Ingesting link…";
      part("progress-bar").style.width = "60%";
      part("progress-pct").textContent = "60%";

      const res = await api("/api/custom/link", {
        method: "POST",
        body: { url, title, artist, lyrics_text: lyrics, target, singer }
      });
      part("progress-bar").style.width = "100%";
      part("progress-pct").textContent = "100%";
      toast(target === "queue" ? `Queued custom song “${res.title}”!` : `Saved “${res.title}” to library!`);
      popup.close();
      if (target === "queue") onQueued?.(res);
      else onSaved?.(res);
      return res;
    }

    part("btn-cancel").onclick = popup.close;
    part("btn-queue").onclick = () => submit("queue");
    part("btn-library").onclick = () => submit("library");

    return popup;
  }

  return { open };
})();
