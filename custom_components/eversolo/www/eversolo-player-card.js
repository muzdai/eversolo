/* Eversolo player card for Home Assistant — https://github.com/muzdai/eversolo
 * - landscape / portrait layout from the screen orientation (landscape when unknown)
 * - background colours sampled from the album cover (ambient style)
 * - inputs, outputs, VU / spectrum, streaming apps, power menu, loop mode
 */
const EVERSOLO_CARD_VERSION = "2.1.0";

const ICONS = {
  play: "M8 5v14l11-7z",
  pause: "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
  next: "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
  prev: "M6 6h2v12H6zm3.5 6l8.5 6V6z",
  volume: "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z",
  mute: "M16.5 12A4.5 4.5 0 0 0 14 8v2.18l2.45 2.45c.03-.2.05-.41.05-.63zM19 12c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.8 8.8 0 0 0 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a8.99 8.99 0 0 0 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z",
  repeat: "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z",
  shuffle: "M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z",
  once: "M4 10h12v2H4zm0-4h12v2H4zm0 8h8v2H4zm10 0v6l5-3z",
  music: "M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z",
};

// MediaPlayerEntityFeature bits used to disable controls the source cannot handle.
const F = { PAUSE: 1, SEEK: 2, VOLUME_SET: 4, VOLUME_MUTE: 8, PREV: 16, NEXT: 32, PLAY: 16384, REPEAT: 262144 };

