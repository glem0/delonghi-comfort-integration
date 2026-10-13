/* ==========================================================================
 * De'Longhi Comfort - weekly schedule Lovelace card
 *
 * A single-file, dependency-free Lovelace card that views and edits the
 * weekly schedule of a De'Longhi dehumidifier.
 *
 *   data in  : the schedule sensor attributes `days` (7 x 24 labels
 *              "off"/"A"/"B"/"C", Monday first) and `modes`
 *              ({"A": {humidity, fan}, ...})
 *   data out : service `delonghi_comfort.set_schedule` with
 *              {week: [7 strings of 24 chars 0/A/B/C], modes: {...},
 *               activate?: bool}
 *
 * Device slot codes (2-bit values in the device payload):
 *   0 = off, 1 = preset C, 2 = preset B, 3 = preset A
 * The card keeps those codes internally so that no conversion is needed
 * when talking to the service.
 * ========================================================================== */
(() => {
  'use strict';

  /* --------------------------------------------------------------------- *
   * Constants
   * --------------------------------------------------------------------- */

  const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const PRESET_KEYS = ['A', 'B', 'C'];
  const HOURS = 24;
  const DAYS = 7;

  /** Device slot code -> single character used by the service. */
  const SLOT_CHARS = { 0: '0', 1: 'C', 2: 'B', 3: 'A' };
  /** Device slot code -> letter shown inside the cell ('' = off). */
  const SLOT_LETTERS = { 0: '', 1: 'C', 2: 'B', 3: 'A' };
  const SLOT_NAMES = { 0: 'Off', 1: 'Preset C', 2: 'Preset B', 3: 'Preset A' };
  /** Sensor attribute label -> device slot code. */
  const LABEL_SLOTS = { off: 0, a: 3, b: 2, c: 1 };

  const FAN_OPTIONS = [
    { value: 0, label: 'Off' },
    { value: 1, label: 'Low' },
    { value: 2, label: 'Medium' },
    { value: 3, label: 'High' },
  ];

  /** Brush toolbar, in display order (slot code + label + CSS class). */
  const BRUSHES = [
    { slot: 0, label: 'Off', cls: 'brush-off', title: 'Paint off' },
    { slot: 3, label: 'A', cls: 'brush-A', title: 'Paint preset A' },
    { slot: 2, label: 'B', cls: 'brush-B', title: 'Paint preset B' },
    { slot: 1, label: 'C', cls: 'brush-C', title: 'Paint preset C' },
  ];

  const HUMIDITY_MIN = 30;
  const HUMIDITY_MAX = 80;
  const DEFAULT_HUMIDITY = 50;
  const DEFAULT_FAN = 1;

  /* --------------------------------------------------------------------- *
   * Styles
   * --------------------------------------------------------------------- */

  const STYLES = `
    :host { display: block; }
    ha-card.delonghi-schedule {
      display: block;
      padding: 12px 14px 10px;
      box-sizing: border-box;
      --cell-w: 26px;
      --cell-h: 22px;
      --row-lab: 46px;
    }
    .title {
      font-size: 16px; font-weight: 600; margin-bottom: 8px;
      color: var(--primary-text-color, #212121);
    }
    .msg {
      font-size: 13px; padding: 14px 2px;
      color: var(--secondary-text-color, #727272);
    }

    /* Toolbar ---------------------------------------------------------- */
    .toolbar {
      display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .tool-label {
      font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
      color: var(--secondary-text-color, #727272); margin-right: 2px;
    }
    .brush {
      width: 30px; height: 26px; padding: 0; border-radius: 6px;
      font-family: inherit; font-size: 12px; font-weight: 600; cursor: pointer;
      color: var(--primary-text-color, #212121);
      background: var(--card-background-color, #fff);
      border: 1px solid var(--divider-color, rgba(0,0,0,.16));
    }
    .brush-off { box-shadow: inset 0 -3px 0 rgba(128,128,128,.45); }
    .brush-A { box-shadow: inset 0 -3px 0 #f9a825; }
    .brush-B { box-shadow: inset 0 -3px 0 #29b6f6; }
    .brush-C { box-shadow: inset 0 -3px 0 #66bb6a; }
    .brush.active {
      outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 1px;
    }
    .spacer { flex: 1 1 auto; }
    .toggle {
      font-family: inherit; font-size: 12px; padding: 5px 12px;
      border-radius: 14px; cursor: pointer;
      color: var(--primary-text-color, #212121);
      background: rgba(128,128,128,.14);
      border: 1px solid var(--divider-color, rgba(0,0,0,.16));
    }
    .toggle.on {
      background: var(--primary-color, #03a9f4); color: #fff;
      border-color: transparent;
    }
    .toggle:disabled { opacity: .5; cursor: default; }
    .check {
      display: flex; align-items: center; gap: 6px; font-size: 12px;
      color: var(--secondary-text-color, #727272); cursor: pointer;
    }

    /* Grid ------------------------------------------------------------- */
    .grid-scroll { overflow-x: auto; overflow-y: hidden; padding-bottom: 4px; }
    .grid {
      display: grid;
      grid-template-columns: var(--row-lab) repeat(24, minmax(var(--cell-w), 1fr));
      grid-auto-rows: var(--cell-h);
      gap: 1px;
      width: max-content; min-width: 100%;
      user-select: none; -webkit-user-select: none;
    }
    .rul {
      display: flex; align-items: center; justify-content: center;
      font-size: 10px; color: var(--secondary-text-color, #727272);
    }
    .rul.corner, .rul.day {
      position: sticky; left: 0; z-index: 2;
      background: var(--card-background-color, #fff);
    }
    .rul.day {
      justify-content: flex-start; padding-left: 2px;
      font-size: 11px; font-weight: 500;
      color: var(--primary-text-color, #212121);
    }
    .rul.day.weekend { color: var(--secondary-text-color, #727272); }
    .cell {
      display: flex; align-items: center; justify-content: center;
      border-radius: 3px; cursor: pointer; touch-action: manipulation;
      font-size: 10px; font-weight: 700; color: rgba(0,0,0,.62);
      background: rgba(128,128,128,.16);
    }
    .cell.s1 { background: #66bb6a; }
    .cell.s2 { background: #29b6f6; }
    .cell.s3 { background: #f9a825; }
    .cell:hover { outline: 1px solid var(--primary-color, #03a9f4); }
    .delonghi-schedule.compact { --cell-w: 15px; }
    .delonghi-schedule.compact .cell { font-size: 0; }

    /* Preset editor ---------------------------------------------------- */
    .presets {
      display: flex; flex-wrap: wrap; gap: 8px 14px; margin: 10px 0 12px;
    }
    .preset {
      display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
      padding: 6px 8px; border-radius: 8px; background: rgba(128,128,128,.08);
    }
    .swatch { width: 12px; height: 12px; border-radius: 3px; }
    .swatch-A { background: #f9a825; }
    .swatch-B { background: #29b6f6; }
    .swatch-C { background: #66bb6a; }
    .preset-name {
      font-size: 13px; font-weight: 600; min-width: 64px;
      color: var(--primary-text-color, #212121);
    }
    .field {
      display: flex; align-items: center; gap: 4px; font-size: 12px;
      color: var(--secondary-text-color, #727272);
    }
    .field input, .field select {
      font-family: inherit; font-size: 13px; padding: 2px 4px;
      border-radius: 4px; border: 1px solid var(--divider-color, rgba(0,0,0,.2));
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color, #212121);
    }
    .hum { width: 54px; text-align: right; }

    /* Footer ----------------------------------------------------------- */
    .foot {
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      padding-top: 8px;
      border-top: 1px solid var(--divider-color, rgba(0,0,0,.12));
    }
    .status {
      flex: 1 1 120px; font-size: 12px;
      color: var(--secondary-text-color, #727272);
    }
    .status.dirty { color: var(--warning-color, #ffa600); }
    .status.saved { color: var(--success-color, #43a047); }
    .status.error { color: var(--error-color, #db4437); }
    .actions { display: flex; gap: 8px; }
    .save {
      font-family: inherit; font-size: 13px; font-weight: 500;
      padding: 7px 16px; border: none; border-radius: 6px; cursor: pointer;
      background: var(--primary-color, #03a9f4);
      color: var(--text-primary-color, #fff);
    }
    .save:disabled { opacity: .45; cursor: default; }
    .save.busy { opacity: .7; }
    .discard {
      font-family: inherit; font-size: 13px; padding: 6px 12px;
      border-radius: 6px; cursor: pointer; background: transparent;
      color: var(--primary-color, #03a9f4);
      border: 1px solid var(--divider-color, rgba(0,0,0,.2));
    }
    .discard:disabled { opacity: .45; cursor: default; }
  `;

  /* --------------------------------------------------------------------- *
   * Card
   * --------------------------------------------------------------------- */

  class DelonghiScheduleCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });

      /* configuration / HA */
      this._config = null;
      this._configKey = null;
      this._hass = null;
      this._built = false;

      /* local schedule model (source of truth for the DOM) */
      this._model = null;        // {grid, modes, activate}
      this._modelSig = null;     // signature of the data currently on screen
      this._deviceSig = null;    // signature of the last data read from the device
      this._pendingSig = null;   // signature of the payload we last saved
      this._adoptBlockUntil = 0; // don't adopt stale data right after a save
      this._activateTouched = false;

      /* editing state */
      this._brush = 3;
      this._dirty = false;
      this._saving = false;
      this._notice = null;       // {kind: 'saved'|'error', text}
      this._painting = false;
      this._pendingTap = null;
      this._compact = false;
      this._windowBound = false;
    }

    /* --------------------------------------------------------------- *
     * Home Assistant card API
     * --------------------------------------------------------------- */

    setConfig(config) {
      if (!config || !config.entity) {
        throw new Error(
          "delonghi-schedule-card: 'entity' is required (the De'Longhi schedule sensor)"
        );
      }
      const key = [config.entity, config.switch_entity || '', config.name || ''].join('|');
      this._config = {
        entity: config.entity,
        switch_entity: config.switch_entity || null,
        name: config.name || 'Weekly schedule',
      };
      if (key !== this._configKey) {
        this._configKey = key;
        this._built = false;
        this._model = null;
        this._modelSig = null;
        this._deviceSig = null;
        this._pendingSig = null;
        this._dirty = false;
        this._saving = false;
        this._notice = null;
        this._activateTouched = false;
        if (this.shadowRoot) this.shadowRoot.textContent = '';
      }
      this._ensureBuilt();
      this._refresh();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._config || !hass) return;
      this._ensureBuilt();
      this._refresh();
    }

    getCardSize() {
      return 9;
    }

    connectedCallback() {
      this._bindWindow();
      if (this._config) this._ensureBuilt();
      this._applyCompact();
    }

    disconnectedCallback() {
      if (this._windowBound) {
        window.removeEventListener('pointerup', this._onWindowPointerUp);
        window.removeEventListener('pointercancel', this._onWindowPointerCancel);
        this._windowBound = false;
      }
      if (this._resizeObserver) {
        this._resizeObserver.disconnect();
        this._resizeObserver = null;
      }
    }

    /* --------------------------------------------------------------- *
     * Build the (static) DOM
     * --------------------------------------------------------------- */

    _ensureBuilt() {
      if (this._built || !this._config) return;

      const root = this.shadowRoot;
      root.textContent = '';

      const style = document.createElement('style');
      style.textContent = STYLES;

      this._card = document.createElement('ha-card');
      this._card.className = 'delonghi-schedule';

      this._titleEl = this._el('div', 'title', this._config.name);
      this._msgEl = this._el('div', 'msg');
      this._msgEl.hidden = true;

      this._editorEl = this._el('div', 'editor');
      this._toolbarEl = this._el('div', 'toolbar');
      this._gridEl = this._el('div', 'grid');
      this._presetsEl = this._el('div', 'presets');
      this._footEl = this._el('div', 'foot');
      const scroll = this._el('div', 'grid-scroll');
      scroll.append(this._gridEl);
      this._editorEl.append(this._toolbarEl, scroll, this._presetsEl, this._footEl);

      this._card.append(this._titleEl, this._msgEl, this._editorEl);
      root.append(style, this._card);

      this._buildToolbar();
      this._buildGrid();
      this._buildPresets();
      this._buildFooter();
      this._observeResize();

      this._built = true;
    }

    _buildToolbar() {
      this._toolbarEl.append(this._el('span', 'tool-label', 'Brush'));

      this._brushButtons = new Map();
      for (const brush of BRUSHES) {
        const btn = this._el('button', 'brush ' + brush.cls, brush.label);
        btn.type = 'button';
        btn.title = brush.title;
        btn.addEventListener('click', () => this._setBrush(brush.slot));
        this._toolbarEl.append(btn);
        this._brushButtons.set(brush.slot, btn);
      }
      this._setBrush(this._brush);

      this._activeSlotEl = this._el('div', 'active-slot');
      this._toolbarEl.append(this._el('div', 'spacer'), this._activeSlotEl);
      this._buildActiveToggle();
    }

    /** Activation widget: switch entity if configured, checkbox otherwise. */
    _buildActiveToggle() {
      this._activeSlotEl.textContent = '';
      this._switchEl = null;
      this._activateCb = null;

      if (this._config.switch_entity) {
        const btn = this._el('button', 'toggle');
        btn.type = 'button';
        btn.addEventListener('click', () => this._onToggleActive());
        this._activeSlotEl.append(btn);
        this._switchEl = btn;
        return;
      }

      const label = this._el('label', 'check');
      const cb = this._el('input');
      cb.type = 'checkbox';
      cb.addEventListener('change', () => {
        if (!this._model) return;
        this._model.activate = cb.checked;
        this._activateTouched = true;
        this._markDirty();
      });
      label.append(cb, this._el('span', null, 'Activate schedule when saving'));
      this._activeSlotEl.append(label);
      this._activateCb = cb;
    }

    _buildGrid() {
      const grid = this._gridEl;
      grid.textContent = '';
      this._cellEls = new Array(DAYS * HOURS);

      grid.append(this._el('div', 'rul corner'));
      for (let h = 0; h < HOURS; h++) {
        const major = h % 3 === 0;
        grid.append(this._el('div', 'rul hour' + (major ? ' major' : ''),
          major ? String(h).padStart(2, '0') : ''));
      }

      for (let d = 0; d < DAYS; d++) {
        const lab = this._el('div', 'rul day', DAY_NAMES[d]);
        if (d >= 5) lab.classList.add('weekend');
        grid.append(lab);
        for (let h = 0; h < HOURS; h++) {
          const cell = this._el('div', 'cell');
          cell.addEventListener('pointerdown', (ev) => this._onCellPointerDown(ev, d, h));
          cell.addEventListener('pointerenter', () => this._onCellPointerEnter(d, h));
          this._cellEls[d * HOURS + h] = cell;
          grid.append(cell);
        }
      }
    }

    _buildPresets() {
      this._presetInputs = {};
      for (const key of PRESET_KEYS) {
        const row = this._el('div', 'preset');
        row.append(this._el('span', 'swatch swatch-' + key));
        row.append(this._el('span', 'preset-name', 'Preset ' + key));

        const humField = this._el('label', 'field');
        humField.append(this._el('span', null, 'Humidity'));
        const hum = this._el('input', 'hum');
        hum.type = 'number';
        hum.min = String(HUMIDITY_MIN);
        hum.max = String(HUMIDITY_MAX);
        hum.step = '5';
        hum.setAttribute('aria-label', `Preset ${key} humidity in percent`);
        hum.addEventListener('input', () => this._onHumidityInput(key, hum));
        hum.addEventListener('change', () => this._onHumidityCommit(key, hum));
        humField.append(hum, this._el('span', null, '%'));

        const fanField = this._el('label', 'field');
        fanField.append(this._el('span', null, 'Fan'));
        const fan = this._el('select', 'fan');
        fan.setAttribute('aria-label', `Preset ${key} fan speed`);
        for (const option of FAN_OPTIONS) {
          const opt = this._el('option', null, option.label);
          opt.value = String(option.value);
          fan.append(opt);
        }
        // Placeholder for raw fan values the device reports but we can't name.
        const extra = this._el('option');
        extra.hidden = true;
        fan.append(extra);
        fan.addEventListener('change', () => this._onFanChange(key, fan));
        fanField.append(fan);

        row.append(humField, fanField);
        this._presetsEl.append(row);
        this._presetInputs[key] = { hum, fan, extra };
      }
    }

    _buildFooter() {
      this._statusEl = this._el('div', 'status');

      this._discardBtn = this._el('button', 'discard', 'Discard');
      this._discardBtn.type = 'button';
      this._discardBtn.addEventListener('click', () => this._onDiscard());

      this._saveBtn = this._el('button', 'save', 'Save');
      this._saveBtn.type = 'button';
      this._saveBtn.addEventListener('click', () => this._onSave());

      const actions = this._el('div', 'actions');
      actions.append(this._discardBtn, this._saveBtn);
      this._footEl.append(this._statusEl, actions);
    }

    _observeResize() {
      this._applyCompact();
      if (typeof ResizeObserver === 'undefined') return;
      this._resizeObserver = new ResizeObserver(() => this._applyCompact());
      this._resizeObserver.observe(this._card);
    }

    /** Narrow cards hide the in-cell letters and shrink the columns. */
    _applyCompact() {
      if (!this._card) return;
      const width = this._card.clientWidth;
      const compact = width > 0 && width < 440;
      if (compact === this._compact) return;
      this._compact = compact;
      this._card.classList.toggle('compact', compact);
    }

    /* --------------------------------------------------------------- *
     * Device data <-> local model
     * --------------------------------------------------------------- */

    _refresh() {
      if (!this._config || !this._hass) return;
      this._titleEl.textContent = this._config.name;

      const device = this._readDevice();
      if (!device) {
        this._showMessage(`Entity not found: ${this._config.entity}`);
        return;
      }
      if (device.error) {
        this._showMessage(device.error);
        return;
      }

      this._showEditor();
      const adopted = this._maybeAdopt(device);
      if (adopted) this._applyModelToDom();
      this._updateActiveToggle();
      this._updateFooter();
    }

    /** Read the schedule sensor -> {model, sig} | {error} | null (no state). */
    _readDevice() {
      const state = this._hass.states[this._config.entity];
      if (!state) return null;

      const attrs = state.attributes || {};
      if (!attrs.days || !attrs.modes) {
        return { error: 'No schedule reported by the device yet.' };
      }
      const grid = this._parseDays(attrs.days);
      if (!grid) return { error: 'Schedule attributes are in an unexpected format.' };

      const modes = {};
      for (const key of PRESET_KEYS) {
        const raw = attrs.modes[key] || {};
        modes[key] = {
          humidity: this._intOr(raw.humidity, DEFAULT_HUMIDITY),
          fan: this._intOr(raw.fan, DEFAULT_FAN),
        };
      }
      return { model: { grid, modes, activate: true }, sig: this._signature(grid, modes) };
    }

    /** Attribute days -> 7x24 grid of device slot codes (null if malformed). */
    _parseDays(days) {
      const grid = [];
      for (let d = 0; d < DAYS; d++) {
        const row = days[String(d)] !== undefined ? days[String(d)] : days[d];
        if (!Array.isArray(row) || row.length !== HOURS) return null;
        grid.push(row.map((label) => {
          const slot = LABEL_SLOTS[String(label).toLowerCase()];
          return slot === undefined ? 0 : slot;
        }));
      }
      return grid;
    }

    /**
     * Adopt device data only when it is safe: never while the user has
     * unsaved edits, and never from a stale entity state right after a save.
     */
    _maybeAdopt(device) {
      if (this._dirty) return false;
      if (!this._model) {
        this._adopt(device);
        return true;
      }
      if (device.sig === this._modelSig) {
        this._deviceSig = device.sig;
        return false;
      }
      const staleAfterSave = Date.now() < this._adoptBlockUntil
        && device.sig !== this._pendingSig;
      if (staleAfterSave) return false;
      this._adopt(device);
      return true;
    }

    _adopt(device) {
      const activate = this._activateTouched && this._model
        ? this._model.activate
        : true;
      this._model = {
        grid: device.model.grid.map((row) => row.slice()),
        modes: {
          A: { ...device.model.modes.A },
          B: { ...device.model.modes.B },
          C: { ...device.model.modes.C },
        },
        activate: this._config.switch_entity ? null : activate,
      };
      this._modelSig = device.sig;
      this._deviceSig = device.sig;
      this._dirty = false;
      this._notice = null;
    }

    /** Push the current model into the grid, the preset inputs and the footer. */
    _applyModelToDom() {
      if (!this._model) return;
      for (let d = 0; d < DAYS; d++) {
        for (let h = 0; h < HOURS; h++) this._applyCell(d, h);
      }
      for (const key of PRESET_KEYS) {
        const ui = this._presetInputs[key];
        const mode = this._model.modes[key] || {};
        ui.hum.value = String(this._intOr(mode.humidity, DEFAULT_HUMIDITY));
        this._setFanValue(ui, this._intOr(mode.fan, DEFAULT_FAN));
      }
      this._updateActiveToggle();
    }

    /* --------------------------------------------------------------- *
     * Grid & painting
     * --------------------------------------------------------------- */

    _setBrush(slot) {
      this._brush = slot;
      if (!this._brushButtons) return;
      for (const [key, btn] of this._brushButtons) {
        btn.classList.toggle('active', key === slot);
      }
    }

    _onCellPointerDown(ev, day, hour) {
      if (ev.pointerType === 'mouse' && ev.button !== 0) return;
      // Touch: wait for the pointerup so scrolling does not paint by accident.
      if (ev.pointerType === 'touch') {
        this._pendingTap = { day, hour, x: ev.clientX, y: ev.clientY };
        return;
      }
      ev.preventDefault();
      this._painting = true;
      this._paintAt(day, hour);
    }

    _onCellPointerEnter(day, hour) {
      if (this._painting) this._paintAt(day, hour);
    }

    _paintAt(day, hour) {
      if (!this._model) return;
      const row = this._model.grid[day];
      if (!row || row[hour] === this._brush) return;
      row[hour] = this._brush;
      this._applyCell(day, hour);
      this._markDirty();
    }

    _applyCell(day, hour) {
      const el = this._cellEls[day * HOURS + hour];
      if (!el) return;
      const slot = this._model.grid[day][hour];
      el.className = 'cell s' + slot;
      el.textContent = SLOT_LETTERS[slot];
      el.title = `${DAY_NAMES[day]} ${String(hour).padStart(2, '0')}:00 - ${SLOT_NAMES[slot]}`;
    }

    _bindWindow() {
      if (this._windowBound) return;
      this._windowBound = true;
      this._onWindowPointerUp = (ev) => this._finishPointer(ev, false);
      this._onWindowPointerCancel = (ev) => this._finishPointer(ev, true);
      window.addEventListener('pointerup', this._onWindowPointerUp);
      window.addEventListener('pointercancel', this._onWindowPointerCancel);
    }

    /** Stop painting; a touch tap (little movement) paints its cell. */
    _finishPointer(ev, cancelled) {
      this._painting = false;
      const tap = this._pendingTap;
      this._pendingTap = null;
      if (cancelled || !tap) return;
      const dx = Math.abs((ev.clientX || 0) - tap.x);
      const dy = Math.abs((ev.clientY || 0) - tap.y);
      if (dx + dy < 10) this._paintAt(tap.day, tap.hour);
    }

    /* --------------------------------------------------------------- *
     * Preset editor
     * --------------------------------------------------------------- */

    _onHumidityInput(key, input) {
      if (!this._model) return;
      const value = parseInt(input.value, 10);
      if (!Number.isFinite(value) || value < HUMIDITY_MIN || value > HUMIDITY_MAX) return;
      this._model.modes[key].humidity = value;
      this._markDirty();
    }

    _onHumidityCommit(key, input) {
      if (!this._model) return;
      const value = parseInt(input.value, 10);
      const clamped = Number.isFinite(value)
        ? Math.min(HUMIDITY_MAX, Math.max(HUMIDITY_MIN, Math.round(value)))
        : this._intOr(this._model.modes[key].humidity, DEFAULT_HUMIDITY);
      this._model.modes[key].humidity = clamped;
      if (input.value !== String(clamped)) input.value = String(clamped);
      this._markDirty();
    }

    _onFanChange(key, select) {
      if (!this._model) return;
      const value = parseInt(select.value, 10);
      if (!Number.isFinite(value)) return;
      this._model.modes[key].fan = value;
      this._markDirty();
    }

    /** Show a raw device fan value the named options cannot represent. */
    _setFanValue(ui, value) {
      const known = FAN_OPTIONS.some((option) => option.value === value);
      if (known) {
        ui.extra.hidden = true;
        ui.fan.value = String(value);
        return;
      }
      ui.extra.value = String(value);
      ui.extra.textContent = `Raw ${value}`;
      ui.extra.hidden = false;
      ui.fan.value = String(value);
    }

    /* --------------------------------------------------------------- *
     * Activation
     * --------------------------------------------------------------- */

    _updateActiveToggle() {
      if (this._switchEl) {
        const state = this._hass.states[this._config.switch_entity];
        const on = !!state && state.state === 'on';
        this._switchEl.textContent = !state
          ? this._config.switch_entity + ' (unavailable)'
          : on ? 'Schedule active' : 'Schedule inactive';
        this._switchEl.classList.toggle('on', on);
        this._switchEl.disabled = !state || this._saving;
        return;
      }
      if (this._activateCb && this._model) {
        this._activateCb.checked = this._model.activate !== false;
      }
    }

    async _onToggleActive() {
      if (!this._switchEl || this._switchEl.disabled) return;
      const state = this._hass.states[this._config.switch_entity];
      const on = !!state && state.state === 'on';
      this._switchEl.disabled = true;
      try {
        await this._hass.callService('switch', on ? 'turn_off' : 'turn_on', {
          entity_id: this._config.switch_entity,
        });
        this._notice = { kind: 'saved', text: on ? 'Schedule switched off' : 'Schedule switched on' };
      } catch (err) {
        this._notice = { kind: 'error', text: this._errorText(err) };
      }
      this._updateActiveToggle();
      this._updateFooter();
    }

    /* --------------------------------------------------------------- *
     * Footer: status, save, discard
     * --------------------------------------------------------------- */

    _markDirty() {
      if (!this._model) return;
      this._dirty = true;
      this._notice = null;
      this._updateFooter();
    }

    _updateFooter() {
      if (!this._saveBtn) return;
      const busy = this._saving;
      this._saveBtn.disabled = busy || !this._dirty;
      this._saveBtn.textContent = busy ? 'Saving...' : 'Save';
      this._saveBtn.classList.toggle('busy', busy);
      this._discardBtn.disabled = busy || !this._dirty;

      let text = 'No unsaved changes';
      let tone = 'idle';
      if (busy) {
        text = 'Saving...';
        tone = 'dirty';
      } else if (this._notice) {
        text = this._notice.text;
        tone = this._notice.kind;
      } else if (this._dirty) {
        text = 'Unsaved changes';
        tone = 'dirty';
      }
      this._statusEl.textContent = text;
      this._statusEl.className = 'status ' + tone;
    }

    _onDiscard() {
      if (this._saving) return;
      this._dirty = false;
      this._notice = null;
      this._pendingSig = null;
      this._adoptBlockUntil = 0;
      this._activateTouched = false;
      const device = this._readDevice();
      if (device && device.model) {
        this._adopt(device);
        this._applyModelToDom();
      }
      this._updateFooter();
    }

    async _onSave() {
      if (!this._model || this._saving || !this._dirty) return;

      const payload = { week: this._buildWeek(), modes: this._buildModes() };
      if (!this._config.switch_entity) {
        payload.activate = this._model.activate !== false;
      }

      this._saving = true;
      this._notice = null;
      this._updateFooter();
      try {
        await this._hass.callService('delonghi_comfort', 'set_schedule', payload);
        this._dirty = false;
        const sig = this._signature(this._model.grid, this._model.modes);
        this._pendingSig = sig;
        this._modelSig = sig;
        this._adoptBlockUntil = Date.now() + 10000;
        this._notice = { kind: 'saved', text: 'Saved ' + this._clock() };
      } catch (err) {
        this._notice = { kind: 'error', text: this._errorText(err) };
      }
      this._saving = false;
      this._updateFooter();
    }

    /* --------------------------------------------------------------- *
     * Helpers
     * --------------------------------------------------------------- */

    _buildWeek() {
      return this._model.grid.map((row) =>
        row.map((slot) => SLOT_CHARS[slot] || '0').join('')
      );
    }

    _buildModes() {
      const modes = {};
      for (const key of PRESET_KEYS) {
        const mode = this._model.modes[key] || {};
        modes[key] = {
          humidity: this._intOr(mode.humidity, DEFAULT_HUMIDITY),
          fan: this._intOr(mode.fan, DEFAULT_FAN),
        };
      }
      return modes;
    }

    /** Stable fingerprint of a schedule, used to detect real device changes. */
    _signature(grid, modes) {
      const week = grid.map((row) =>
        row.map((slot) => SLOT_CHARS[slot] || '0').join('')
      );
      const normalised = {};
      for (const key of PRESET_KEYS) {
        const mode = modes[key] || {};
        normalised[key] = {
          humidity: this._intOr(mode.humidity, DEFAULT_HUMIDITY),
          fan: this._intOr(mode.fan, DEFAULT_FAN),
        };
      }
      return JSON.stringify([week, normalised]);
    }

    _showMessage(text) {
      if (!this._built) return;
      this._msgEl.textContent = text;
      this._msgEl.hidden = false;
      this._editorEl.hidden = true;
    }

    _showEditor() {
      this._msgEl.hidden = true;
      this._editorEl.hidden = false;
    }

    _intOr(value, fallback) {
      const num = parseInt(value, 10);
      return Number.isFinite(num) ? num : fallback;
    }

    _errorText(err) {
      return err && err.message ? err.message : String(err);
    }

    _clock() {
      const now = new Date();
      const pad = (value) => String(value).padStart(2, '0');
      return `${pad(now.getHours())}:${pad(now.getMinutes())}`;
    }

    _el(tag, className, text) {
      const el = document.createElement(tag);
      if (className) el.className = className;
      if (text !== undefined && text !== null) el.textContent = text;
      return el;
    }
  }

  /* --------------------------------------------------------------------- *
   * Registration
   * --------------------------------------------------------------------- */

  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card && card.type === 'delonghi-schedule-card')) {
    window.customCards.push({
      type: 'delonghi-schedule-card',
      name: "De'Longhi Schedule",
      description: "View and edit the weekly schedule of a De'Longhi dehumidifier",
    });
  }

  if (!customElements.get('delonghi-schedule-card')) {
    customElements.define('delonghi-schedule-card', DelonghiScheduleCard);
  }
})();
