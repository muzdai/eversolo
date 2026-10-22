/* Eversolo player card for Home Assistant — https://github.com/muzdai/eversolo
 * Styled after the Eversolo Control app's now-playing screen:
 * - landscape / portrait layout from the screen orientation (landscape when unknown)
 * - background colours sampled from the album cover (ambient style)
 * - DSP / EQ / sub status, spectrum and VU buttons, menu with inputs, outputs, apps, power
 * - decorative level bars behind the controls while playing (the device does not expose
 *   real levels over its API, so these are animated, not measured)
 * Icons come from the eversolo:* icon set (eversolo-icons.js) when it is loaded.
 */
window.customCards = window.customCards || [];
const EVERSOLO_CARD_VERSION = "2.6.1";

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

/* The integration loads eversolo-icons.js on every page; if it has not arrived yet
 * (or the card is used without it), load it from the integration's static path. */
if (!window.EversoloIcons && !window.__eversoloIconsRequested) {
  window.__eversoloIconsRequested = true;
  import(`/eversolo/eversolo-icons.js?v=${EVERSOLO_CARD_VERSION}`).catch(() => {});
}

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
    this._config = { show_background: true, show_spectrum: true, show_volume: true, show_chips: false, layout: "auto", ...config };
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
    this._specOn = false;
    cancelAnimationFrame(this._raf);
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
        .amb { position:absolute; left:-15%; top:-15%; width:130%; height:130%; object-fit:cover;
               filter: blur(60px) saturate(1.6) brightness(.7); opacity:0; transition: opacity .9s ease; }
        .amb.on { opacity:.95; }
        .bg { position:absolute; inset:-30%; background:
                radial-gradient(50% 60% at 25% 30%, var(--c1), transparent 72%),
                radial-gradient(55% 65% at 85% 80%, var(--c2), transparent 75%),
                #0d0b0a;
              filter: blur(42px) saturate(1.15); transition: background 0.8s ease; }
        .bg.off { background:#0d0b0a; }
        .amb.on + .bg { opacity:.55; }
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

        .info { position:relative; min-width:0; width:100%; display:grid; gap:clamp(4px, .9cqw, 10px); }
        .info > :not(.spec) { position:relative; z-index:1; }
        .spec { position:absolute; left:-6px; right:-6px; bottom:0; height:64%; z-index:0; pointer-events:none;
                width:calc(100% + 12px); opacity:.6; }
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
      <img class="amb" id="amb" alt=""><div class="bg" id="bg"></div><div class="shade"></div>
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
            <canvas class="spec" id="spec"></canvas>
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
      this._specIdleDrawn = false;
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

    let playing = st.state === "playing";
    const hold = this._playHold;
    if (hold && Date.now() < hold.until && st.last_updated === hold.stamp) playing = hold.playing;
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
    this._setSpectrum(playing && this._config.show_spectrum !== false);
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
    // Right after a seek, show the chosen position until the player reports the new one.
    const sh = this._seekHold;
    if (sh && Date.now() < sh.until && a.media_position_updated_at === sh.stamp) {
      pos = sh.pos + (st.state === "playing" ? (Date.now() - sh.at) / 1000 : 0);
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
    const amb = this._root.getElementById("amb");
    if (!img) return;
    if (!url) {
      img.hidden = true; this._coverSrc = null; this._setColors(null);
      if (amb) { amb.classList.remove("on"); amb.removeAttribute("src"); }
      return;
    }
    if (amb && amb.dataset.src !== url && this._config.show_background) {
      amb.dataset.src = url;
      amb.onload = () => amb.classList.add("on");
      amb.onerror = () => amb.classList.remove("on");
      amb.src = url;
    }
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
    this._accent = rgb(p.map((v) => Math.min(255, v * lift)));
    this.style.setProperty("--accent", this._accent);
  }

  _updateBackground(enabled) {
    const bg = this._root.getElementById("bg");
    if (bg) bg.style.display = enabled ? "" : "none";
    const amb = this._root.getElementById("amb");
    if (amb) amb.style.display = enabled ? "" : "none";
  }

  /* ---- decorative level bars ----------------------------------------
   * Segmented bars like the Eversolo screen. The device API has no level data,
   * so the motion is generated: a falling-off spectrum envelope, random energy
   * per band, a light pulse and slowly falling peak caps. Paused -> bars sink. */
  _setSpectrum(playing) {
    this._specPlaying = playing;
    // "Reduce motion" (e.g. Windows animation effects off) only calms the bars down: they
    // are the point of the feature, so they are not switched off. show_spectrum: false does that.
    this._specCalm = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    // Playing: animate. Paused/idle: draw the unlit segment grid once, like the device screen.
    const wanted = playing || !this._specIdleDrawn;
    if (wanted && !this._specOn) {
      this._specOn = true;
      this._raf = requestAnimationFrame((t) => this._specFrame(t));
    }
  }

  _specFrame(ts) {
    if (!this._specOn) return;
    const next = () => { this._raf = requestAnimationFrame((t) => this._specFrame(t)); };
    if (ts - (this._specLast || 0) < 33) return next(); // ~30 fps is plenty
    this._specLast = ts;
    const c = this._root && this._root.getElementById("spec");
    if (!c || !c.clientWidth) return next();
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    }
    const barW = Math.max(8, Math.min(18, w / 34)), gap = barW * 0.45;
    const n = Math.max(6, Math.floor((w + gap) / (barW + gap)));
    if (!this._lv || this._lv.length !== n) {
      this._lv = new Array(n).fill(0); this._tg = new Array(n).fill(0); this._pk = new Array(n).fill(0);
    }
    const lv = this._lv, tg = this._tg, pk = this._pk;
    if (ts - (this._specRetarget || 0) > (this._specCalm ? 280 : 110)) {
      this._specRetarget = ts;
      const pulse = Math.sin(ts / 235) > 0.55 ? 0.22 : 0;
      for (let i = 0; i < n; i++) {
        const f = i / (n - 1);
        const env = 0.92 - 0.5 * f + 0.14 * Math.sin(ts / 900 + i * 0.7);
        tg[i] = this._specPlaying ? Math.min(1, Math.max(0.04, env * (0.3 + 0.7 * Math.random()) + pulse * (1 - f))) : 0;
      }
    }
    let alive = false;
    for (let i = 0; i < n; i++) {
      lv[i] += (tg[i] - lv[i]) * (tg[i] > lv[i] ? 0.45 : 0.16);
      pk[i] = Math.max(lv[i], pk[i] - 0.01);
      if (pk[i] > 0.01) alive = true;
    }
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const segH = Math.max(3, h / 30), segGap = segH * 0.55, step = segH + segGap;
    const rows = Math.floor(h / step);
    const x0 = (w - (n * barW + (n - 1) * gap)) / 2;
    for (let i = 0; i < n; i++) {
      const x = x0 + i * (barW + gap);
      const on = Math.round(lv[i] * rows);
      for (let r = 0; r < rows; r++) {
        ctx.fillStyle = r < on ? "rgba(255,255,255,0.42)" : "rgba(255,255,255,0.05)";
        ctx.fillRect(x, h - (r + 1) * step + segGap, barW, segH);
      }
      const pr = Math.round(pk[i] * rows);
      if (pr > 0) {
        ctx.fillStyle = this._accent || "rgba(255,210,170,0.7)";
        ctx.globalAlpha = 0.75;
        ctx.fillRect(x, h - pr * step - step + segGap, barW, segH);
        ctx.globalAlpha = 1;
      }
    }
    if (!this._specPlaying && !alive) { this._specOn = false; this._specIdleDrawn = true; return; }
    next();
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
      case "play": {
        const st = this._state();
        this._playHold = { playing: st.state !== "playing", stamp: st.last_updated, until: Date.now() + 3000 };
        this._render();
        return this._call("media_player", "media_play_pause", { entity_id: entity });
      }
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
      if (target != null) {
        this._seekHold = { pos: target, at: Date.now(), until: Date.now() + 4000, stamp: this._state()?.attributes.media_position_updated_at };
        this._call("media_player", "media_seek", { entity_id: this._config.entity, seek_position: target });
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    seek(ev);
  }
}

