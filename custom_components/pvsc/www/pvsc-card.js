// PVSC Card - Begleit-Card zur "PV Überschussladen (Test)" Integration.
// Angelehnt an wallbox-stecker-card.js, aber verdrahtet auf die neuen
// pvsc_* Entities (unabhängige Home-Assistant-Integration statt Node-RED/MQTT).
// Override-Befehle werden über normale HA-Services gesendet
// (select.select_option / number.set_value / switch.turn_on|off) statt MQTT.
class PvscCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._phaseSwitching = false;
    this._phaseSwitchTimeout = null;
  }

  setConfig(config) {
    // `prefix` = Objekt-ID-Präfix des Config-Eintrags (Feld "id_prefix" im
    // Setup/Reconfigure, Standard "pvsc"). Bei mehreren Wallboxen pro Karte
    // das jeweilige Präfix setzen, z.B.:
    //   type: custom:pvsc-card
    //   prefix: pvsc_garage
    // Einzelne *_entity-Optionen übersteuern das Präfix weiterhin.
    const p = (config && config.prefix) || 'pvsc';
    this._config = Object.assign({
      title: 'EM2GO Home Wallbox',
      plug_entity:            `binary_sensor.${p}_plug_connected`,
      status_code_entity:     `sensor.${p}_em2go_state`,
      leistung_entity:        `sensor.${p}_em2go_power`,
      kwh_entity:             `sensor.${p}_em2go_session_kwh`,
      target_charging_entity: `binary_sensor.${p}_target_charging`,
      target_ampere_entity:   `sensor.${p}_target_ampere`,
      status_text_entity:     `sensor.${p}_status_text`,
      control_enabled_entity: `switch.${p}_control_enabled`,
      override_mode_entity:   `select.${p}_override_mode`,
      override_ampere_entity: `number.${p}_override_ampere`,
      override_phases_entity: `select.${p}_override_phases`,
      correction_factor_entity: `number.${p}_correction_factor`,
      correction_current_entity: `sensor.${p}_correction_faktor`,
      correction_auto_entity:   `switch.${p}_correction_auto`,
      car_soc_entity:           `sensor.${p}_car_soc`,
      car_end_entity:           `sensor.${p}_car_end`,
    }, config);
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _callService(domain, service, data) {
    if (!this._hass) return;
    this._hass.callService(domain, service, data);
  }

  _updateOverrideUI(ov) {
    const root = this.shadowRoot;
    if (!root.querySelector('.mode-btn')) return;

    root.querySelectorAll('.mode-btn').forEach(btn => {
      btn.disabled = this._phaseSwitching;
      btn.classList.remove('active-pv', 'active-manual', 'active-stop', 'switching');
      const isActive = btn.dataset.mode === ov.mode;
      if (isActive && this._phaseSwitching) {
        btn.classList.add('switching');
      } else if (isActive) {
        btn.classList.add(`active-${ov.mode}`);
      }
    });

    root.querySelector('.manual-settings').classList.toggle('visible', ov.mode === 'manual');
    root.querySelector('.amp-val').textContent = `${ov.ampere}A`;

    root.querySelectorAll('.amp-btn').forEach(btn => { btn.disabled = this._phaseSwitching; });

    root.querySelectorAll('.ph-btn').forEach(btn => {
      const isTarget = parseInt(btn.dataset.phases) === ov.phases;
      btn.disabled = this._phaseSwitching;
      btn.classList.toggle('active',    isTarget && !this._phaseSwitching);
      btn.classList.toggle('switching', isTarget &&  this._phaseSwitching);
    });
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card {
          padding: 8px 14px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: 6px;
          height: 100%;
          box-sizing: border-box;
          border-top: 3px solid var(--shadow-border-color, var(--warning-color, #FF9800));
        }
        .main-row { display: flex; flex-direction: row; align-items: center; gap: 14px; }
        .svg-wrap { width: 50px; height: 50px; flex: 0 0 auto; display: flex; align-items: center; justify-content: center; }
        svg { width: 100%; height: 100%; }
        .right-col { display: flex; flex-direction: column; justify-content: center; gap: 4px; flex: 0 0 auto; }
        .text { display: flex; flex-direction: column; flex: 1; min-width: 0; gap: 1px; }
        .title-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
        .title { font-size: 10px; font-weight: 500; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.1; }
        .shadow-badge {
          font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 8px;
          background: var(--warning-color, #FF9800); color: white; white-space: nowrap; cursor: pointer;
        }
        .shadow-badge.live { background: var(--success-color); }
        .status { font-size: 14px; font-weight: 600; color: var(--status-color, var(--secondary-text-color)); transition: color 0.5s; line-height: 1.2; margin-bottom: 2px; }
        .details { font-size: 12px; color: var(--secondary-text-color); line-height: 1.2; }
        .target-row { font-size: 11px; color: var(--secondary-text-color); }

        .override-row { display: flex; flex-direction: row; align-items: center; gap: 4px; flex-wrap: nowrap; justify-content: space-between; }
        .mode-btn {
          padding: 3px 10px; border: 1px solid var(--divider-color, rgba(0,0,0,0.12)); border-radius: 4px;
          background: transparent; color: var(--secondary-text-color); font-size: 12px; font-weight: 500;
          cursor: pointer; transition: background 0.2s, color 0.2s, border-color 0.2s; line-height: 1.6; white-space: nowrap;
        }
        .mode-btn.active-pv { background: var(--success-color); color: white; border-color: var(--success-color); }
        .mode-btn.active-manual { background: var(--info-color, #2196F3); color: white; border-color: var(--info-color, #2196F3); }
        .mode-btn.active-stop { background: var(--error-color); color: white; border-color: var(--error-color); }
        .mode-btn.switching { background: var(--warning-color, #FF9800); color: white; border-color: var(--warning-color, #FF9800); animation: pulse 1s infinite; }
        .mode-btn:disabled { opacity: 0.4; cursor: default; }
        .manual-settings { display: none; flex-direction: row; align-items: center; gap: 5px; }
        .manual-settings.visible { display: flex; }
        .amp-btn { padding: 2px 8px; border: 1px solid var(--divider-color, rgba(0,0,0,0.12)); border-radius: 4px; background: transparent; color: var(--secondary-text-color); font-size: 13px; font-weight: 600; cursor: pointer; line-height: 1.5; }
        .amp-btn:disabled { opacity: 0.4; cursor: default; }
        .amp-val { font-size: 11px; font-weight: 600; color: var(--primary-text-color); min-width: 26px; text-align: center; }
        .ph-btn { padding: 3px 7px; border: 1px solid var(--divider-color, rgba(0,0,0,0.12)); border-radius: 4px; background: transparent; color: var(--secondary-text-color); font-size: 11px; cursor: pointer; line-height: 1.5; }
        .ph-btn.active { background: var(--info-color, #2196F3); color: white; border-color: var(--info-color, #2196F3); }
        .ph-btn:disabled { opacity: 0.4; cursor: default; }
        .ph-btn.switching { background: var(--warning-color, #FF9800); color: white; border-color: var(--warning-color, #FF9800); animation: pulse 1s infinite; }

        .st0 { fill: none; }
        .st1 { fill: var(--connector-color, var(--disabled-color)); transition: fill 0.5s; }
        .st2 { stroke: var(--contact-color, var(--secondary-text-color)); fill: none; stroke-width: 3.9451; stroke-miterlimit: 10; transition: stroke 0.5s; }
        .st3 { stroke: var(--contact-color, var(--secondary-text-color)); fill: none; stroke-width: 5.2601; stroke-miterlimit: 10; transition: stroke 0.5s; }

        .corr-row { display: flex; flex-direction: row; align-items: center; gap: 6px; width: 100%; padding: 0 2px; box-sizing: border-box; }
        .corr-label { font-size: 10px; color: var(--secondary-text-color); white-space: nowrap; width: 26px; flex: 0 0 auto; }
        .corr-slider { flex: 1; height: 3px; cursor: pointer; accent-color: var(--primary-color); margin: 0; }
        .corr-slider:disabled { opacity: 0.35; cursor: default; }
        .corr-val { font-size: 10px; font-weight: 600; color: var(--primary-text-color); width: 32px; text-align: right; flex: 0 0 auto; }
        .corr-auto-btn { padding: 1px 6px; border: 1px solid var(--divider-color, rgba(0,0,0,0.12)); border-radius: 3px; background: transparent; color: var(--secondary-text-color); font-size: 10px; font-weight: 600; cursor: pointer; line-height: 1.5; white-space: nowrap; flex: 0 0 auto; }
        .corr-auto-btn.active { background: var(--success-color); color: white; border-color: var(--success-color); }

        @keyframes pulse { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } }
        .pulsing { animation: pulse 1.8s infinite cubic-bezier(0.4, 0, 0.6, 1); }
      </style>

      <ha-card>
        <div class="main-row">
          <div class="svg-wrap">
            <svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 93.6 81.3">
              <path class="st0" d="M69.2,4.5c2.1,0,4.3,0.2,5,0.2c6.9,0,15.1,18.8,15.1,29.8C89.2,58,70.2,77,46.8,77C23.3,77,4.3,60.7,4.3,34.5 c0-11.6,7.4-28.1,15.9-29.8c0.7-0.1,4.3-0.1,6.1-0.2C26.4,4.5,69.1,4.3,69.2,4.5z"/>
              <path class="st1" d="M74.1,0c11.7,0.3,19.5,23.1,19.5,34.5c0,25.8-21,46.8-46.8,46.8C19.7,81.3,0,61.6,0,34.5 c0-6.4,2-14.1,5.2-20.6C9.1,6.3,14.1,1.5,19.4,0.5l0,0c0.8-0.2,2.2-0.4,4.2-0.5C23.6,0,74.2,0,74.1,0z M25.2,8.8 c-2,0.1-3.5,0-4,0.1l0,0C15.4,10.1,8.7,24,8.7,34.5c0,22.5,15.7,38.1,38.1,38.1c21,0,38.1-17.1,38.1-38.1 c0-10.7-7.7-24.9-10.8-25.5c-2.2-0.3-4.3-0.2-5.2-0.2H25.2z"/>
              <circle class="st2" cx="35.6" cy="20.9" r="4.3"/>
              <circle class="st2" cx="57.7" cy="20.9" r="4.3"/>
              <circle class="st3" cx="35.6" cy="55.1" r="6.1"/>
              <circle class="st3" cx="57.7" cy="55.1" r="6.1"/>
              <circle class="st3" cx="24.7" cy="36.3" r="6.1"/>
              <circle class="st3" cx="46.8" cy="36.3" r="6.1"/>
              <circle class="st3" cx="68.9" cy="36.3" r="6.1"/>
            </svg>
          </div>
          <div class="text">
            <div class="title-row">
              <span class="title"></span>
              <span class="shadow-badge" id="shadow-badge">STEUERUNG AUS</span>
            </div>
            <div class="status"></div>
            <div class="details"></div>
            <div class="target-row"></div>
          </div>
          <div class="right-col">
            <div class="override-row">
              <button class="mode-btn" data-mode="pv">PV</button>
              <button class="mode-btn" data-mode="manual">Manuell</button>
              <button class="mode-btn" data-mode="stop">Stop</button>
            </div>
            <div class="manual-settings">
              <button class="amp-btn" data-delta="-1">−</button>
              <span class="amp-val">6A</span>
              <button class="amp-btn" data-delta="1">+</button>
              <button class="ph-btn" data-phases="1">1Ph</button>
              <button class="ph-btn" data-phases="3">3Ph</button>
            </div>
          </div>
        </div>
        <div class="corr-row">
          <span class="corr-label">Korr.</span>
          <input class="corr-slider" id="corr-slider" type="range" min="0" max="125" step="5" value="75">
          <span class="corr-val" id="corr-val">75%</span>
          <button class="corr-auto-btn active" id="corr-auto-btn">Auto</button>
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelector('.title').textContent = this._config.title;

    // Schatten-/Live-Badge -> togglet switch.pvsc_control_enabled
    this.shadowRoot.getElementById('shadow-badge').addEventListener('click', () => {
      if (!this._hass) return;
      const isLive = this._hass.states[this._config.control_enabled_entity]?.state === 'on';
      const service = isLive ? 'turn_off' : 'turn_on';
      // eslint-disable-next-line no-alert
      if (!isLive && !confirm('Steuerung wirklich aktivieren? Die Integration schreibt dann auf die Wallbox (Start/Stopp/Ampere/Phasen).')) {
        return;
      }
      this._callService('switch', service, { entity_id: this._config.control_enabled_entity });
    });

    // Override-Steuerung -> HA-Services statt MQTT
    this.shadowRoot.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!this._hass) return;
        const prevMode = this._hass.states[this._config.override_mode_entity]?.state ?? 'pv';
        const newMode = btn.dataset.mode;
        const statusCode = parseInt(this._hass.states[this._config.status_code_entity]?.state ?? '0');

        this._callService('select', 'select_option', {
          entity_id: this._config.override_mode_entity, option: newMode,
        });

        if ((newMode === 'pv' && prevMode === 'manual') || (newMode === 'manual' && prevMode === 'pv')) {
          if (statusCode === 4) {
            this._phaseSwitching = true;
            clearTimeout(this._phaseSwitchTimeout);
            this._phaseSwitchTimeout = setTimeout(() => {
              this._phaseSwitching = false;
              this._update();
            }, 8000);
          }
        }
      });
    });

    this.shadowRoot.querySelectorAll('.amp-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!this._hass) return;
        const cur = parseInt(this._hass.states[this._config.override_ampere_entity]?.state ?? '6');
        const delta = parseInt(btn.dataset.delta);
        const next = Math.min(16, Math.max(6, cur + delta));
        this._callService('number', 'set_value', {
          entity_id: this._config.override_ampere_entity, value: next,
        });
      });
    });

    this.shadowRoot.querySelectorAll('.ph-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!this._hass) return;
        const newPhases = btn.dataset.phases;
        const curPhases = this._hass.states[this._config.override_phases_entity]?.state ?? '1';
        if (newPhases === curPhases) return;

        const statusCode = parseInt(this._hass.states[this._config.status_code_entity]?.state ?? '0');
        if (statusCode === 4) {
          this._phaseSwitching = true;
          clearTimeout(this._phaseSwitchTimeout);
          this._phaseSwitchTimeout = setTimeout(() => {
            this._phaseSwitching = false;
            this._update();
          }, 8000);
        }
        this._callService('select', 'select_option', {
          entity_id: this._config.override_phases_entity, option: newPhases,
        });
      });
    });

    // Korrekturfaktor
    {
      const slider  = this.shadowRoot.getElementById('corr-slider');
      const valEl   = this.shadowRoot.getElementById('corr-val');
      const autoBtn = this.shadowRoot.getElementById('corr-auto-btn');

      slider.addEventListener('pointerdown', () => { this._corrDragging = true; });
      slider.addEventListener('pointerup',   () => { this._corrDragging = false; });
      slider.addEventListener('input', () => { valEl.textContent = `${slider.value}%`; });
      slider.addEventListener('change', () => {
        this._callService('number', 'set_value', {
          entity_id: this._config.correction_factor_entity, value: parseInt(slider.value),
        });
      });

      autoBtn.addEventListener('click', () => {
        const isAuto = autoBtn.classList.contains('active');
        this._callService('switch', isAuto ? 'turn_off' : 'turn_on', {
          entity_id: this._config.correction_auto_entity,
        });
      });
    }

    this._update();
  }

  _updateCorrUI() {
    const root = this.shadowRoot;
    if (!this._hass || !this._config) return;

    const isAuto    = this._hass.states[this._config.correction_auto_entity]?.state === 'on';
    const manualVal = Math.round(parseFloat(this._hass.states[this._config.correction_factor_entity]?.state ?? '75'));
    // Tatsächlich angewendeter Faktor aus der Regel-Logik (sensor.pvsc_correction_faktor,
    // z.B. 1.05 -> 105%). Im Auto-Modus weicht er vom manuellen Regler ab.
    const appliedRaw = parseFloat(this._hass.states[this._config.correction_current_entity]?.state ?? 'NaN');
    const appliedVal = isNaN(appliedRaw) ? manualVal : Math.round(appliedRaw * 100);

    const corrSlider  = root.getElementById('corr-slider');
    const corrValEl   = root.getElementById('corr-val');
    const corrAutoBtn = root.getElementById('corr-auto-btn');
    if (corrSlider) {
      corrSlider.disabled = isAuto;
      if (!this._corrDragging) corrSlider.value = isAuto ? appliedVal : manualVal;
    }
    if (corrValEl) corrValEl.textContent = this._corrDragging ? `${corrSlider.value}%` : `${appliedVal}%`;
    if (corrAutoBtn) corrAutoBtn.classList.toggle('active', isAuto);
  }

  _update() {
    if (!this._hass || !this._config) return;
    const card     = this.shadowRoot.querySelector('ha-card');
    const statusEl = this.shadowRoot.querySelector('.status');
    const detailEl = this.shadowRoot.querySelector('.details');
    const targetEl = this.shadowRoot.querySelector('.target-row');
    const circles  = this.shadowRoot.querySelectorAll('circle');
    const badge    = this.shadowRoot.getElementById('shadow-badge');

    const plugConnected = this._hass.states[this._config.plug_entity]?.state === 'on';
    const statusCode    = parseInt(this._hass.states[this._config.status_code_entity]?.state ?? '0');
    const leistung      = parseFloat(this._hass.states[this._config.leistung_entity]?.state ?? '0');
    const kwh           = parseFloat(this._hass.states[this._config.kwh_entity]?.state ?? '0');
    const controlLive   = this._hass.states[this._config.control_enabled_entity]?.state === 'on';
    const targetCharging = this._hass.states[this._config.target_charging_entity]?.state === 'on';
    const targetAmpere   = this._hass.states[this._config.target_ampere_entity]?.state;

    badge.textContent = controlLive ? 'LIVE' : 'STEUERUNG AUS';
    badge.classList.toggle('live', controlLive);
    card.style.setProperty('--shadow-border-color', controlLive ? 'var(--success-color)' : 'var(--warning-color, #FF9800)');

    const STATUS_MAP = {
      0: { label: 'Unbekannt',      color: 'var(--error-color)',          pulse: false },
      1: { label: 'Bereit',         color: 'var(--disabled-color)',       pulse: false },
      2: { label: 'Verbunden',      color: 'var(--warning-color)',        pulse: false },
      3: { label: 'Starte…',        color: 'var(--success-color)',        pulse: false },
      4: { label: 'Lädt',           color: 'var(--success-color)',        pulse: true  },
      5: { label: 'Fehler',         color: 'var(--error-color)',          pulse: false },
      6: { label: 'Laden beendet',  color: 'var(--info-color)',           pulse: false },
    };
    const s = STATUS_MAP[statusCode] ?? STATUS_MAP[0];
    const ringColor = plugConnected ? s.color : 'var(--disabled-color)';

    card.style.setProperty('--connector-color', ringColor);
    card.style.setProperty('--contact-color', plugConnected ? s.color : 'var(--secondary-text-color)');
    card.style.setProperty('--status-color', plugConnected ? s.color : 'var(--secondary-text-color)');

    circles.forEach(c => {
      if (s.pulse && plugConnected) c.classList.add('pulsing');
      else c.classList.remove('pulsing');
    });

    const carSoc    = parseFloat(this._hass.states[this._config.car_soc_entity]?.state ?? '-1');
    const carEndRaw = this._hass.states[this._config.car_end_entity]?.state;
    let carEndStr = '';
    if (carEndRaw && carEndRaw !== 'unknown' && carEndRaw !== 'unavailable') {
      const d = new Date(carEndRaw);
      if (!isNaN(d)) carEndStr = `→${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
    }
    const carStr = (statusCode === 4 && carSoc >= 0) ? ` ${Math.round(carSoc)}%${carEndStr}` : '';
    statusEl.textContent = !plugConnected ? 'Nicht verbunden' : `${s.label}${carStr}`;

    if (statusCode === 4 && leistung > 0) {
      const leistungStr = leistung >= 1000 ? `${(leistung/1000).toFixed(2)} kW` : `${Math.round(leistung)} W`;
      detailEl.innerHTML = `${leistungStr}<br>${kwh.toFixed(2)} kWh`;
    } else if (statusCode === 6) {
      detailEl.textContent = `${kwh.toFixed(2)} kWh geladen`;
    } else {
      detailEl.textContent = '';
    }

    // Eigene Ziel-Logik anzeigen (auch im Schatten-Modus sichtbar)
    if (targetCharging !== (statusCode === 3 || statusCode === 4)) {
      targetEl.textContent = `Eigene Logik will: ${targetCharging ? 'AN' : 'AUS'}${targetCharging && targetAmpere ? ' @ ' + targetAmpere + 'A' : ''}`;
    } else if (targetCharging && targetAmpere) {
      targetEl.textContent = `Ziel-Ampere: ${targetAmpere}A`;
    } else {
      targetEl.textContent = '';
    }

    const ov = {
      mode: this._hass.states[this._config.override_mode_entity]?.state ?? 'pv',
      ampere: parseInt(this._hass.states[this._config.override_ampere_entity]?.state ?? '6'),
      phases: parseInt(this._hass.states[this._config.override_phases_entity]?.state ?? '1'),
    };
    this._updateOverrideUI(ov);
    this._updateCorrUI();
  }

  getCardSize() { return 3; }

  getGridOptions() { return { rows: 3, min_rows: 3, columns: 12 }; }

  static getStubConfig() {
    return { title: 'EM2GO Home Wallbox', prefix: 'pvsc' };
  }

  static getConfigElement() {
    return document.createElement('pvsc-card-editor');
  }
}

// Grafischer Karten-Editor: Titel + Auswahl der Wallbox über deren
// Entity-ID-Präfix. Die vorhandenen Wallboxen werden automatisch an den
// sensor.<prefix>_em2go_state Entities erkannt (eine pro Config-Eintrag).
// Bewusst native Formular-Elemente statt ha-* Komponenten, damit der
// Editor ohne interne Frontend-Abhängigkeiten funktioniert.
class PvscCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._built = false;
  }

  setConfig(config) {
    this._config = Object.assign({}, config);
    this._build();
    this._updateValues();
  }

  set hass(hass) {
    this._hass = hass;
    this._build();
    this._updateOptions();
  }

  _detectPrefixes() {
    const found = new Set();
    if (this._hass) {
      for (const id of Object.keys(this._hass.states)) {
        const m = id.match(/^sensor\.(.+)_em2go_state$/);
        if (m) found.add(m[1]);
      }
    }
    // Aktuell konfiguriertes Präfix immer anbieten, auch wenn (noch)
    // keine passende Entity existiert (z.B. Integration gerade neu lädt).
    found.add((this._config && this._config.prefix) || 'pvsc');
    return [...found].sort();
  }

  _build() {
    if (this._built) return;
    this._built = true;
    this.shadowRoot.innerHTML = `
      <style>
        .row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
        label { font-size: 12px; color: var(--secondary-text-color); }
        input, select {
          padding: 8px; font-size: 14px; color: var(--primary-text-color);
          background: var(--card-background-color, #fff);
          border: 1px solid var(--divider-color, rgba(0,0,0,0.2)); border-radius: 4px;
        }
        .hint { font-size: 11px; color: var(--secondary-text-color); }
      </style>
      <div class="row">
        <label for="title">Titel</label>
        <input id="title" type="text">
      </div>
      <div class="row">
        <label for="prefix">Wallbox (Entity-ID-Präfix des Eintrags)</label>
        <select id="prefix"></select>
        <span class="hint">Erkannt über die vorhandenen sensor.&lt;präfix&gt;_em2go_state Entities - eine pro eingerichteter Wallbox.</span>
      </div>
    `;
    this.shadowRoot.getElementById('title').addEventListener('input', (ev) => {
      this._valueChanged('title', ev.target.value);
    });
    this.shadowRoot.getElementById('prefix').addEventListener('change', (ev) => {
      this._valueChanged('prefix', ev.target.value);
    });
  }

  _updateOptions() {
    if (!this._built) return;
    const select = this.shadowRoot.getElementById('prefix');
    const current = (this._config && this._config.prefix) || 'pvsc';
    const prefixes = this._detectPrefixes();
    select.innerHTML = '';
    for (const p of prefixes) {
      const opt = document.createElement('option');
      opt.value = p;
      opt.textContent = p;
      select.appendChild(opt);
    }
    select.value = current;
  }

  _updateValues() {
    if (!this._built || !this._config) return;
    const titleEl = this.shadowRoot.getElementById('title');
    if (document.activeElement !== titleEl) {
      titleEl.value = this._config.title || '';
    }
    this._updateOptions();
  }

  _valueChanged(key, value) {
    if (!this._config) return;
    const config = Object.assign({}, this._config);
    if (value === '' && key === 'title') delete config.title;
    else config[key] = value;
    this._config = config;
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config }, bubbles: true, composed: true,
    }));
  }
}

if (!customElements.get('pvsc-card')) {
  customElements.define('pvsc-card', PvscCard);
}
if (!customElements.get('pvsc-card-editor')) {
  customElements.define('pvsc-card-editor', PvscCardEditor);
}
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'pvsc-card',
  name: 'PV Überschussladen (Test)',
  description: 'Begleit-Card zur pvsc Integration (Schatten-Modus Testkarte)',
  preview: false,
});
