/* Eversolo player card for Home Assistant — https://github.com/muzdai/eversolo
 * Styled after the Eversolo Control app's now-playing screen:
 * - landscape / portrait layout from the screen orientation (landscape when unknown)
 * - background colours sampled from the album cover (ambient style)
 * - DSP / EQ / sub status, spectrum and VU buttons, menu with inputs, outputs, apps, power
 * Icons come from the eversolo:* icon set (eversolo-icons.js) when it is loaded.
 */
const EVERSOLO_CARD_VERSION = "2.2.0";

const BASE_ICONS = {
  play: "M8 5v14l11-7z",
  pause: "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
  next: "M5 18.5V5.5L14 12zM16 5.5h3v13h-3z",
  prev: "M19 5.5v13L10 12zM5 5.5h3v13H5z",
  volume: "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z",
  mute: "M16.5 12A4.5 4.5 0 0 0 14 8v2.18l2.45 2.45c.03-.2.05-.41.05-.63zM19 12c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.8 8.8 0 0 0 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a8.99 8.99 0 0 0 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z",
  repeat: "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z",
  more: "M6 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  back: "M15.4 7.4L14 6l-6 6 6 6 1.4-1.4L10.8 12z",
  pulse: "M3 13h2.8l4.3-8.2 1.2 9 3.2-4.1 3.3 3.3H21v2h-4l-2.3-2.3-4.8 6.1-1-7.4L7 15H3z",
  music: "M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z",
};

// MediaPlayerEntityFeature bits used to disable controls the source cannot handle.
const F = { PAUSE: 1, SEEK: 2, VOLUME_SET: 4, VOLUME_MUTE: 8, PREV: 16, NEXT: 32, PLAY: 16384, REPEAT: 262144 };

const STRINGS = {
  en: {
    nothing: "Nothing playing", notFound: "Entity {e} not found", unavailable: "Player is unavailable",
    input: "Input", output: "Output", vu: "VU meter", spectrum: "Spectrum", app: "Apps", power: "Power", more: "More",
    dsp: "DSP", eq: "EQ", sub: "Subwoofer", on: "on", off: "off",
    loopTitle: "Loop mode", openApp: "Open app", empty: "Nothing available on this device",
    repeat_all: "Repeat list", repeat_one: "Repeat track", shuffle: "Shuffle", play_once: "Play list once",
  },
  ru: {
    nothing: "Ничего не играет", notFound: "Сущность {e} не найдена", unavailable: "Плеер недоступен",
    input: "Вход", output: "Выход", vu: "VU-индикатор", spectrum: "Спектр", app: "Приложения", power: "Питание", more: "Ещё",
    dsp: "DSP", eq: "EQ", sub: "Сабвуфер", on: "вкл", off: "выкл",
    loopTitle: "Режим повтора", openApp: "Открыть приложение", empty: "На устройстве ничего нет",
    repeat_all: "Повтор списка", repeat_one: "Повтор трека", shuffle: "Случайный порядок", play_once: "Список один раз",
  },
};

const LOOP_ICON = { repeat_all: "repeat", repeat_one: "repeat-one", shuffle: "shuffle", play_once: "play-once" };
// Icon per display mode, as the app picks them (DetailsFragment).
const VU_ICON = { "-1": "vu", 0: "vu", 1: "vu-big", 2: "vu-off" };
const SPECTRUM_ICON = { 0: "spectrum", 1: "spectrum-big", 2: "spectrum-off" };