const STRINGS = {
  en: {
    nothing: "Nothing playing", notFound: "Entity {e} not found", unavailable: "Player is unavailable",
    input: "Input", output: "Out", vu: "VU", spectrum: "Spectrum", app: "Apps", power: "Power",
    inputTitle: "Input", outputTitle: "Output", appTitle: "Open app", powerTitle: "Power", loopTitle: "Loop mode",
    empty: "Nothing available on this device",
    repeat_all: "Repeat list", repeat_one: "Repeat track", shuffle: "Shuffle", play_once: "Play list once",
  },
  ru: {
    nothing: "Ничего не играет", notFound: "Сущность {e} не найдена", unavailable: "Плеер недоступен",
    input: "Вход", output: "Выход", vu: "VU", spectrum: "Спектр", app: "Приложения", power: "Питание",
    inputTitle: "Вход", outputTitle: "Выход", appTitle: "Открыть приложение", powerTitle: "Питание", loopTitle: "Режим повтора",
    empty: "На устройстве ничего нет",
    repeat_all: "Повтор списка", repeat_one: "Повтор трека", shuffle: "Случайный порядок", play_once: "Список один раз",
  },
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
    if (config.layout && !["auto", "landscape", "portrait"].includes(config.layout)) {
      throw new Error("eversolo-player-card: layout must be auto, landscape or portrait");
    }
    this._config = { show_background: true, show_chips: true, layout: "auto", ...config };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this._build();
    }
    this._layout = null;
    this._applyLayout();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._layout === "portrait" ? 9 : 5;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  static getStubConfig(hass) {
    const e = Object.keys(hass.states).find(
      (s) => s.startsWith("media_player.") && hass.states[s].attributes && "vu_mode" in hass.states[s].attributes,
    );
    return { entity: e || "media_player.eversolo" };
  }

  connectedCallback() {
    this._ro = new ResizeObserver(() => this._applyLayout());
    this._ro.observe(this);
    this._mq = window.matchMedia("(orientation: portrait)");
    this._mqListener = () => this._applyLayout();
    this._mq.addEventListener("change", this._mqListener);
    this._tick = setInterval(() => this._updateProgress(), 500);
    this._applyLayout();
  }

  disconnectedCallback() {
    if (this._ro) this._ro.disconnect();
    if (this._mq) this._mq.removeEventListener("change", this._mqListener);
    clearInterval(this._tick);
  }

  _t(key) {
    const lang = (this._hass && (this._hass.locale?.language || this._hass.language)) || "en";
    const table = STRINGS[lang.split("-")[0]] || STRINGS.en;
    return table[key] ?? STRINGS.en[key] ?? key;
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; position:relative; border-radius:var(--ha-card-border-radius, 20px); overflow:hidden;
                --c1:#2a2a2e; --c2:#131316; color:#f2f2f2; font-family:var(--ha-font-family-body, system-ui, sans-serif); }
        .bg { position:absolute; inset:-30%; background:
                radial-gradient(45% 55% at 20% 25%, var(--c1), transparent 70%),
                radial-gradient(50% 60% at 85% 85%, var(--c2), transparent 75%),
                #0b0b0d;
              filter: blur(38px) saturate(1.25); transition: background 0.8s ease; }
        .bg.off { background:#0b0b0d; }
        .shade { position:absolute; inset:0; background:linear-gradient(180deg, rgba(0,0,0,.15), rgba(0,0,0,.55)); }
        .wrap { position:relative; padding:18px; display:grid; gap:16px; }
        :host(.portrait) .wrap { grid-template-columns: 1fr; justify-items:center; text-align:center; }
        :host(.landscape) .wrap { grid-template-columns: minmax(150px, 40%) 1fr; align-items:center; }
        .cover { position:relative; width:100%; aspect-ratio:1/1; border-radius:14px; overflow:hidden;
                 background:rgba(255,255,255,.06); box-shadow:0 18px 40px rgba(0,0,0,.45); }
        :host(.portrait) .cover { width:min(78%, 320px); }
        .cover img { position:absolute; inset:0; z-index:1; width:100%; height:100%; object-fit:cover; display:block; }
        .cover img[hidden] { display:none; }
        .cover .ph { position:absolute; inset:0; display:grid; place-items:center; }
        .cover .ph svg { width:40%; opacity:.35; fill:#fff; }
        .info { min-width:0; display:grid; gap:6px; width:100%; }
        .source { font-size:12px; letter-spacing:.08em; text-transform:uppercase; opacity:.65; }
        .title { font-size:22px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .artist { font-size:15px; opacity:.8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .fmt { font-size:12px; opacity:.55; min-height:1em; }
        .seek { display:grid; grid-template-columns:auto 1fr auto; gap:10px; align-items:center; font-size:12px; margin-top:8px; font-variant-numeric:tabular-nums; }
        .seek.hide { visibility:hidden; }
        .bar { position:relative; height:6px; border-radius:3px; background:rgba(255,255,255,.22); cursor:pointer; touch-action:none; }
        .bar .fill { position:absolute; left:0; top:0; bottom:0; border-radius:3px; background:#fff; width:0%; }
        .transport { display:flex; align-items:center; justify-content:center; gap:18px; margin-top:6px; }
        button { all:unset; cursor:pointer; display:grid; place-items:center; width:44px; height:44px; border-radius:50%; position:relative; }
        button:active { transform:scale(.95); }
        button[disabled] { opacity:.3; pointer-events:none; }
        button svg { width:26px; height:26px; fill:#fff; }
        button.big { width:66px; height:66px; background:#fff; }
        button.big svg { width:34px; height:34px; fill:#111; }
        button.on svg { fill: var(--accent, #ffd58a); }
        button .badge { position:absolute; right:6px; bottom:4px; font-size:9px; font-weight:700; }
        .vol { display:grid; grid-template-columns:auto 1fr auto; gap:10px; align-items:center; margin-top:6px; }
        .vol.hide { display:none; }
        .vol svg { width:22px; height:22px; fill:#fff; opacity:.85; }
        .vol .lvl { font-size:12px; opacity:.7; min-width:3ch; text-align:right; font-variant-numeric:tabular-nums; }
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

  /* Portrait when the screen is held upright or the card is too narrow for two columns. */
  _pickLayout() {
    const forced = this._config && this._config.layout;
    if (forced === "landscape" || forced === "portrait") return forced;
    const width = this.clientWidth;
    if (width && width < 420) return "portrait";
    const mq = this._mq || (window.matchMedia && window.matchMedia("(orientation: portrait)"));
    return mq && mq.matches ? "portrait" : "landscape";
  }

  _applyLayout() {
    if (!this._root) return;
    const layout = this._pickLayout();
    if (layout === this._layout) return;
    this._layout = layout;
    this.classList.toggle("landscape", layout === "landscape");
    this.classList.toggle("portrait", layout === "portrait");
    this._rendered = false;
    this._render();
  }

  _state() {
    return (this._hass && this._config && this._hass.states[this._config.entity]) || null;
  }

  _render() {
    if (!this._root || !this._hass || !this._config) return;
    const st = this._state();
    const wrap = this._root.getElementById("wrap");
    if (!st || st.state === "unavailable") {
      const msg = st ? this._t("unavailable") : this._t("notFound").replace("{e}", this._config.entity);
      wrap.innerHTML = `<div class="unavail">${esc(msg)}</div>`;
      this._rendered = false;
      this._setColors(null);
      return;
    }
    if (!this._rendered) {
      wrap.innerHTML = `
        <div class="cover"><div class="ph">${svg(ICONS.music)}</div><img id="cover" alt="" hidden></div>
        <div class="info">
          <div class="source" id="source"></div>
          <div class="title" id="title"></div>
          <div class="artist" id="artist"></div>
          <div class="fmt" id="fmt"></div>
          <div class="seek" id="seek">
            <span id="pos">--:--</span>
            <div class="bar" id="bar"><div class="fill" id="fill"></div></div>
            <span id="dur">--:--</span>
          </div>
          <div class="transport">
            <button data-act="loop" id="loop">${svg(ICONS.repeat)}</button>
            <button data-act="prev" id="prev">${svg(ICONS.prev)}</button>
            <button data-act="play" class="big" id="play">${svg(ICONS.play)}</button>
            <button data-act="next" id="next">${svg(ICONS.next)}</button>
            <button data-act="mute" id="mute">${svg(ICONS.volume)}</button>
          </div>
          <div class="vol" id="volrow">${svg(ICONS.volume)}<input type="range" id="vol" min="0" max="100" step="1"><span class="lvl" id="lvl"></span></div>
          <div class="chips" id="chips"></div>
        </div>`;
      this._rendered = true;
      this._coverSrc = null;
    }
    const a = st.attributes;
    const feat = Number(a.supported_features) || 0;
    const has = (bit) => (feat & bit) === bit;
    const byId = (id) => this._root.getElementById(id);
    const set = (id, text) => { const el = byId(id); if (el) el.textContent = text; };

    set("source", a.source || a.input || "Eversolo");
    set("title", a.media_title || (st.state === "idle" ? this._t("nothing") : "—"));
    set("artist", [a.media_artist, a.media_album_name].filter(Boolean).join(" · "));
    const fmtParts = [a.codec, a.bits ? `${a.bits}bit` : null, a.sample_rate || null].filter(Boolean);
    set("fmt", [fmtParts.join(" · "), a.output_format ? `→ ${a.output_format}` : null].filter(Boolean).join("  "));

    const playing = st.state === "playing";
    byId("play").innerHTML = svg(playing ? ICONS.pause : ICONS.play);
    byId("play").toggleAttribute("disabled", !(has(F.PLAY) || has(F.PAUSE)));
    byId("prev").toggleAttribute("disabled", !has(F.PREV));
    byId("next").toggleAttribute("disabled", !has(F.NEXT));
    byId("seek").classList.toggle("hide", !has(F.SEEK) && !a.media_duration);

    const loop = a.loop_mode || "repeat_all";
    const loopBtn = byId("loop");
    const loopIcon = { shuffle: ICONS.shuffle, play_once: ICONS.once }[loop] || ICONS.repeat;
    loopBtn.innerHTML = svg(loopIcon) + (loop === "repeat_one" ? '<span class="badge">1</span>' : "");
    loopBtn.classList.toggle("on", loop !== "play_once");
    loopBtn.title = this._t(loop);
    loopBtn.toggleAttribute("disabled", !has(F.REPEAT));

    const muteBtn = byId("mute");
    muteBtn.innerHTML = svg(a.is_volume_muted ? ICONS.mute : ICONS.volume);
    muteBtn.classList.toggle("on", !!a.is_volume_muted);
    muteBtn.toggleAttribute("disabled", !has(F.VOLUME_MUTE));
    byId("volrow").classList.toggle("hide", !has(F.VOLUME_SET));
    const vol = byId("vol");
    if (vol && this._root.activeElement !== vol && a.volume_level != null) vol.value = Math.round(a.volume_level * 100);
    set("lvl", a.volume_display ?? (a.volume_level != null ? Math.round(a.volume_level * 100) : ""));

    this._updateProgress();
    this._renderChips(a);
    this._updateCover(a.entity_picture_local || a.entity_picture);
    this._updateBackground(!!this._config.show_background);
  }

  _renderChips(a) {
    const chips = this._root.getElementById("chips");
    if (!chips) return;
    if (this._config.show_chips === false) { chips.innerHTML = ""; return; }
    const list = [];
    if ((a.input_list || []).length) list.push(["input", this._t("input"), a.input]);
    if ((a.output_list || []).length) list.push(["output", this._t("output"), a.output]);
    // The app shows its VU button for vuDisplayMode >= -1 and its spectrum button for spDisplayMode >= 0.
    if (a.vu_mode != null && a.vu_mode >= -1) list.push(["vu", this._t("vu"), "↻"]);
    if (a.spectrum_mode != null && a.spectrum_mode >= 0) list.push(["spectrum", this._t("spectrum"), "↻"]);
    if ((a.app_list || []).length) list.push(["app", this._t("app"), a.app]);
    if ((a.power_list || []).length) list.push(["power", this._t("power"), "⏻"]);
    const html = list
      .map(([k, label, val]) => `<button class="chip" data-chip="${k}">${val == null || val === ""
        ? esc(label) : `<b>${esc(label)}</b>${esc(val)}`}</button>`)
      .join("");
    if (chips.innerHTML !== html) chips.innerHTML = html;
  }

  _updateProgress() {
    if (!this._root || !this._hass) return;
    const st = this._state();
    if (!st || !this._rendered) return;
    const a = st.attributes;
    const dur = Number(a.media_duration) || 0;
    let pos = Number(a.media_position) || 0;
    if (st.state === "playing" && a.media_position_updated_at) {
      pos += (Date.now() - Date.parse(a.media_position_updated_at)) / 1000;
    }
    if (dur) pos = Math.min(pos, dur);
    const ratio = dur ? pos / dur : 0;
    const fill = this._root.getElementById("fill");
    if (fill && !this._seeking) fill.style.width = `${(ratio * 100).toFixed(2)}%`;
    const p = this._root.getElementById("pos"), d = this._root.getElementById("dur");
    if (p) p.textContent = fmtTime(pos);
    if (d) d.textContent = dur ? fmtTime(dur) : "--:--";
  }

  _updateCover(url) {
    const img = this._root.getElementById("cover");
    if (!img) return;
    if (!url) { img.hidden = true; this._coverSrc = null; this._setColors(null); return; }
    if (this._coverSrc === url) return;
    this._coverSrc = url;
    img.crossOrigin = "anonymous";
    img.onload = () => { img.hidden = false; this._setColors(sampleColors(img)); };
    img.onerror = () => { img.hidden = true; this._setColors(null); };
    img.src = url;
  }

  _setColors(colors) {
    const bg = this._root.getElementById("bg");
    if (!bg) return;
    if (!colors) { bg.classList.add("off"); return; }
    bg.classList.remove("off");
    const rgb = (c, a = 1) => `rgba(${c.map((v) => Math.round(v)).join(",")},${a})`;
    this.style.setProperty("--c1", rgb(colors.primary, 0.9));
    this.style.setProperty("--c2", rgb(colors.secondary, 0.85));
    this.style.setProperty("--accent", rgb(colors.primary.map((v) => Math.min(255, v + 90))));
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
      const sep = btn.dataset.opt.indexOf("|");
      const kind = btn.dataset.opt.slice(0, sep), value = btn.dataset.opt.slice(sep + 1);
      menu.hidden = true;
      const byName = { input: "set_input", output: "set_output", app: "open_app", power: "power" };
      if (byName[kind]) return this._call("eversolo", byName[kind], { entity_id: entity, name: value });
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
      case "loop": return this._openLoop();
    }
  }

  _openLoop() {
    const cur = this._state().attributes.loop_mode || "repeat_all";
    this._showMenu(this._t("loopTitle"),
      ["repeat_all", "repeat_one", "shuffle", "play_once"].map((m) => [m, this._t(m), m === cur]), "loop");
  }

  _openChip(kind) {
    const a = this._state().attributes;
    const entity = this._config.entity;
    if (kind === "vu") return this._call("eversolo", "vu_next", { entity_id: entity });
    if (kind === "spectrum") return this._call("eversolo", "spectrum_next", { entity_id: entity });
    const lists = {
      input: [a.input_list || [], a.input, "inputTitle"],
      output: [a.output_list || [], a.output, "outputTitle"],
      app: [a.app_list || [], a.app, "appTitle"],
      power: [a.power_list || [], null, "powerTitle"],
    };
    const [items, current, title] = lists[kind] || [[], null, kind];
    this._showMenu(this._t(title), items.map((i) => [i, i, i === current]), kind);
  }

  _showMenu(title, items, kind) {
    const menu = this._root.getElementById("menu");
    menu.innerHTML = `<div class="fmt" style="padding:6px 12px">${esc(title)}</div>` +
      (items.length ? items.map(([val, label, sel]) =>
        `<button data-opt="${esc(kind)}|${esc(val)}" class="${sel ? "sel" : ""}">${esc(label)}</button>`).join("")
        : `<div class="fmt" style="padding:8px 12px">${esc(this._t("empty"))}</div>`);
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
    const st = this._state();
    if (!st || !((Number(st.attributes.supported_features) || 0) & F.SEEK)) return;
    this._seeking = true;
    const seek = (e) => {
      const dur = Number(this._state()?.attributes.media_duration) || 0;
      if (!dur) return null;
      const rect = bar.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      bar.querySelector(".fill").style.width = `${ratio * 100}%`;
      return ratio * dur;
    };
    const move = (e) => seek(e);
    const up = (e) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      this._seeking = false;
      const target = seek(e);
      if (target != null) this._call("media_player", "media_seek", { entity_id: this._config.entity, seek_position: target });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    seek(ev);
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
