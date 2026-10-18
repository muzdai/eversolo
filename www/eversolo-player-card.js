class EversoloPlayerCard extends HTMLElement {
  static getConfigElement() { return document.createElement("eversolo-player-card-editor"); }
  static getStubConfig() { return { entity: "media_player.eversolo_player" }; }

  setConfig(config) {
    if (!config.entity) throw new Error("Укажите entity, например media_player.eversolo_player");
    this.config = { name: "Eversolo", ...config };
    this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this.shadowRoot) this._render();
  }

  getCardSize() { return 5; }

  _call(service, data = {}) {
    if (!this._hass) return;
    this._hass.callService("media_player", service, { entity_id: this.config.entity, ...data });
  }

  _fmt(seconds) {
    const n = Math.max(0, Math.floor(Number(seconds) || 0));
    return `${Math.floor(n / 60).toString().padStart(2, "0")}:${(n % 60).toString().padStart(2, "0")}`;
  }

  _render() {
    if (!this.shadowRoot || !this._hass || !this.config) return;
    const e = this._hass.states[this.config.entity];
    if (!e) {
      this.shadowRoot.innerHTML = `<ha-card><div class="missing">Entity not found: ${this.config.entity}</div></ha-card>`;
      return;
    }
    const a = e.attributes || {};
    const title = a.media_title || "Nothing playing";
    const artist = a.media_artist || "";
    const album = a.media_album_name || "";
    const picture = a.entity_picture ? this._hass.hassUrl(a.entity_picture) : "";
    const playing = e.state === "playing";
    const position = Number(a.media_position || 0);
    const duration = Number(a.media_duration || 0);
    const volume = Math.round((Number(a.volume_level || 0)) * 100);
    const elapsed = position + (playing && a.media_position_updated_at ? Math.max(0, (Date.now() - new Date(a.media_position_updated_at).getTime()) / 1000) : 0);
    const pos = duration > 0 ? Math.min(elapsed, duration) : position;
    const progress = duration > 0 ? Math.min(100, pos / duration * 100) : 0;
    const fmt = (v) => this._fmt(v);
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;color:var(--primary-text-color)}
        ha-card{overflow:hidden;border-radius:22px;background:var(--ha-card-background,var(--card-background-color));}
        .wrap{padding:20px;display:grid;grid-template-columns:minmax(130px,42%) 1fr;gap:22px;align-items:center}
        .cover{width:100%;aspect-ratio:1;object-fit:cover;border-radius:14px;background:var(--secondary-background-color);box-shadow:0 8px 24px #0003}
        .placeholder{width:100%;aspect-ratio:1;border-radius:14px;background:linear-gradient(135deg,#444,#222);display:grid;place-items:center}
        .placeholder ha-icon{--mdc-icon-size:64px;color:#aaa}
        .meta{min-width:0}.title{font-size:clamp(20px,2.5vw,30px);font-weight:600;line-height:1.15;overflow-wrap:anywhere}
        .artist{font-size:18px;color:var(--secondary-text-color);margin-top:8px}
        .album{font-size:15px;color:var(--secondary-text-color);margin-top:5px}
        .chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:14px}
        .chip{padding:5px 8px;border-radius:5px;background:var(--secondary-background-color);font-size:12px;color:var(--secondary-text-color)}
        .progress{margin-top:22px}.times{display:flex;justify-content:space-between;font-size:12px;color:var(--secondary-text-color);margin-top:4px}
        input[type=range]{width:100%;accent-color:var(--accent-color);cursor:pointer}
        .controls{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:14px}
        button{border:0;background:transparent;color:var(--primary-text-color);cursor:pointer;display:grid;place-items:center;border-radius:50%;width:42px;height:42px}
        button:hover{background:var(--secondary-background-color)}button ha-icon{--mdc-icon-size:27px}
        button.main{width:60px;height:60px;border:1px solid var(--divider-color)}button.main ha-icon{--mdc-icon-size:34px}
        .volume{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;margin-top:18px;color:var(--secondary-text-color)}
        .volume ha-icon{--mdc-icon-size:22px}.volnum{font-size:12px;min-width:38px;text-align:right}
        .status{font-size:12px;color:var(--secondary-text-color);margin-top:12px}
        .missing{padding:20px}
        @media(max-width:430px){.wrap{grid-template-columns:1fr;gap:18px;padding:15px}.cover,.placeholder{max-height:none}.meta{text-align:left}.title{font-size:24px}.progress{margin-top:18px}}
      </style>
      <ha-card>
        <div class="wrap">
          <div>
            ${picture ? `<img class="cover" src="${picture}" alt="Album cover">` : `<div class="placeholder"><ha-icon icon="mdi:music"></ha-icon></div>`}
          </div>
          <div class="meta">
            <div class="title">${this._escape(title)}</div>
            <div class="artist">${this._escape(artist)}</div>
            ${album ? `<div class="album">${this._escape(album)}</div>` : ""}
            <div class="chips">
              ${a.audio_codec ? `<span class="chip">${this._escape(a.audio_codec)}</span>` : ""}
              ${a.sample_rate ? `<span class="chip">${this._escape(String(a.sample_rate))}</span>` : ""}
              ${a.media_channel ? `<span class="chip">${this._escape(String(a.media_channel))}</span>` : ""}
              ${a.bit_depth ? `<span class="chip">${this._escape(String(a.bit_depth))} bit</span>` : ""}
              ${a.sound_mode ? `<span class="chip">${this._escape(a.sound_mode)}</span>` : ""}
            </div>
            <div class="progress">
              <input id="seek" aria-label="Seek" type="range" min="0" max="${duration || 100}" step="1" value="${duration ? pos : 0}" ${duration ? "" : "disabled"}>
              <div class="times"><span>${fmt(pos)}</span><span>${duration ? fmt(duration) : "--:--"}</span></div>
            </div>
            <div class="controls">
              <button id="prev" title="Previous"><ha-icon icon="mdi:skip-previous"></ha-icon></button>
              <button id="play" class="main" title="${playing ? "Pause" : "Play"}"><ha-icon icon="${playing ? "mdi:pause" : "mdi:play"}"></ha-icon></button>
              <button id="next" title="Next"><ha-icon icon="mdi:skip-next"></ha-icon></button>
              <button id="more" title="Open more-info"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>
            </div>
            <div class="volume">
              <ha-icon icon="mdi:volume-high"></ha-icon>
              <input id="volume" aria-label="Volume" type="range" min="0" max="100" value="${volume}">
              <span class="volnum">${volume}%</span>
            </div>
            <div class="status">${e.state === "unavailable" ? "Player unavailable" : (playing ? "Playing" : e.state === "paused" ? "Paused" : "Ready")}</div>
          </div>
        </div>
      </ha-card>`;
    this.shadowRoot.getElementById("prev")?.addEventListener("click", () => this._call("media_previous_track"));
    this.shadowRoot.getElementById("play")?.addEventListener("click", () => this._call(playing ? "media_pause" : "media_play"));
    this.shadowRoot.getElementById("next")?.addEventListener("click", () => this._call("media_next_track"));
    this.shadowRoot.getElementById("more")?.addEventListener("click", () => {
      const event = new Event("hass-more-info", { bubbles: true, composed: true });
      event.detail = { entityId: this.config.entity };
      this.dispatchEvent(event);
    });
    this.shadowRoot.getElementById("seek")?.addEventListener("change", (ev) => {
      if (duration) this._call("media_seek", { seek_position: Number(ev.target.value) });
    });
    this.shadowRoot.getElementById("volume")?.addEventListener("change", (ev) => {
      this._call("volume_set", { volume_level: Number(ev.target.value) / 100 });
    });
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
  }
}

customElements.define("eversolo-player-card", EversoloPlayerCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "eversolo-player-card",
  name: "Eversolo Player",
  description: "Custom player card for Eversolo with album art, transport controls, seek and volume."
});