/* ---- Screen mirror card -------------------------------------------------
 * The device screen as in the app's "remote screen": H.264 from the player,
 * relayed by the integration over the HA websocket, decoded with WebCodecs.
 * Tap, drag and swipe on the picture act on the player's touchscreen. */
const MIRROR_STRINGS = {
  en: { connecting: "Connecting to the player screen…", ended: "Mirroring stopped. Tap to reconnect.",
        nocodec: "This browser cannot decode the stream (WebCodecs is missing).",
        insecure: "The screen needs Home Assistant opened over HTTPS (browsers allow video decoding only there).", failed: "Could not start mirroring: {e}",
        back: "Back", home: "Home", voldown: "Volume down", volup: "Volume up" },
  ru: { connecting: "Подключение к экрану плеера…", ended: "Трансляция остановлена. Нажмите, чтобы переподключиться.",
        nocodec: "Браузер не умеет декодировать поток (нет WebCodecs).",
        insecure: "Для экрана откройте Home Assistant по HTTPS: браузеры разрешают декодирование видео только там.", failed: "Не удалось запустить трансляцию: {e}",
        back: "Назад", home: "Домой", voldown: "Тише", volup: "Громче" },
};
/* Shown instead of the error when the player cannot be reached (switched off, asleep, unplugged). */
const MIRROR_OFFLINE = {
  en: ["Device offline", "Tap to retry"], ru: ["Устройство не в сети", "Нажмите, чтобы повторить"],
  uk: ["Пристрій не в мережі", "Натисніть, щоб повторити"], be: ["Прылада не ў сетцы", "Націсніце, каб паўтарыць"],
  ka: ["მოწყობილობა ხაზგარეშეა", "შეეხეთ ხელახლა საცდელად"], de: ["Gerät offline", "Zum Wiederholen tippen"],
  fr: ["Appareil hors ligne", "Touchez pour réessayer"], es: ["Dispositivo sin conexión", "Toca para reintentar"],
  it: ["Dispositivo offline", "Tocca per riprovare"], pt: ["Dispositivo offline", "Toque para tentar novamente"],
  nl: ["Apparaat offline", "Tik om opnieuw te proberen"], pl: ["Urządzenie offline", "Dotknij, aby ponowić"],
  cs: ["Zařízení je offline", "Klepnutím zkusíte znovu"], tr: ["Cihaz çevrimdışı", "Yeniden denemek için dokunun"],
  hy: ["Սարքը ցանցից դուրս է", "Հպեք՝ կրկին փորձելու համար"], az: ["Cihaz oflayndır", "Təkrar cəhd üçün toxunun"],
  kk: ["Құрылғы желіден тыс", "Қайталау үшін түртіңіз"], lv: ["Ierīce bezsaistē", "Pieskarieties, lai mēģinātu vēlreiz"],
  lt: ["Įrenginys neprisijungęs", "Palieskite, kad bandytumėte dar kartą"], et: ["Seade on võrguühenduseta", "Puudutage uuesti proovimiseks"],
  zh: ["设备离线", "点击重试"], ja: ["デバイスはオフラインです", "タップして再試行"], ko: ["기기가 오프라인입니다", "탭하여 다시 시도"],
};
const OFFLINE_RETRY_MS = 15000;
const MIRROR_ICONS = {
  back: "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20z",
  home: "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
  voldown: "M18.5 12A4.5 4.5 0 0 0 16 8v8a4.5 4.5 0 0 0 2.5-4zM5 9v6h4l5 5V4L9 9H5z",
  volup: BASE_ICONS.volume,
};

