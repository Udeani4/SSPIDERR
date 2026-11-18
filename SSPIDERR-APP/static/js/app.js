/* SSPIDERR shared front-end behaviour (replaces the copies that used to live in every template).
 *
 *  - SSPIDERR.fetch(): fetch() that always sends the CSRF token
 *  - SSPIDERR.toast(): small notifications (also used for Flask flash messages)
 *  - "Add to playlist": any element with data-add-track="<spotify track id>" opens the
 *    playlist picker. Playlists are loaded from /api/my-playlists only when needed.
 *  - Only one audio preview plays at a time; broken images fall back to a placeholder.
 */
(function () {
  "use strict";

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const body = document.body;
  const isLoggedIn = body.dataset.loggedIn === "1";
  const loginUrl = body.dataset.loginUrl || "/login-page";
  const createPlaylistUrl = body.dataset.createPlaylistUrl || "/create-playlist";
  const PLACEHOLDER = "/static/img/core-img/track-placeholder.svg";

  function ssFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
    headers.set("Accept", "application/json");
    return fetch(url, { credentials: "same-origin", ...options, headers });
  }

  // ---------------------------------------------------------------- toasts
  const toastBox = document.getElementById("ss-toasts");

  function toast(message, kind = "info", timeout = 5000) {
    if (!toastBox) { console.log(message); return; }
    const el = document.createElement("div");
    el.className = `ss-toast ${kind}`;
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    const text = document.createElement("div");
    text.textContent = message;
    const close = document.createElement("button");
    close.type = "button";
    close.setAttribute("aria-label", "Dismiss");
    close.innerHTML = "&times;";
    el.append(text, close);
    const dismiss = () => { el.classList.add("hide"); setTimeout(() => el.remove(), 300); };
    close.addEventListener("click", dismiss);
    toastBox.appendChild(el);
    if (timeout) setTimeout(dismiss, timeout);
  }

  // Server-side flash messages are rendered into #ss-flashes as JSON.
  try {
    const flashes = JSON.parse(document.getElementById("ss-flashes")?.textContent || "[]");
    flashes.forEach(([category, message]) => toast(message, category === "message" ? "info" : category));
  } catch (e) { /* ignore */ }

  // ---------------------------------------------------------------- playlist picker
  const modal = document.getElementById("ss-playlist-modal");
  const listBox = modal?.querySelector("[data-playlist-list]");
  let playlists = null;            // cached after the first successful load
  let currentTrack = null;
  let lastFocus = null;

  function renderState(html) { if (listBox) listBox.innerHTML = `<div class="ss-modal__state">${html}</div>`; }

  function renderPlaylists() {
    if (!playlists.length) {
      renderState("You don't have any playlists you can add to yet.<br>Create one below.");
      return;
    }
    listBox.innerHTML = "";
    playlists.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ss-pl-item";
      btn.dataset.playlistId = p.id;
      const img = document.createElement("img");
      img.src = p.image || PLACEHOLDER; img.alt = ""; img.loading = "lazy";
      const text = document.createElement("div");
      const name = document.createElement("strong"); name.textContent = p.name;
      const count = document.createElement("small"); count.textContent = `${p.tracks} song${p.tracks === 1 ? "" : "s"}`;
      text.append(name, count);
      btn.append(img, text);
      btn.addEventListener("click", () => addToPlaylist(p, btn));
      listBox.appendChild(btn);
    });
    listBox.querySelector("button")?.focus();
  }

  async function loadPlaylists() {
    if (playlists) { renderPlaylists(); return; }
    renderState('<span class="ss-spinner"></span><p>Loading your playlists...</p>');
    try {
      const res = await ssFetch("/api/my-playlists");
      const data = await res.json();
      if (res.status === 401) { window.location = `${loginUrl}?next=${encodeURIComponent(location.pathname)}`; return; }
      if (res.status === 403 && data.invite_only) {
        const note = document.createElement("div");
        note.className = "ss-modal__state";
        note.textContent = data.error;
        listBox.replaceChildren(note);
        return;
      }
      if (res.status === 403 && data.connect) {
        renderState(`${data.error}<br><br><a class="ss-btn spotify" href="${data.connect}?next=${encodeURIComponent(location.pathname)}">Connect Spotify</a>`);
        return;
      }
      if (!res.ok) throw new Error(data.error || "Couldn't load playlists");
      playlists = data.playlists || [];
      renderPlaylists();
    } catch (err) {
      renderState(`${err.message}<br><br><button type="button" class="ss-btn ghost" data-retry>Try again</button>`);
      listBox.querySelector("[data-retry]")?.addEventListener("click", loadPlaylists);
    }
  }

  async function addToPlaylist(playlist, button) {
    if (!currentTrack) return;
    button.setAttribute("aria-busy", "true");
    try {
      const res = await ssFetch("/add_to_playlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ playlist_id: playlist.id, track_id: currentTrack }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.success) throw new Error(data.error || "Couldn't add that song.");
      playlist.tracks += 1;
      closeModal();
      toast(`Added to “${playlist.name}”`, "success");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      button.removeAttribute("aria-busy");
    }
  }

  function openModal(trackId) {
    if (!isLoggedIn) {
      toast("Log in to add songs to your playlists.", "info");
      setTimeout(() => { window.location = `${loginUrl}?next=${encodeURIComponent(location.pathname)}`; }, 900);
      return;
    }
    if (!modal) return;
    currentTrack = trackId;
    lastFocus = document.activeElement;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    document.documentElement.style.overflow = "hidden";
    loadPlaylists();
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    document.documentElement.style.overflow = "";
    lastFocus?.focus?.();
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-add-track]");
    if (trigger) {
      event.preventDefault();
      if (trigger.dataset.addTrack) openModal(trigger.dataset.addTrack);
      return;
    }
    if (event.target === modal || event.target.closest("[data-close-modal]")) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal?.classList.contains("open")) closeModal();
  });
  modal?.querySelector("[data-create-playlist]")?.addEventListener("click", () => {
    window.location = `${createPlaylistUrl}?next=${encodeURIComponent(location.pathname)}`;
  });

  // ---------------------------------------------------------------- previews
  // Pages contain only <button data-preview="url">. A single Audio object is created on the
  // first click, so loading a page never downloads any audio.
  let player = null;
  let activeButton = null;

  function setButton(btn, state) {
    if (!btn) return;
    btn.classList.toggle("playing", state === "playing");
    btn.classList.toggle("loading", state === "loading");
    btn.setAttribute("aria-pressed", state === "playing" ? "true" : "false");
    const icon = btn.querySelector("i");
    if (icon) icon.className = state === "playing" ? "fa fa-pause" : state === "loading" ? "fa fa-spinner fa-spin" : "fa fa-play";
    if (state === "idle") btn.style.removeProperty("--ss-progress");
  }

  function stopPreview() {
    if (player) { player.pause(); player.removeAttribute("src"); player.load(); }
    setButton(activeButton, "idle");
    activeButton = null;
  }

  function getPlayer() {
    if (player) return player;
    player = new Audio();
    player.preload = "none";
    player.addEventListener("playing", () => setButton(activeButton, "playing"));
    player.addEventListener("waiting", () => setButton(activeButton, "loading"));
    player.addEventListener("ended", stopPreview);
    player.addEventListener("error", () => {
      if (!player.getAttribute("src")) return;          // error from clearing src on stop
      toast("That preview couldn't be played.", "error");
      stopPreview();
    });
    player.addEventListener("timeupdate", () => {
      if (activeButton && player.duration) {
        activeButton.style.setProperty("--ss-progress", `${(player.currentTime / player.duration) * 100}%`);
      }
    });
    return player;
  }

  document.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-preview]");
    if (!btn) return;
    event.preventDefault();
    if (btn === activeButton) {                          // same button: toggle pause / resume
      if (player.paused) { player.play(); } else { player.pause(); setButton(btn, "idle"); }
      return;
    }
    stopPreview();
    const audio = getPlayer();
    activeButton = btn;
    setButton(btn, "loading");
    audio.src = btn.dataset.preview;
    audio.play().catch(() => {});
  });

  // ---------------------------------------------------------------- images

  document.addEventListener("error", (event) => {
    const img = event.target;
    if (img.tagName === "IMG" && !img.dataset.fallback) {
      img.dataset.fallback = "1";
      img.src = img.dataset.placeholder || PLACEHOLDER;
    }
  }, true);

  window.SSPIDERR = { fetch: ssFetch, toast, openPlaylistPicker: openModal, closePlaylistPicker: closeModal };
})();
