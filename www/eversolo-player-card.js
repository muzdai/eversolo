class EversoloPlayerCard extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = null;
    this._timer = null;
    this._dragSeek = false;
    this._seekValue = null;
    this._dragVolume = false;
    this._volumeValue = null;
    this.attachShadow({ mode: 'open' });
  }

  setConfig(config) {
    if (!config.entity) throw new Error('Укажите entity, например media_player.eversolo_player');
    this._config = {
      entity: config.entity,
      name: config.name || 'EVERSOLO DMP-A6',
      refresh_interval: Math.max(100, Number(config.refresh_interval || 100)),
      accent: config.accent || '#d6b77a',
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._dragSeek && !this._dragVolume) this._render();
    // Render at 10 Hz; fresh device data comes from the integration coordinator.
    if (!this._timer) {
      this._timer = setInterval(() => {
        if (!this._dragSeek && !this._dragVolume) this._render();
      }, this._config?.refresh_interval || 100);
    }
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
  }

  getCardSize() { return 5; }

  _esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  _formatTime(value) {
    const n = Math.max(0, Math.floor(Number(value) || 0));
    return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  }

  _getData() {
    const entity = this._hass?.states?.[this._config?.entity];
    const a = entity?.attributes || {};
    const nested = a.playingMusic || a.playing_music || {};
    const info = a.everSoloPlayInfo || a.eversolo_play_info || {};
    const state = entity?.state || 'unavailable';
    const title = a.media_title || nested.title || a.title || 'Нет активного трека';
    const artist = a.media_artist || nested.artist || a.artist || 'Eversolo DMP-A6';
    const album = a.media_album_name || nested.album || a.album || '';
    const picture = a.entity_picture || nested.albumArt || nested.albumArtBig || a.albumArt || '';
    const duration = Number(a.media_duration ?? nested.duration / 1000 ?? 0) || 0;
    let position = Number(a.media_position ?? info.currentPosition / 1000 ?? 0) || 0;
    const updated = a.media_position_updated_at ? new Date(a.media_position_updated_at).getTime() : 0;
    const playing = state === 'playing' || Number(info.playStatus) === 1;
    if (playing && updated > 0 && Number.isFinite(updated)) position += Math.max(0, (Date.now() - updated) / 1000);
    position = Math.min(duration || Infinity, position);
    const volume = this._volumeValue ?? (typeof a.volume_level === 'number' ? a.volume_level * 100 : (Number(a.currenttVolume ?? a.volumeData?.currenttVolume) / 2 || 0));
    const db = a.volume_db || a.volumeData?.display || nested.volumeData?.display || '';
    const source = a.source || nested.streamId || a.streamId || '';
    const format = [nested.extension || a.audio_format || a.extension, nested.bits ? `${nested.bits} bit` : '', nested.sampleRate || a.sample_rate].filter(Boolean).join(' · ');
    const quality = nested.audioQuality || nested.streamQuality || a.audio_quality || '';
    const bitrate = nested.bitrate || a.bitrate || '';
    const output = a.volumeData?.volumeTag || a.output || a.output_name || '';
    return { entity, a, state, title, artist, album, picture, duration, position, playing, volume, db, source, format, quality, bitrate, output };
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const d = this._getData();
    const accent = this._config.accent;
    const pct = d.duration > 0 ? Math.min(100, d.position / d.duration * 100) : 0;
    const image = d.picture ? (d.picture.startsWith('http') ? d.picture : d.picture) : '';
    const playIcon = d.playing
      ? '<svg viewBox="0 0 24 24"><path d="M8 5h3v14H8zM15 5h3v14h-3z"/></svg>'
      : '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
    const sourceLabel = d.source ? String(d.source).toUpperCase() : 'LOCAL PLAYER';
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;color:var(--primary-text-color,#f5f3ef);font-family:var(--paper-font-body1_-_font-family,Roboto,Arial,sans-serif);--ev-accent:${accent}}
        *{box-sizing:border-box}.shell{position:relative;overflow:hidden;border-radius:24px;padding:clamp(16px,2.5vw,28px);background:radial-gradient(ellipse at 80% 0%,color-mix(in srgb,var(--ev-accent) 13%,transparent),transparent 48%),linear-gradient(135deg,#20201f 0%,#151515 60%,#101010 100%);border:1px solid #383632;box-shadow:0 16px 40px #0003}
        .top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:22px}.brand{font-size:11px;font-weight:700;letter-spacing:.22em;color:#c9c3b8}.model{font-size:10px;letter-spacing:.12em;color:#858078;margin-top:5px}.live{display:flex;align-items:center;gap:7px;font-size:10px;letter-spacing:.12em;color:#b9b4a9;text-transform:uppercase}.dot{width:7px;height:7px;border-radius:50%;background:${d.entity && d.state!=='unavailable'?'#7dbb8b':'#a66d68'};box-shadow:0 0 10px currentColor}
        .main{display:grid;grid-template-columns:minmax(150px,36%) minmax(0,1fr);gap:clamp(18px,3vw,32px);align-items:center}.cover-wrap{position:relative;aspect-ratio:1;max-width:360px;width:100%;border-radius:16px;overflow:hidden;background:linear-gradient(145deg,#393733,#171717);box-shadow:0 12px 28px #0008}.cover{width:100%;height:100%;display:block;object-fit:cover}.cover-empty{height:100%;display:flex;align-items:center;justify-content:center;color:#b7a985}.cover-empty svg{width:25%;fill:currentColor}.eyebrow{font-size:10px;letter-spacing:.18em;color:var(--ev-accent);text-transform:uppercase;margin-bottom:10px}.title{font-size:clamp(23px,3.2vw,38px);line-height:1.1;font-weight:650;letter-spacing:-.035em;overflow-wrap:anywhere}.artist{font-size:clamp(14px,1.6vw,18px);color:#b9b5ad;margin-top:9px}.album{font-size:12px;color:#817e77;margin-top:6px}.tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:17px}.tag{border:1px solid #4a4740;border-radius:7px;padding:6px 9px;color:#c6c0b4;font-size:10px;letter-spacing:.06em;background:#ffffff05}.tag.gold{color:var(--ev-accent);border-color:color-mix(in srgb,var(--ev-accent) 45%,#4a4740)}
        .timeline{margin-top:24px}.times{display:flex;justify-content:space-between;font-size:11px;font-variant-numeric:tabular-nums;color:#8f8b83;margin-bottom:9px}.seek{width:100%;height:4px;appearance:none;background:linear-gradient(to right,var(--ev-accent) 0%,var(--ev-accent) ${pct}%,#45433e ${pct}%,#45433e 100%);border-radius:99px;outline:none;cursor:pointer;display:block}.seek::-webkit-slider-thumb{appearance:none;width:11px;height:11px;border-radius:50%;background:#f4e2b8;border:2px solid var(--ev-accent);box-shadow:0 0 0 4px #d6b77a22}.seek::-moz-range-thumb{width:9px;height:9px;border-radius:50%;background:#f4e2b8;border:2px solid var(--ev-accent)}
        .controls{display:flex;align-items:center;justify-content:center;gap:clamp(16px,3vw,28px);margin-top:22px}.ctrl{border:0;background:transparent;color:#c5c0b7;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background .15s,color .15s,transform .15s}.ctrl:hover{background:#ffffff12;color:#fff}.ctrl:active{transform:scale(.93)}.ctrl svg{width:23px;height:23px;fill:currentColor}.ctrl.primary{width:58px;height:58px;background:var(--ev-accent);color:#191815;box-shadow:0 5px 18px color-mix(in srgb,var(--ev-accent) 22%,transparent)}.ctrl.primary:hover{background:#e7cd98}.ctrl.primary svg{width:25px;height:25px}.lower{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;align-items:center;margin-top:24px;padding-top:19px;border-top:1px solid #373530}.volume-line{display:flex;align-items:center;gap:12px}.vol-icon{width:20px;height:20px;fill:#aaa49a;flex-shrink:0}.vol-range{width:100%;min-width:50px;height:3px;accent-color:var(--ev-accent);cursor:pointer}.db{min-width:66px;text-align:right;font-size:12px;color:#d0c7b5;font-variant-numeric:tabular-nums}.output{text-align:right}.output-label{font-size:9px;letter-spacing:.16em;color:#817d75;text-transform:uppercase}.output-value{font-size:12px;color:#d0c8b9;margin-top:5px}.offline{color:#d49a92;font-size:11px;margin-top:12px}
        @media(max-width:520px){.shell{border-radius:18px;padding:15px}.top{margin-bottom:16px}.main{grid-template-columns: minmax(96px,34%) minmax(0,1fr);gap:14px;align-items:start}.cover-wrap{border-radius:11px}.title{font-size:22px}.artist{font-size:14px;margin-top:7px}.album{font-size:11px}.eyebrow{font-size:9px;margin-bottom:7px}.tags{gap:5px;margin-top:12px}.tag{font-size:9px;padding:5px 6px}.timeline{margin-top:18px}.controls{margin-top:18px;gap:17px}.ctrl{width:34px;height:34px}.ctrl.primary{width:52px;height:52px}.lower{margin-top:18px;padding-top:15px;gap:10px}.db{min-width:55px;font-size:11px}.output-value{font-size:11px}}
        @media(max-width:360px){.main{grid-template-columns:1fr}.cover-wrap{max-width:210px;margin:0 auto 4px}.track{text-align:center}.tags{justify-content:center}.title{font-size:25px}}
      </style>
      <ha-card><div class="shell">
        <div class="top"><div><div class="brand">EVERSOLO</div><div class="model">${this._esc(this._config.name)}</div></div><div class="live"><span class="dot"></span>${d.playing?'PLAYING':d.state==='unavailable'?'OFFLINE':'READY'}</div></div>
        <div class="main">
          <div class="cover-wrap">${image ? `<img class="cover" src="${this._esc(image)}" alt="Album cover" loading="eager"/>` : '<div class="cover-empty"><svg viewBox="0 0 24 24"><path d="M12 3v12.2a3.8 3.8 0 1 1-2-3.35V6l10-2v11.2a3.8 3.8 0 1 1-2-3.35V3z"/></svg></div>'}</div>
          <div class="track"><div class="eyebrow">Now playing · ${this._esc(sourceLabel)}</div><div class="title">${this._esc(d.title)}</div><div class="artist">${this._esc(d.artist)}</div><div class="album">${this._esc(d.album)}</div>
            <div class="tags">${d.format?`<span class="tag">${this._esc(d.format)}</span>`:''}${d.quality?`<span class="tag gold">${this._esc(d.quality)}</span>`:''}${d.bitrate?`<span class="tag">${this._esc(d.bitrate)}</span>`:''}</div>
          </div>
        </div>
        <div class="timeline"><div class="times"><span>${this._formatTime(this._dragSeek && this._seekValue!==null ? this._seekValue : d.position)}</span><span>${this._formatTime(d.duration)}</span></div><input class="seek" aria-label="Позиция воспроизведения" type="range" min="0" max="${Math.max(1,d.duration)}" step="1" value="${Math.min(d.duration||0,this._dragSeek&&this._seekValue!==null?this._seekValue:d.position)}" /></div>
        <div class="controls"><button class="ctrl" data-action="previous" title="Предыдущий трек" aria-label="Предыдущий трек"><svg viewBox="0 0 24 24"><path d="M6 5h2v14H6zM20 6v12L9 12z"/></svg></button><button class="ctrl primary" data-action="playpause" title="Play / Pause" aria-label="Play / Pause">${playIcon}</button><button class="ctrl" data-action="next" title="Следующий трек" aria-label="Следующий трек"><svg viewBox="0 0 24 24"><path d="M16 5h2v14h-2zM4 6v12l11-6z"/></svg></button></div>
        <div class="lower"><div class="volume-line"><svg class="vol-icon" viewBox="0 0 24 24"><path d="M3 9v6h4l5 4V5L7 9H3zm13.5 3a4.5 4.5 0 0 0-2.5-4.03v8.05a4.5 4.5 0 0 0 2.5-4.02zM14 3.23v2.06a7 7 0 0 1 0 13.42v2.06a9 9 0 0 0 0-17.54z"/></svg><input class="vol-range" aria-label="Громкость" type="range" min="0" max="100" step="1" value="${Math.max(0,Math.min(100,d.volume))}"/><span class="db">${this._esc(d.db || `${Math.round(d.volume)}%`)}</span></div><div class="output"><div class="output-label">Audio output</div><div class="output-value">${this._esc(d.output || 'DMP-A6')}</div></div></div>
        ${d.state==='unavailable'?'<div class="offline">Сущность недоступна — проверьте интеграцию Home Assistant.</div>':''}
      </div></ha-card>`;

    const seek = this.shadowRoot.querySelector('.seek');
    seek.addEventListener('input', e => { this._dragSeek = true; this._seekValue = Number(e.target.value); const t=this.shadowRoot.querySelector('.times span'); if(t)t.textContent=this._formatTime(this._seekValue); });
    seek.addEventListener('change', async e => { const seconds=Number(e.target.value); this._dragSeek=false; this._seekValue=null; await this._call('media_player','media_seek',{entity_id:this._config.entity,seek_position:seconds}); this._render(); });
    const vol = this.shadowRoot.querySelector('.vol-range');
    vol.addEventListener('input', e => { this._dragVolume=true; this._volumeValue=Number(e.target.value); const label=this.shadowRoot.querySelector('.db'); if(label)label.textContent=`${this._volumeValue}%`; });
    vol.addEventListener('change', async e => { const value=Number(e.target.value)/100; this._dragVolume=false; this._volumeValue=null; await this._call('media_player','volume_set',{entity_id:this._config.entity,volume_level:value}); this._render(); });
    this.shadowRoot.querySelectorAll('[data-action]').forEach(btn=>btn.addEventListener('click',()=>{
      const action=btn.dataset.action;
      if(action==='previous') this._call('media_player','media_previous',{entity_id:this._config.entity});
      if(action==='next') this._call('media_player','media_next',{entity_id:this._config.entity});
      if(action==='playpause') this._call('media_player','media_play_pause',{entity_id:this._config.entity});
    }));
  }

  _call(domain, service, data) {
    if (!this._hass) return Promise.resolve();
    return this._hass.callService(domain, service, data).catch(err=>{
      console.error(`[Eversolo Player Card] ${domain}.${service} failed`, err);
    });
  }

  static getConfigElement() { return document.createElement('eversolo-player-card-editor'); }
  static getStubConfig() { return { entity: 'media_player.eversolo_player', name: 'DMP-A6', refresh_interval: 100 }; }
}

if (!customElements.get('eversolo-player-card')) customElements.define('eversolo-player-card', EversoloPlayerCard);
window.customCards = window.customCards || [];
window.customCards.push({type:'eversolo-player-card',name:'Eversolo Player Card',description:'Тёмная панель управления Eversolo DMP-A6'});