const b64ToBytes = (b64) => {
  const bin = atob(b64), out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
};

/* avc1.PPCCLL from the SPS that follows the first Annex-B start code. */
const avcCodec = (config) => {
  for (let i = 0; i + 7 < config.length; i++) {
    const sc4 = config[i] === 0 && config[i + 1] === 0 && config[i + 2] === 0 && config[i + 3] === 1;
    const sc3 = config[i] === 0 && config[i + 1] === 0 && config[i + 2] === 1;
    const n = sc4 ? i + 4 : sc3 ? i + 3 : -1;
    if (n >= 0 && (config[n] & 0x1f) === 7) {
      const hex = (v) => v.toString(16).padStart(2, "0");
      return `avc1.${hex(config[n + 1])}${hex(config[n + 2])}${hex(config[n + 3])}`;
    }
  }
  return "avc1.42E01F";
};

class EversoloMirrorCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity || !config.entity.startsWith("media_player.")) {
      throw new Error("eversolo-mirror-card: set `entity` to the Eversolo media_player");
    }
    this._config = { show_nav: true, ...config };
    if (!this.shadowRoot) this._build();
    this._root.getElementById("nav").classList.toggle("hide", !this._config.show_nav);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) { this._wasOnline = this._entityOnline(); if (this.isConnected) this._start(); return; }
    // Player came back (entity available again): reconnect right away instead of waiting for the retry timer.
    // Only on the transition, so a reachable-but-refusing player is not hammered on every state update.
    const online = this._entityOnline();
    if (this._offline && online && this._wasOnline === false) this._restart();
    this._wasOnline = online;
  }

  _entityOnline() {
    const st = this._hass && this._hass.states[this._config.entity];
    return !!st && st.state !== "unavailable" && st.state !== "unknown";
  }

  getCardSize() { return 6; }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }

  static getStubConfig(hass) {
    const e = Object.keys(hass.states).find(
      (s) => s.startsWith("media_player.") && hass.states[s].attributes && "vu_mode" in hass.states[s].attributes,
    );
    return { entity: e || "media_player.eversolo" };
  }

  _offlineText() {
    const lang = ((this._hass && (this._hass.locale?.language || this._hass.language)) || "en").toLowerCase();
    return MIRROR_OFFLINE[lang] || MIRROR_OFFLINE[lang.split("-")[0]] || MIRROR_OFFLINE.en;
  }

  _t(key) {
    const lang = (this._hass && (this._hass.locale?.language || this._hass.language)) || "en";
    const table = MIRROR_STRINGS[lang.split("-")[0]] || MIRROR_STRINGS.en;
    return table[key] ?? MIRROR_STRINGS.en[key] ?? key;
  }

  _build() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; background:#000; border-radius:var(--ha-card-border-radius, 16px); overflow:hidden; color:#eee;
                font-family:var(--ha-font-family-body, system-ui, sans-serif); }
        .screen { position:relative; width:100%; aspect-ratio:var(--ratio, 2 / 1); background:#000; }
        canvas { position:absolute; inset:0; width:100%; height:100%; touch-action:none; cursor:pointer; display:block; }
        .msg { position:absolute; inset:0; display:grid; place-items:center; text-align:center; padding:16px;
               font-size:14px; opacity:.75; background:rgba(0,0,0,.55); cursor:pointer; }
        .msg[hidden] { display:none; }
        .msg.offline { opacity:1; background:radial-gradient(ellipse at center, #1a1a1d 0%, #050506 75%); align-content:center; gap:10px; }
        .msg .big { font-size:clamp(18px, 4.2vw, 28px); font-weight:600; letter-spacing:.14em; text-transform:uppercase;
                    color:#e9e9ec; display:flex; align-items:center; gap:12px; }
        .msg .big::before { content:""; width:10px; height:10px; border-radius:50%; background:#e5484d;
                            box-shadow:0 0 10px 2px rgba(229,72,77,.55); flex:none; }
        .msg .small { font-size:12px; letter-spacing:.06em; opacity:.45; }
        .nav { display:flex; justify-content:center; gap:28px; padding:6px 0 8px; background:#0b0b0c; }
        .nav.hide { display:none; }
        .nav button { all:unset; cursor:pointer; width:40px; height:40px; display:grid; place-items:center; border-radius:50%; }
        .nav button:active { background:rgba(255,255,255,.12); }
        .nav svg { width:24px; height:24px; fill:#ddd; }
      </style>
      <div class="screen" id="screen"><canvas id="cv"></canvas><div class="msg" id="msg"></div></div>
      <div class="nav" id="nav">
        ${["back", "home", "voldown", "volup"].map((k) =>
          `<button data-key="${k}"><svg viewBox="0 0 24 24"><path d="${MIRROR_ICONS[k]}"/></svg></button>`).join("")}
      </div>`;
    this._root = this.shadowRoot;
    this._canvas = this._root.getElementById("cv");
    this._ctx = this._canvas.getContext("2d");
    this._root.getElementById("msg").addEventListener("click", () => { if (this._ended || this._offline) this._restart(); });
    this._root.getElementById("nav").addEventListener("click", (ev) => {
      const btn = ev.composedPath().find((el) => el && el.dataset && el.dataset.key);
      if (!btn) return;
      const key = { back: "Back", home: "Home", voldown: "VolumeDown", volup: "VolumeUp" }[btn.dataset.key];
      this._send({ type: "eversolo/mirror/key", key });
    });
    for (const [ev, fn] of [["pointerdown", "_down"], ["pointermove", "_move"], ["pointerup", "_up"], ["pointercancel", "_up"]]) {
      this._canvas.addEventListener(ev, (e) => this[fn](e));
    }
  }

  connectedCallback() {
    this._vis = () => (document.hidden ? this._stop() : this._start());
    document.addEventListener("visibilitychange", this._vis);
    if (this._hass) this._start();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._vis);
    this._stop();
    this._clearRetry();
  }

  _status(text) {
    const m = this._root.getElementById("msg");
    m.classList.remove("offline");
    m.textContent = text || "";
    m.hidden = !text;
  }

  _showOffline() {
    this._offline = true;
    const [big, small] = this._offlineText();
    const m = this._root.getElementById("msg");
    m.classList.add("offline");
    m.replaceChildren();
    for (const [cls, text] of [["big", big], ["small", small]]) {
      const el = document.createElement("div");
      el.className = cls; el.textContent = text; m.appendChild(el);
    }
    m.hidden = false;
    this._ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
    this._clearRetry();
    this._retry = setTimeout(() => { this._retry = null; if (this._offline && this.isConnected) this._restart(); }, OFFLINE_RETRY_MS);
  }

  _clearRetry() {
    if (this._retry) { clearTimeout(this._retry); this._retry = null; }
  }

  async _start() {
    if (this._unsub || this._starting || !this._hass || document.hidden) return;
    for (const b of this._root.querySelectorAll(".nav button")) b.title = this._t(b.dataset.key);
    if (typeof VideoDecoder === "undefined") { this._status(this._t(window.isSecureContext ? "nocodec" : "insecure")); return; }
    this._starting = true;
    this._ended = false;
    this._clearRetry();
    if (!this._entityOnline()) { this._starting = false; this._showOffline(); return; }
    if (!this._offline) this._status(this._t("connecting"));
    try {
      this._unsub = await this._hass.connection.subscribeMessage((m) => this._onMessage(m), {
        type: "eversolo/mirror/subscribe", entity_id: this._config.entity,
      });
      if (this._offline) { this._offline = false; this._status(this._t("connecting")); }
    } catch (err) {
      // The usual cause is a switched-off player (connection refused / timeout to its address).
      // Only a setup problem (old integration, wrong entity) is spelled out; everything else reads as "offline".
      if (err && (err.code === "unknown_command" || err.code === "not_found")) {
        this._ended = true;
        this._status(this._t("failed").replace("{e}", err.message || err.code));
      } else {
        this._showOffline();
      }
    } finally {
      this._starting = false;
    }
  }

  _stop() {
    const unsub = this._unsub;
    this._unsub = null;
    if (unsub) unsub().catch(() => {});
    this._closeDecoder();
  }

  _restart() { this._stop(); this._start(); }

  _closeDecoder() {
    if (this._decoder && this._decoder.state !== "closed") { try { this._decoder.close(); } catch (e) { /* closed */ } }
    this._decoder = null;
    this._gotKey = false;
  }

  _onMessage(m) {
    if (m.type === "config") return this._configure(m);
    if (m.type === "frame") return this._frame(m);
    if (m.type === "ended") {
      this._stop();
      if (!this._entityOnline()) { this._showOffline(); return; }
      this._ended = true; this._status(this._t("ended"));
    }
  }

  _configure(m) {
    this._closeDecoder();
    this._config_bytes = b64ToBytes(m.data);
    this._w = m.width || 960; this._h = m.height || 480;
    this._canvas.width = this._w; this._canvas.height = this._h;
    this.style.setProperty("--ratio", `${this._w} / ${this._h}`);
    this._ts = 0;
    this._decoder = new VideoDecoder({
      output: (frame) => { this._ctx.drawImage(frame, 0, 0, this._w, this._h); frame.close(); this._status(""); },
      error: (e) => { this._status(this._t("failed").replace("{e}", e.message)); this._closeDecoder(); },
    });
    // No description: chunks are Annex-B, so SPS/PPS go in front of every key frame.
    this._decoder.configure({ codec: avcCodec(this._config_bytes), optimizeForLatency: true });
  }

  _frame(m) {
    const dec = this._decoder;
    if (!dec || dec.state !== "configured") return;
    if (!m.key && !this._gotKey) return;
    if (!m.key && dec.decodeQueueSize > 30) return; // falling behind: wait for the next key frame
    let data = b64ToBytes(m.data);
    if (m.key) {
      this._gotKey = true;
      const joined = new Uint8Array(this._config_bytes.length + data.length);
      joined.set(this._config_bytes, 0); joined.set(data, this._config_bytes.length);
      data = joined;
    }
    this._ts += 33333;
    try {
      dec.decode(new EncodedVideoChunk({ type: m.key ? "key" : "delta", timestamp: this._ts, data }));
    } catch (e) {
      this._gotKey = false;
    }
  }

  /* ---- touch ----------------------------------------------------------- */
  _point(e) {
    const r = this._canvas.getBoundingClientRect();
    return {
      x: Math.round(((e.clientX - r.left) / r.width) * (this._w || 960)),
      y: Math.round(((e.clientY - r.top) / r.height) * (this._h || 480)),
    };
  }

  _send(msg) {
    if (!this._hass) return;
    this._hass.connection.sendMessagePromise({ entity_id: this._config.entity, ...msg }).catch(() => {});
  }

  _down(e) {
    if (!this._unsub) return;
    this._canvas.setPointerCapture(e.pointerId);
    this._pressed = true;
    this._lastMove = 0;
    const p = this._point(e);
    this._send({ type: "eversolo/mirror/touch", action: 0, ...p });
  }

  _move(e) {
    if (!this._pressed) return;
    const now = performance.now();
    if (now - this._lastMove < 16) return; // ~60 updates per second is enough for swipes
    this._lastMove = now;
    this._send({ type: "eversolo/mirror/touch", action: 2, ...this._point(e) });
  }

  _up(e) {
    if (!this._pressed) return;
    this._pressed = false;
    this._send({ type: "eversolo/mirror/touch", action: 1, ...this._point(e) });
  }
}

if (!customElements.get("eversolo-mirror-card")) {
  customElements.define("eversolo-mirror-card", EversoloMirrorCard);
}
if (!window.customCards.some((c) => c.type === "eversolo-mirror-card")) {
  window.customCards.push({
    type: "eversolo-mirror-card",
    name: "Eversolo Screen",
    description: "The Eversolo player's screen, mirrored and controllable by touch",
    preview: false,
  });
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