/* eversolo:* icon if the icon set is loaded, else a built-in fallback path. */
const iconPath = (name, fallback) => (window.EversoloIcons && window.EversoloIcons[name]) || BASE_ICONS[fallback || name] || "";

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
    this._config = { show_background: true, show_volume: true, show_chips: false, layout: "auto", ...config };
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
    return this._layout === "portrait" ? 10 : 6;
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
    this._iconsListener = () => { this._rendered = false; this._render(); };
    window.addEventListener("eversolo-icons-loaded", this._iconsListener);
    this._tick = setInterval(() => this._updateProgress(), 500);
    this._applyLayout();
  }

  disconnectedCallback() {
    if (this._ro) this._ro.disconnect();
    if (this._mq) this._mq.removeEventListener("change", this._mqListener);
    window.removeEventListener("eversolo-icons-loaded", this._iconsListener);
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
                --c1:#3a2a22; --c2:#140f0d; --accent:#d9925a; color:#f4f1ee;
                font-family:var(--ha-font-family-body, system-ui, sans-serif); }
        .bg { position:absolute; inset:-30%; background:
                radial-gradient(50% 60% at 25% 30%, var(--c1), transparent 72%),
                radial-gradient(55% 65% at 85% 80%, var(--c2), transparent 75%),
                #0d0b0a;
              filter: blur(42px) saturate(1.15); transition: background 0.8s ease; }
        .bg.off { background:#0d0b0a; }
        .shade { position:absolute; inset:0; background:linear-gradient(180deg, rgba(0,0,0,.28), rgba(0,0,0,.6)); }
        .wrap { position:relative; padding:14px 20px 18px; container-type:inline-size; }

        .top { display:flex; align-items:center; gap:12px; min-height:40px; }
        .src { flex:1; min-width:0; font-size:clamp(15px, 2.6cqw, 26px); font-weight:500; letter-spacing:.01em;
               opacity:.85; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .tools { display:flex; align-items:center; gap:clamp(4px, 1.4cqw, 18px); }
        .tool { all:unset; display:grid; place-items:center; width:clamp(30px, 4.6cqw, 46px); height:clamp(30px, 4.6cqw, 46px);
                border-radius:10px; cursor:pointer; opacity:.78; }
        .tool:hover { background:rgba(255,255,255,.08); opacity:1; }
        .tool.static { cursor:default; }
        .tool.static:hover { background:none; }
        .tool.on { opacity:1; color:var(--accent); }
        .tool svg { width:100%; height:100%; fill:currentColor; padding:3px; box-sizing:border-box; }

        .main { display:grid; gap:clamp(14px, 3cqw, 34px); margin-top:10px; }
        :host(.landscape) .main { grid-template-columns: minmax(150px, 44%) 1fr; align-items:center; }
        :host(.portrait) .main { grid-template-columns: 1fr; justify-items:center; text-align:center; }
        .cover { position:relative; width:100%; aspect-ratio:1/1; border-radius:10px; overflow:hidden;
                 background:rgba(255,255,255,.06); box-shadow:0 18px 44px rgba(0,0,0,.5); }
        :host(.portrait) .cover { width:min(80%, 340px); }
        .cover img { position:absolute; inset:0; z-index:1; width:100%; height:100%; object-fit:cover; display:block; }
        .cover img[hidden] { display:none; }
        .cover .ph { position:absolute; inset:0; display:grid; place-items:center; }
        .cover .ph svg { width:38%; opacity:.3; fill:#fff; }

        .info { min-width:0; width:100%; display:grid; gap:clamp(4px, .9cqw, 10px); }
        .title { font-size:clamp(20px, 4.2cqw, 44px); font-weight:500; line-height:1.15;
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .artist, .album { font-size:clamp(14px, 2.6cqw, 28px); opacity:.62; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .fmt { display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:clamp(12px, 2cqw, 22px); opacity:.55;
               margin-top:clamp(2px, 1cqw, 12px); }
        :host(.portrait) .fmt, :host(.portrait) .out { justify-content:center; }
        .codec { border:1.5px solid currentColor; border-radius:4px; padding:1px 6px; }
        .out { display:flex; align-items:center; gap:12px; font-size:clamp(18px, 3.6cqw, 38px); margin-top:clamp(4px, 1.4cqw, 18px); }
        .out .dot { width:1.5em; height:1.5em; border-radius:50%; background:#fff; display:grid; place-items:center; flex:none; }
        .out .dot svg { width:78%; height:78%; fill:#111; }
        .hide { display:none !important; }

        .transport { display:flex; align-items:center; justify-content:space-between; margin-top:clamp(8px, 2.2cqw, 26px);
                     max-width:640px; }
        :host(.portrait) .transport { justify-content:center; gap:clamp(10px, 4cqw, 28px); max-width:none; }
        button.ctl { all:unset; cursor:pointer; display:grid; place-items:center; width:clamp(38px, 6cqw, 62px); height:clamp(38px, 6cqw, 62px);
                     border-radius:50%; position:relative; }
        button.ctl:active { transform:scale(.95); }
        button.ctl[disabled] { opacity:.3; pointer-events:none; }
        button.ctl svg { width:62%; height:62%; fill:#fff; }
        button.ctl.dim svg { opacity:.75; }
        button.ctl.play { width:clamp(56px, 9cqw, 92px); height:clamp(56px, 9cqw, 92px);
                          box-shadow: inset 0 0 0 2px var(--accent); background:rgba(0,0,0,.18); }
        button.ctl.play svg { width:46%; height:46%; }
        button.ctl.on svg { fill:var(--accent); }

        .vol { display:grid; grid-template-columns:auto 1fr auto; gap:10px; align-items:center; margin-top:4px; max-width:640px; }
        .vol svg { width:22px; height:22px; fill:#fff; opacity:.8; }
        .vol .lvl { font-size:12px; opacity:.7; min-width:3ch; text-align:right; font-variant-numeric:tabular-nums; }
        input[type=range] { width:100%; accent-color:var(--accent); }

        .seek { display:grid; grid-template-columns:auto 1fr auto; gap:14px; align-items:center; margin-top:clamp(8px, 2cqw, 22px);
                font-size:clamp(13px, 2.2cqw, 24px); font-variant-numeric:tabular-nums; opacity:.9; max-width:640px; }
        :host(.portrait) .vol, :host(.portrait) .seek { width:100%; max-width:none; }
        .bar { position:relative; height:clamp(6px, 1.2cqw, 12px); border-radius:2px; background:rgba(255,255,255,.12); cursor:pointer; touch-action:none; }
        .bar .fill { position:absolute; left:0; top:0; bottom:0; border-radius:2px; background:var(--accent); width:0%; }

        .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
        :host(.portrait) .chips { justify-content:center; }
        .chip { all:unset; cursor:pointer; padding:7px 12px; border-radius:999px; background:rgba(255,255,255,.14);
                font-size:12px; white-space:nowrap; max-width:100%; overflow:hidden; text-overflow:ellipsis; }
        .chip b { font-weight:600; opacity:.7; margin-right:4px; }

        .menu { position:absolute; z-index:5; right:14px; top:58px; min-width:230px; max-height:70%; overflow:auto;
                background:rgba(22,19,18,.97); border-radius:14px; padding:6px; box-shadow:0 12px 30px rgba(0,0,0,.55); }
        .menu[hidden] { display:none; }
        .menu .mh { display:flex; align-items:center; gap:6px; padding:6px 10px; font-size:12px; opacity:.6; }
        .menu .mh button { all:unset; cursor:pointer; display:grid; place-items:center; width:24px; height:24px; }
        .menu .mh svg { width:20px; height:20px; fill:#fff; }
        .menu .it { all:unset; display:flex; align-items:center; justify-content:space-between; gap:10px; width:100%; box-sizing:border-box;
                    border-radius:10px; padding:10px 12px; font-size:14px; cursor:pointer; }
        .menu .it:hover { background:rgba(255,255,255,.08); }
        .menu .it.sel { background:rgba(255,255,255,.14); }
        .menu .it small { opacity:.55; }
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
    if (width && width < 460) return "portrait";
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
        <div class="top"><div class="src" id="src"></div><div class="tools" id="tools"></div></div>
        <div class="main">
          <div class="cover"><div class="ph">${svg(BASE_ICONS.music)}</div><img id="cover" alt="" hidden></div>
          <div class="info">
            <div class="title" id="title"></div>
            <div class="artist" id="artist"></div>
            <div class="album" id="album"></div>
            <div class="fmt" id="fmtrow"><span class="codec" id="codec"></span><span id="fmt"></span></div>
            <div class="out" id="outrow"><span class="dot">${svg(BASE_ICONS.pulse)}</span><span id="out"></span></div>
            <div class="transport">
              <button class="ctl" data-act="prev" id="prev">${svg(BASE_ICONS.prev)}</button>
              <button class="ctl play" data-act="play" id="play">${svg(BASE_ICONS.play)}</button>
              <button class="ctl" data-act="next" id="next">${svg(BASE_ICONS.next)}</button>
              <button class="ctl dim" data-act="loop" id="loop"></button>
              <button class="ctl dim" data-act="mute" id="mute"></button>
            </div>
            <div class="vol" id="volrow">${svg(BASE_ICONS.volume)}<input type="range" id="vol" min="0" max="100" step="1"><span class="lvl" id="lvl"></span></div>
            <div class="seek" id="seek"><span id="pos">--:--</span><div class="bar" id="bar"><div class="fill" id="fill"></div></div><span id="dur">--:--</span></div>
          </div>
        </div>
        <div class="chips" id="chips"></div>`;
      this._rendered = true;
      this._coverSrc = null;
      this._toolsHtml = null;
    }
    const a = st.attributes;
    const feat = Number(a.supported_features) || 0;
    const has = (bit) => (feat & bit) === bit;
    const byId = (id) => this._root.getElementById(id);
    const set = (id, text) => { const el = byId(id); if (el && el.textContent !== String(text)) el.textContent = text; };

    set("src", a.source_name || a.source || a.input || "Eversolo");
    this._renderTools(a);
    set("title", a.media_title || (st.state === "idle" ? this._t("nothing") : "—"));
    set("artist", a.media_artist || "");
    set("album", a.media_album_name || "");
    byId("artist").classList.toggle("hide", !a.media_artist);
    byId("album").classList.toggle("hide", !a.media_album_name);

    // FLAC | 96 kHz | 2 ch | 2.63 Mbps | 24 bit, like the app's format line.
    const bits = a.bits ? `${String(a.bits).replace(/\s*bit$/i, "")} bit` : null;
    const parts = [a.sample_rate, a.channels ? `${a.channels} ch` : null, a.bitrate, bits].filter(Boolean);
    set("codec", a.codec || "");
    byId("codec").classList.toggle("hide", !a.codec);
    set("fmt", parts.join("  |  "));
    byId("fmtrow").classList.toggle("hide", !a.codec && !parts.length);
    const out = [a.output_codec, a.output_rate].filter(Boolean).join("  ");
    set("out", out);
    byId("outrow").classList.toggle("hide", !out);

    const playing = st.state === "playing";
    const playBtn = byId("play");
    const playIcon = playing ? BASE_ICONS.pause : BASE_ICONS.play;
    if (playBtn.dataset.icon !== playIcon) { playBtn.innerHTML = svg(playIcon); playBtn.dataset.icon = playIcon; }
    playBtn.toggleAttribute("disabled", !(has(F.PLAY) || has(F.PAUSE)));
    byId("prev").toggleAttribute("disabled", !has(F.PREV));
    byId("next").toggleAttribute("disabled", !has(F.NEXT));
    byId("seek").classList.toggle("hide", !has(F.SEEK) && !a.media_duration);

    const loop = a.loop_mode || "repeat_all";
    const loopBtn = byId("loop");
    const loopHtml = svg(iconPath(LOOP_ICON[loop], "repeat"));
    if (loopBtn.innerHTML !== loopHtml) loopBtn.innerHTML = loopHtml;
    loopBtn.title = this._t(loop);
    loopBtn.toggleAttribute("disabled", !has(F.REPEAT));

    const muteBtn = byId("mute");
    const muteHtml = svg(a.is_volume_muted ? BASE_ICONS.mute : BASE_ICONS.volume);
    if (muteBtn.innerHTML !== muteHtml) muteBtn.innerHTML = muteHtml;
    muteBtn.classList.toggle("on", !!a.is_volume_muted);
    muteBtn.toggleAttribute("disabled", !has(F.VOLUME_MUTE));

    byId("volrow").classList.toggle("hide", !this._config.show_volume || !has(F.VOLUME_SET));
    const vol = byId("vol");
    if (vol && this._root.activeElement !== vol && a.volume_level != null) vol.value = Math.round(a.volume_level * 100);
    set("lvl", a.volume_display ?? (a.volume_level != null ? Math.round(a.volume_level * 100) : ""));

    this._updateProgress();
    this._renderChips(a);
    this._updateCover(a.entity_picture_local || a.entity_picture);
    this._updateBackground(!!this._config.show_background);
  }

  /* Top-right row, in the app's order: DSP, EQ, sub (status), spectrum, VU (buttons), more. */
  _renderTools(a) {
    const tools = [];
    const status = (key, value) => {
      if (value === null || value === undefined) return;
      const name = `${key}-${value ? "on" : "off"}`;
      tools.push(`<span class="tool static${value ? " on" : ""}" title="${esc(`${this._t(key)}: ${this._t(value ? "on" : "off")}`)}">${svg(iconPath(name, "pulse"))}</span>`);
    };
    status("dsp", a.dsp);
    status("eq", a.eq);
    status("sub", a.sub);
    // The app shows the spectrum button for spDisplayMode >= 0 and the VU button for vuDisplayMode >= -1.
    if (a.spectrum_mode != null && a.spectrum_mode >= 0) {
      tools.push(`<button class="tool" data-act="spectrum" title="${esc(this._t("spectrum"))}">${svg(iconPath(SPECTRUM_ICON[a.spectrum_mode] || "spectrum", "pulse"))}</button>`);
    }
    if (a.vu_mode != null && a.vu_mode >= -1) {
      tools.push(`<button class="tool" data-act="vu" title="${esc(this._t("vu"))}">${svg(iconPath(VU_ICON[a.vu_mode] || "vu", "pulse"))}</button>`);
    }
    tools.push(`<button class="tool" data-act="more" title="${esc(this._t("more"))}">${svg(BASE_ICONS.more)}</button>`);
    const html = tools.join("");
    if (html !== this._toolsHtml) {
      this._root.getElementById("tools").innerHTML = html;
      this._toolsHtml = html;
    }
  }

  _renderChips(a) {
    const chips = this._root.getElementById("chips");
    if (!chips) return;
    if (!this._config.show_chips) { chips.innerHTML = ""; chips.classList.add("hide"); return; }
    chips.classList.remove("hide");
    const list = [];
    if ((a.input_list || []).length) list.push(["input", this._t("input"), a.input]);
    if ((a.output_list || []).length) list.push(["output", this._t("output"), a.output]);
    if ((a.app_list || []).length) list.push(["app", this._t("app"), a.app]);
    if ((a.power_list || []).length) list.push(["power", this._t("power"), null]);
    const html = list
      .map(([k, label, val]) => `<button class="chip" data-list="${k}">${val == null || val === ""
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
    if (!colors) { bg.classList.add("off"); this.style.removeProperty("--accent"); return; }
    bg.classList.remove("off");
    const rgb = (c, a = 1) => `rgba(${c.map((v) => Math.round(v)).join(",")},${a})`;
    const dim = (c, k) => c.map((v) => v * k);
    this.style.setProperty("--c1", rgb(dim(colors.primary, 0.75), 0.95));
    this.style.setProperty("--c2", rgb(dim(colors.secondary, 0.55), 0.9));
    // Accent: the cover's dominant hue, lifted so it reads on the dark background.
    const p = colors.primary, max = Math.max(...p) || 1, lift = Math.max(1, 215 / max);
    this.style.setProperty("--accent", rgb(p.map((v) => Math.min(255, v * lift))));
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
    const btn = path.find((el) => el && el.dataset && (el.dataset.act || el.dataset.list || el.dataset.opt));
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
    if (btn.dataset.list) return this._openList(btn.dataset.list);
    switch (btn.dataset.act) {
      case "play": return this._call("media_player", "media_play_pause", { entity_id: entity });
      case "prev": return this._call("media_player", "media_previous_track", { entity_id: entity });
      case "next": return this._call("media_player", "media_next_track", { entity_id: entity });
      case "mute": {
        const muted = !!this._state().attributes.is_volume_muted;
        return this._call("media_player", "volume_mute", { entity_id: entity, is_volume_muted: !muted });
      }
      case "vu": return this._call("eversolo", "vu_next", { entity_id: entity });
      case "spectrum": return this._call("eversolo", "spectrum_next", { entity_id: entity });
      case "loop": return this._openLoop();
      case "more": return menu.hidden ? this._openMore() : (menu.hidden = true);
      case "back": return this._openMore();
    }
  }

  _openMore() {
    const a = this._state().attributes;
    const rows = [
      ["input", this._t("input"), a.input, (a.input_list || []).length],
      ["output", this._t("output"), a.output, (a.output_list || []).length],
      ["app", this._t("app"), a.app, (a.app_list || []).length],
      ["power", this._t("power"), null, (a.power_list || []).length],
    ].filter((r) => r[3]);
    const menu = this._root.getElementById("menu");
    menu.innerHTML = `<div class="mh">${esc(this._t("more"))}</div>` + (rows.length
      ? rows.map(([k, label, cur]) => `<button class="it" data-list="${k}"><span>${esc(label)}</span><small>${esc(cur ?? "")}</small></button>`).join("")
      : `<div class="mh">${esc(this._t("empty"))}</div>`);
    menu.hidden = false;
  }

  _openLoop() {
    const cur = this._state().attributes.loop_mode || "repeat_all";
    this._showMenu(this._t("loopTitle"),
      ["repeat_all", "repeat_one", "shuffle", "play_once"].map((m) => [m, this._t(m), m === cur]), "loop", false);
  }

  _openList(kind) {
    const a = this._state().attributes;
    const lists = {
      input: [a.input_list || [], a.input, "input"],
      output: [a.output_list || [], a.output, "output"],
      app: [a.app_list || [], a.app, "openApp"],
      power: [a.power_list || [], null, "power"],
    };
    const [items, current, title] = lists[kind] || [[], null, kind];
    this._showMenu(this._t(title), items.map((i) => [i, i, i === current]), kind, true);
  }

  _showMenu(title, items, kind, withBack) {
    const menu = this._root.getElementById("menu");
    const back = withBack ? `<button data-act="back">${svg(BASE_ICONS.back)}</button>` : "";
    menu.innerHTML = `<div class="mh">${back}${esc(title)}</div>` +
      (items.length ? items.map(([val, label, sel]) =>
        `<button class="it${sel ? " sel" : ""}" data-opt="${esc(kind)}|${esc(val)}"><span>${esc(label)}</span></button>`).join("")
        : `<div class="mh">${esc(this._t("empty"))}</div>`);
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
    description: "Eversolo DMP/DAC player, styled after the Eversolo app, with ambient cover background",
    preview: false,
  });
}
console.info(`%c EVERSOLO-PLAYER-CARD %c ${EVERSOLO_CARD_VERSION} `, "color:#fff;background:#c68a3c;font-weight:700", "color:#c68a3c;background:#222");
