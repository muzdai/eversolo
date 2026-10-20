/* Eversolo player card for Home Assistant
 * - landscape / portrait layout picked from the card's own shape
 * - background colours sampled from the album cover (ambient style)
 * - inputs, outputs, music service, meter view, front display, loop mode
 * Version 1.0.0 — https://github.com/muzdai/eversolo
 */
const EVERSOLO_CARD_VERSION = "1.0.2";

const ICONS = {
  play: "M8 5v14l11-7z",
  pause: "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
  next: "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
  prev: "M6 6h2v12H6zm3.5 6l8.5 6V6z",
  volume: "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z",
  mute: "M16.5 12A4.5 4.5 0 0 0 14 8v2.18l2.45 2.45c.03-.2.05-.41.05-.63zM19 12c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.8 8.8 0 0 0 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a8.99 8.99 0 0 0 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z",
  repeat: "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z",
  shuffle: "M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z",
  display: "M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h7v2H8v2h8v-2h-2v-2h7c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z",
  music: "M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z",
};

const svg = (path, cls = "") =>
  `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const fmtTime = (sec) => {
  if (sec == null || isNaN(sec)) return "--:--";
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const mm = String(m).padStart(2, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};

/* Dominant colours from an image, sampled on a tiny canvas (same-origin only). */
function sampleColors(img) {
  try {
    const c = document.createElement("canvas");
    c.width = c.height = 24;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0, 24, 24);
    const data = ctx.getImageData(0, 0, 24, 24).data;
    let best = null, bestScore = -1, r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < data.length; i += 4) {
      const pr = data[i], pg = data[i + 1], pb = data[i + 2];
      r += pr; g += pg; b += pb; n++;
      const max = Math.max(pr, pg, pb), min = Math.min(pr, pg, pb);
      const sat = max === 0 ? 0 : (max - min) / max;
      const score = sat * (max / 255) + 0.01;
      if (score > bestScore) { bestScore = score; best = [pr, pg, pb]; }
    }
    const avg = [r / n, g / n, b / n];
    return { primary: best || avg, secondary: avg };
  } catch (e) {
    return null; // tainted canvas: keep the default background
  }
}

class EversoloPlayerCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity || !config.entity.startsWith("media_player.")) {
      throw new Error("eversolo-player-card: set `entity` to a media_player.* entity");
    }
    this._config = { show_background: true, show_chips: true, ...config };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this._build();
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._landscape ? 5 : 9;
  }

  static getStubConfig(hass) {
    const e = Object.keys(hass.states).find((s) => s.startsWith("media_player.") && s.includes("eversolo"));
    return { entity: e || "media_player.eversolo" };
  }

  connectedCallback() {
    this._ro = new ResizeObserver(() => this._applyLayout());
    this._ro.observe(this);
    this._tick = setInterval(() => this._updateProgress(), 500);
    this._applyLayout();
  }

  disconnectedCallback() {
    if (this._ro) this._ro.disconnect();
    clearInterval(this._tick);
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; position:relative; border-radius:20px; overflow:hidden;
                --c1:#2a2a2e; --c2:#131316; color:#f2f2f2; font-family:var(--paper-font-body1_-_font-family, system-ui, sans-serif); }
        .bg { position:absolute; inset:-30%; background:
                radial-gradient(45% 55% at 20% 25%, var(--c1), transparent 70%),
                radial-gradient(50% 60% at 85% 85%, var(--c2), transparent 75%),
                #0b0b0d;
              filter: blur(38px) saturate(1.25); transition: background 0.8s ease; }
        .bg.off { background:#0b0b0d; }
        .shade { position:absolute; inset:0; background:linear-gradient(180deg, rgba(0,0,0,.15), rgba(0,0,0,.55)); }
        .wrap { position:relative; padding:18px; display:grid; gap:16px; }
        :host(.portrait) .wrap { grid-template-columns: 1fr; justify-items:center; text-align:center; }
        :host(.landscape) .wrap { grid-template-columns: minmax(160px, 42%) 1fr; align-items:center; }
        .cover { position:relative; width:100%; aspect-ratio:1/1; border-radius:14px; overflow:hidden;
                 background:rgba(255,255,255,.06); box-shadow:0 18px 40px rgba(0,0,0,.45); }
        :host(.portrait) .cover { width:min(78%, 300px); }
        .cover img { width:100%; height:100%; object-fit:cover; display:block; }
        .cover .ph { position:absolute; inset:0; display:grid; place-items:center; }
        .cover .ph svg { width:40%; opacity:.35; fill:#fff; }
        .info { min-width:0; display:grid; gap:6px; width:100%; }
        .source { font-size:12px; letter-spacing:.08em; text-transform:uppercase; opacity:.65; }
        .title { font-size:22px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .artist { font-size:15px; opacity:.8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .fmt { font-size:12px; opacity:.55; }
        .seek { display:grid; grid-template-columns:auto 1fr auto; gap:10px; align-items:center; font-size:12px; margin-top:8px; font-variant-numeric:tabular-nums; }
        .bar { position:relative; height:6px; border-radius:3px; background:rgba(255,255,255,.22); cursor:pointer; touch-action:none; }
        .bar .fill { position:absolute; left:0; top:0; bottom:0; border-radius:3px; background:#fff; width:0%; }
        .transport { display:flex; align-items:center; justify-content:center; gap:18px; margin-top:6px; }
        button { all:unset; cursor:pointer; display:grid; place-items:center; width:44px; height:44px; border-radius:50%; position:relative; }
        button:active { transform:scale(.95); }
        button svg { width:26px; height:26px; fill:#fff; }
        button.big { width:66px; height:66px; background:#fff; }
        button.big svg { width:34px; height:34px; fill:#111; }
        button.on svg { fill: var(--accent, #ffd58a); }
        button .badge { position:absolute; right:6px; bottom:4px; font-size:9px; font-weight:700; }
        .vol { display:grid; grid-template-columns:auto 1fr; gap:10px; align-items:center; margin-top:6px; }
        .vol svg { width:22px; height:22px; fill:#fff; opacity:.85; }
        input[type=range] { width:100%; accent-color:#fff; }
        .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
        :host(.portrait) .chips { justify-content:center; }
        .chip { all:unset; cursor:pointer; padding:7px 12px; border-radius:999px; background:rgba(255,255,255,.14);
                font-size:12px; white-space:nowrap; max-width:100%; overflow:hidden; text-overflow:ellipsis; }
        .chip b { font-weight:600; opacity:.7; margin-right:4px; }
        .menu { position:absolute; z-index:5; right:12px; bottom:12px; min-width:220px; max-height:60%; overflow:auto;
                background:rgba(20,20,24,.96); border-radius:14px; padding:6px; box-shadow:0 12px 30px rgba(0,0,0,.5); }
        .menu[hidden] { display:none; }
        .menu button { display:block; width:100%; height:auto; border-radius:10px; text-align:left; padding:10px 12px; font-size:14px; box-sizing:border-box; }
        .menu button.sel { background:rgba(255,255,255,.14); }
        .menu button:hover { background:rgba(255,255,255,.08); }
        .unavail { padding:24px; text-align:center; opacity:.7; }
      </style>
      <div class="bg" id="bg"></div><div class="shade"></div>
      <div class="wrap" id="wrap"></div>
      <div class="menu" id="menu" hidden></div>`;
    this._root = this.shadowRoot;
    this._root.addEventListener("click", (ev) => this._onClick(ev));
    this._root.addEventListener("input", (ev) => this._onInput(ev));
    this._root.addEventListener("pointerdown", (ev) => this._onSeekDown(ev));
  }

  _applyLayout() {
    const w = this.clientWidth || 1, h = this.clientHeight || 1;
    const landscape = w >= h * 1.05;
    this._landscape = landscape;
    this.classList.toggle("landscape", landscape);
    this.classList.toggle("portrait", !landscape);
    this._render(true);
  }

  _state() {
    const s = this._hass && this._config && this._hass.states[this._config.entity];
    return s || null;
  }

  _render(layoutOnly = false) {
    if (!this._root || !this._hass) return;
    const st = this._state();
    const wrap = this._root.getElementById("wrap");
    if (!st) {
      wrap.innerHTML = `<div class="unavail">Entity ${esc(this._config.entity)} not found</div>`;
      return;
    }
    if (!this._rendered || layoutOnly) {
      wrap.innerHTML = `
        <div class="cover"><div class="ph">${svg(ICONS.music)}</div><img id="cover" alt="" hidden></div>
        <div class="info">
          <div class="source" id="source"></div>
          <div class="title" id="title"></div>
          <div class="artist" id="artist"></div>
          <div class="fmt" id="fmt"></div>
          <div class="seek">
            <span id="pos">--:--</span>
            <div class="bar" id="bar"><div class="fill" id="fill"></div></div>
            <span id="dur">--:--</span>
          </div>
          <div class="transport">
            <button data-act="loop" id="loop" title="Loop">${svg(ICONS.repeat)}</button>
            <button data-act="prev" title="Previous">${svg(ICONS.prev)}</button>
            <button data-act="play" class="big" id="play" title="Play / pause">${svg(ICONS.play)}</button>
            <button data-act="next" title="Next">${svg(ICONS.next)}</button>
            <button data-act="mute" id="mute" title="Mute">${svg(ICONS.volume)}</button>
          </div>
          <div class="vol">${svg(ICONS.volume)}<input type="range" id="vol" min="0" max="100" step="1"></div>
          <div class="chips" id="chips"></div>
        </div>`;
      this._rendered = true;
    }
    const a = st.attributes;
    const set = (id, text) => { const el = this._root.getElementById(id); if (el) el.textContent = text; };
    set("source", a.source || "Eversolo");
    set("title", st.attributes.media_title || (st.state === "idle" ? "Nothing playing" : "—"));
    set("artist", [a.media_artist, a.media_album_name].filter(Boolean).join(" · "));
    const fmtParts = [a.codec, a.bits ? `${a.bits}bit` : null, a.sample_rate ? `${a.sample_rate} Hz` : null].filter(Boolean);
    set("fmt", fmtParts.join(" · "));
    const playing = st.state === "playing";
    this._root.getElementById("play").innerHTML = svg(playing ? ICONS.pause : ICONS.play);
    const loop = a.loop_mode || "list";
    const loopBtn = this._root.getElementById("loop");
    loopBtn.innerHTML = svg(loop === "shuffle" ? ICONS.shuffle : ICONS.repeat) + (loop === "single" ? '<span class="badge">1</span>' : "");
    loopBtn.classList.toggle("on", loop !== "list");
    const muteBtn = this._root.getElementById("mute");
    muteBtn.innerHTML = svg(a.is_volume_muted ? ICONS.mute : ICONS.volume);
    muteBtn.classList.toggle("on", !!a.is_volume_muted);
    const vol = this._root.getElementById("vol");
    if (vol && document.activeElement !== vol && a.volume_level != null) vol.value = Math.round(a.volume_level * 100);
    this._updateProgress();
    this._renderChips(a);
    this._updateCover(a.entity_picture_local || a.entity_picture);
    this._updateBackground(!!this._config.show_background);
  }

  _renderChips(a) {
    const chips = this._root.getElementById("chips");
    if (!chips || this._config.show_chips === false) return;
    const list = [
      ["input", "Input", a.input],
      ["output", "Out", a.output],
      ["service", "Service", a.service],
      ["vu", "Meter", a.vu_mode === "spectrum" ? "Spectrum" : a.vu_mode === "vu" ? "VU" : "—"],
      ["display", "Display", a.display_on == null ? "?" : a.display_on ? "On" : "Off"],
    ];
    chips.innerHTML = list
      .filter(([k]) => !(k === "service" && !(a.service_list || []).length))
      .map(([k, label, val]) => `<button class="chip" data-chip="${k}"><b>${esc(label)}</b>${esc(val ?? "—")}</button>`)
      .join("");
  }

  _updateProgress() {
    if (!this._root || !this._hass) return;
    const st = this._state();
    if (!st) return;
    const a = st.attributes;
    const dur = Number(a.media_duration) || 0;
    let pos = Number(a.media_position) || 0;
    if (st.state === "playing" && a.media_position_updated_at) {
      pos += (Date.now() - Date.parse(a.media_position_updated_at)) / 1000;
    }
    if (dur) pos = Math.min(pos, dur);
    const ratio = dur ? pos / dur : 0;
    const fill = this._root.getElementById("fill");
    if (fill) fill.style.width = `${(ratio * 100).toFixed(2)}%`;
    const p = this._root.getElementById("pos"), d = this._root.getElementById("dur");
    if (p) p.textContent = fmtTime(pos);
    if (d) d.textContent = fmtTime(dur);
  }

  _updateCover(url) {
    const img = this._root.getElementById("cover");
    if (!img) return;
    if (!url) { img.hidden = true; this._setColors(null); return; }
    if (img.dataset.src === url) return;
    img.dataset.src = url;
    img.crossOrigin = "anonymous";
    img.hidden = false;
    img.onload = () => this._setColors(sampleColors(img));
    img.onerror = () => { img.hidden = true; this._setColors(null); };
    img.src = url;
  }

  _setColors(colors) {
    const bg = this._root.getElementById("bg");
    if (!bg) return;
    if (!colors) { bg.classList.add("off"); return; }
    bg.classList.remove("off");
    const rgb = (c, a = 1) => `rgba(${c.map((v) => Math.round(v)).join(",")},${a})`;
    this._root.host.style.setProperty("--c1", rgb(colors.primary, 0.9));
    this._root.host.style.setProperty("--c2", rgb(colors.secondary, 0.85));
    this._root.host.style.setProperty("--accent", rgb(colors.primary.map((v) => Math.min(255, v + 90))));
  }

  _updateBackground(enabled) {
    const bg = this._root.getElementById("bg");
    if (bg) bg.style.display = enabled ? "" : "none";
  }

  /* ---- interaction ------------------------------------------------- */
  _call(domain, service, data) {
    return this._hass.callService(domain, service, data);
  }

  _onClick(ev) {
    const menu = this._root.getElementById("menu");
    const path = ev.composedPath();
    const btn = path.find((el) => el && el.dataset && (el.dataset.act || el.dataset.chip || el.dataset.opt));
    if (!btn) { if (!menu.hidden && !path.includes(menu)) menu.hidden = true; return; }
    const entity = this._config.entity;
    if (btn.dataset.opt) {
      const [kind, value] = btn.dataset.opt.split("|");
      menu.hidden = true;
      const map = { input: "set_input", output: "set_output", service: "set_service" };
      if (map[kind]) return this._call("eversolo", map[kind], { entity_id: entity, name: value });
      if (kind === "vu") return this._call("eversolo", "set_vu_mode", { entity_id: entity, mode: value });
      if (kind === "loop") return this._call("eversolo", "set_loop_mode", { entity_id: entity, mode: value });
      return;
    }
    if (btn.dataset.chip) return this._openChip(btn.dataset.chip, btn);
    switch (btn.dataset.act) {
      case "play": return this._call("media_player", "media_play_pause", { entity_id: entity });
      case "prev": return this._call("media_player", "media_previous_track", { entity_id: entity });
      case "next": return this._call("media_player", "media_next_track", { entity_id: entity });
      case "mute": {
        const muted = !!this._state().attributes.is_volume_muted;
        return this._call("media_player", "volume_mute", { entity_id: entity, is_volume_muted: !muted });
      }
      case "loop": return this._openLoop(btn);
    }
  }

  _openLoop(anchor) {
    const cur = this._state().attributes.loop_mode || "list";
    this._showMenu(anchor, "Loop mode", [
      ["list", "List (in order)", cur === "list"],
      ["single", "Repeat one", cur === "single"],
      ["shuffle", "Shuffle", cur === "shuffle"],
    ], "loop");
  }

  _openChip(kind, anchor) {
    const a = this._state().attributes;
    if (kind === "display") {
      return this._call("eversolo", "set_display", { entity_id: this._config.entity, on: !a.display_on });
    }
    const lists = {
      input: [a.input_list || [], a.input],
      output: [a.output_list || [], a.output],
      service: [a.service_list || [], a.service],
      vu: [["vu", "spectrum"], a.vu_mode],
    };
    const [items, current] = lists[kind] || [[], null];
    const labels = kind === "vu" ? { vu: "VU meter (needles)", spectrum: "Spectrum" } : {};
    this._showMenu(anchor, { input: "Input", output: "Output", service: "Music service", vu: "Meter display" }[kind],
      items.map((i) => [i, labels[i] || i, i === current]), kind);
  }

  _showMenu(anchor, title, items, kind) {
    const menu = this._root.getElementById("menu");
    menu.innerHTML = `<div class="fmt" style="padding:6px 12px">${esc(title)}</div>` +
      (items.length ? items.map(([val, label, sel]) =>
        `<button data-opt="${esc(kind)}|${esc(val)}" class="${sel ? "sel" : ""}">${esc(label)}</button>`).join("")
        : `<div class="fmt" style="padding:8px 12px">Nothing available on this device</div>`);
    menu.hidden = false;
  }

  _onInput(ev) {
    if (ev.target && ev.target.id === "vol") {
      clearTimeout(this._volTimer);
      const level = Number(ev.target.value) / 100;
      this._volTimer = setTimeout(() => {
        this._call("media_player", "volume_set", { entity_id: this._config.entity, volume_level: level });
      }, 250);
    }
  }

  _onSeekDown(ev) {
    const bar = ev.composedPath().find((el) => el && el.id === "bar");
    if (!bar) return;
    const seek = (e) => {
      const st = this._state();
      const dur = Number(st && st.attributes.media_duration) || 0;
      if (!dur) return;
      const rect = bar.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      bar.querySelector(".fill").style.width = `${ratio * 100}%`;
      return ratio * dur;
    };
    const move = (e) => seek(e);
    const up = (e) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const target = seek(e);
      if (target != null) this._call("media_player", "media_seek", { entity_id: this._config.entity, seek_position: target });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }
}

if (!customElements.get("eversolo-player-card")) {
  customElements.define("eversolo-player-card", EversoloPlayerCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "eversolo-player-card")) {
  window.customCards.push({
    type: "eversolo-player-card",
    name: "Eversolo Player",
    description: "Eversolo DMP/DAC player with ambient cover background",
    preview: false,
  });
}
console.info(`%c EVERSOLO-PLAYER-CARD %c ${EVERSOLO_CARD_VERSION} `, "color:#fff;background:#c68a3c;font-weight:700", "color:#c68a3c;background:#222");
