// The Meals sidebar page: person, month and day pickers, buttons to step a day
// or a month, a week of kcal as bars, and the day's items (the
// meal-recorder-card). The pickers and buttons work through the integration's
// select and button entities; the bars come from the daily statistics the
// integration writes, read a week at a time.

import "./meal-recorder-card.js";

const PICKERS = [
  ["select.meals_person", "Person"],
  ["select.meals_year", "Year"],
  ["select.meals_month", "Month"],
  ["select.meals_day", "Day"],
];
const STEPS = [
  ["button.meals_previous_month", "mdi:chevron-double-left", "Month"],
  ["button.meals_previous_week", "mdi:calendar-arrow-left", "Week"],
  ["button.meals_previous_day", "mdi:chevron-left", "Day"],
  ["button.meals_next_day", "mdi:chevron-right", "Day"],
  ["button.meals_next_week", "mdi:calendar-arrow-right", "Week"],
  ["button.meals_next_month", "mdi:chevron-double-right", "Month"],
];

// Fixed order, never cycled: protein, carbohydrate, fat.
const MACROS = [
  ["protein", "Protein"],
  ["carbohydrate", "Carb"],
  ["fat", "Fat"],
];
const FIELDS = ["kcal", ...MACROS.map(([field]) => field)];

const isoDate = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

// The Monday of that date's week.
const weekStart = (date) => {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  return start;
};

// Fixed axes, so a week reads the same whatever is in it.
const KCAL_MAX = 3000;
const MACRO_MAX = 400;

const addDays = (date, days) => {
  const moved = new Date(date);
  moved.setDate(moved.getDate() + days);
  return moved;
};

class MealRecorderPanel extends HTMLElement {
  // Each time the page is opened it shows today.
  connectedCallback() {
    this._openOnToday = true;
    if (this._hass) this._showToday();
  }

  _showToday() {
    this._openOnToday = false;
    this._hass.callService("button", "press", { entity_id: "button.meals_today" });
  }

  set hass(hass) {
    this._hass = hass;
    if (this._openOnToday) this._showToday();
    if (!this._built) this._build();
    this._menu.hass = hass;
    this._card.hass = hass;
    this._updatePickers();
    this._updateChart();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menu) this._menu.narrow = narrow;
  }

  set panel(_panel) {}

  _build() {
    this._built = true;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar"><span class="menu"></span><div class="title">Meal record</div></div>
      <div class="content">
        <div class="column">
          <ha-card class="controls">
            <div class="pickers">
              ${PICKERS.map(([entity, label]) => `<label>${label}<select data-entity="${entity}"></select></label>`).join("")}
            </div>
            <div class="steps">
              ${STEPS.map(([entity, icon, label]) => `<button data-entity="${entity}"><ha-icon icon="${icon}"></ha-icon>${label}</button>`).join("")}
            </div>
          </ha-card>
          <div class="items"></div>
        </div>
        <div class="column">
          <ha-card class="chart">
            <div class="chart-head">
              <button class="icon" data-week="-1" title="Previous week"><ha-icon icon="mdi:chevron-left"></ha-icon></button>
              <div class="chart-title">Energy Consumed (kcal)<span class="range"></span></div>
              <button class="icon" data-week="1" title="Next week"><ha-icon icon="mdi:chevron-right"></ha-icon></button>
            </div>
            <div class="chart-body kcal-body"></div>
          </ha-card>
          <ha-card class="chart">
            <div class="chart-head">
              <div class="chart-title">Nutrients Consumed (g)</div>
              <div class="legend">
                ${MACROS.map(([field, label], index) => `<span class="key"><i class="s${index + 1}"></i>${label}</span>`).join("")}
              </div>
            </div>
            <div class="chart-body macro-body"></div>
          </ha-card>
        </div>
      </div>`;

    this._menu = document.createElement("ha-menu-button");
    this._menu.narrow = this._narrow;
    root.querySelector(".menu").appendChild(this._menu);

    this._card = document.createElement("meal-recorder-card");
    this._card.setConfig({ entity: "sensor.meals_day" });
    root.querySelector(".items").appendChild(this._card);

    root.querySelectorAll("select").forEach((select) =>
      select.addEventListener("change", () =>
        this._hass.callService("select", "select_option", { entity_id: select.dataset.entity, option: select.value })
      )
    );
    root.querySelectorAll("button[data-entity]").forEach((button) =>
      button.addEventListener("click", () =>
        this._hass.callService("button", "press", { entity_id: button.dataset.entity })
      )
    );
    root.querySelectorAll("button[data-week]").forEach((button) =>
      button.addEventListener("click", () => {
        this._offset += Number(button.dataset.week);
        this._updateChart();
      })
    );
  }

  _updatePickers() {
    this.shadowRoot.querySelectorAll("select").forEach((select) => {
      const state = this._hass.states[select.dataset.entity];
      if (!state || state === select._state) return;
      select._state = state;
      const options = state.attributes.options || [];
      select.innerHTML = options.map((option) => `<option></option>`).join("");
      [...select.options].forEach((el, index) => {
        el.value = options[index];
        el.textContent = options[index];
      });
      select.value = state.state;
      select.disabled = false;
    });
  }

  // The chart ------------------------------------------------------------

  _updateChart() {
    const state = this._hass.states["sensor.meals_day"];
    if (!state) return;
    const { folder, date } = state.attributes;
    if (!folder || !date) return;

    // Picking another day goes back to that day's own week.
    const dayChanged = date !== this._day;
    if (dayChanged) {
      this._day = date;
      this._offset = 0;
    }
    const start = addDays(weekStart(new Date(`${date}T00:00:00`)), this._offset * 7);
    const key = `${folder}|${isoDate(start)}`;
    if (key === this._week) {
      // Same week, so only the highlighted day can have changed.
      if (dayChanged && this._rows) this._drawWeek(this._start, this._rows, this._failed);
      return;
    }
    this._week = key;
    this._loadWeek(folder, start);
  }

  async _loadWeek(folder, start) {
    const id = (field) => `meal_recorder:${folder}_${field}`;
    let days = {};
    let failed = null;
    try {
      const result = await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: start.toISOString(),
        end_time: addDays(start, 7).toISOString(),
        statistic_ids: FIELDS.map(id),
        period: "day",
        types: ["change"],
      });
      days = Object.fromEntries(
        FIELDS.map((field) => {
          const perDay = {};
          for (const row of result[id(field)] || []) {
            const when = new Date(typeof row.start === "number" ? row.start : Date.parse(row.start));
            perDay[isoDate(when)] = Math.round(row.change || 0);
          }
          return [field, perDay];
        })
      );
    } catch (err) {
      failed = err?.message || String(err);
    }
    this._start = start;
    this._rows = days;
    this._failed = failed;
    this._drawWeek(start, days, failed);
  }

  _drawWeek(start, days, failed) {
    const root = this.shadowRoot;
    const end = addDays(start, 6);
    const short = { day: "numeric", month: "short" };
    root.querySelector(".range").textContent = failed
      ? ""
      : ` · ${start.toLocaleDateString(undefined, short)} – ${end.toLocaleDateString(undefined, short)}`;

    if (failed) {
      root.querySelectorAll(".chart-body").forEach((el) => {
        el.innerHTML = `<div class="none">${failed}</div>`;
      });
      return;
    }

    const week = [];
    for (let index = 0; index < 7; index += 1) {
      const day = addDays(start, index);
      week.push({ day, key: isoDate(day) });
    }

    const kcal = days.kcal || {};
    root.querySelector(".kcal-body").innerHTML = this._plot(
      week,
      KCAL_MAX,
      ({ key }, top) => {
        const value = kcal[key] || 0;
        return `<div class="bar" style="height:${Math.min(100, (value / top) * 100)}%" title="${key}: ${value} kcal"></div>`;
      }
    );

    // One scale across the three macros, so their bars compare.
    root.querySelector(".macro-body").innerHTML = this._plot(
      week,
      MACRO_MAX,
      ({ key }, top) =>
        MACROS.map(([field, label], index) => {
          const value = (days[field] || {})[key] || 0;
          return `<div class="bar s${index + 1}" style="height:${Math.min(100, (value / top) * 100)}%" title="${key}: ${label} ${value} g"></div>`;
        }).join("")
    );
  }

  // Axis, gridlines, bars and the day labels, as one block of markup.
  _plot(week, top, bars) {
    const ticks = [0, 25, 50, 75, 100];
    return `
      <div class="axis">
        ${ticks.map((at) => `<span style="bottom:${at}%">${Math.round((top * at) / 100).toLocaleString()}</span>`).join("")}
      </div>
      <div class="plot">
        ${ticks.map((at) => `<i style="bottom:${at}%"></i>`).join("")}
        <div class="bars">
          ${week
            .map((entry) => `<div class="col${entry.key === this._day ? " on" : ""}">${bars(entry, top)}</div>`)
            .join("")}
        </div>
      </div>
      <div class="ticks">
        ${week
          .map(
            ({ day, key }) => `
          <div class="tick${key === this._day ? " on" : ""}">
            ${day.toLocaleDateString(undefined, { weekday: "narrow" })}<span>${day.getDate()}</span>
          </div>`
          )
          .join("")}
      </div>`;
  }
}

const STYLE = `
  :host { display: block; min-height: 100vh; overflow-x: hidden; background: var(--primary-background-color); color: var(--primary-text-color); }
  *, *::before, *::after { box-sizing: border-box; }
  .toolbar { display: flex; align-items: center; height: 56px; padding: 0 12px; gap: 8px; background: var(--app-header-background-color); color: var(--app-header-text-color, white); border-bottom: var(--app-header-border-bottom, none); }
  .title { font-size: 20px; }
  .content { max-width: 1240px; margin: 0 auto; padding: 16px; display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; align-items: start; }
  .column { display: grid; gap: 16px; align-content: start; min-width: 0; overflow: hidden; }
  .content > *, .column > * { min-width: 0; max-width: 100%; }
  .controls { padding: 16px; display: grid; gap: 12px; }
  .pickers { display: grid; grid-template-columns: repeat(auto-fit, minmax(116px, 1fr)); gap: 8px; }
  label { display: flex; flex-direction: column; gap: 2px; font-size: 0.85em; color: var(--secondary-text-color); }
  select { font: inherit; font-size: 1rem; padding: 6px 8px; border: 1px solid var(--divider-color); border-radius: 6px; background: var(--card-background-color); color: var(--primary-text-color); min-width: 0; }
  .steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(82px, 1fr)); gap: 6px; }
  .chart { padding: 16px 16px 12px; overflow: hidden; min-width: 0; }
  .chart-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .chart-title { font-weight: 500; }
  .range, .tick span, .value { color: var(--secondary-text-color); font-weight: 400; }
  .chart-body { display: grid; grid-template-columns: 38px minmax(0, 1fr); column-gap: 8px; margin-top: 12px; }
  .axis { position: relative; height: 260px; overflow: visible; }
  .axis span { position: absolute; right: 0; transform: translateY(50%); font-size: 0.72em; line-height: 1; color: var(--secondary-text-color); white-space: nowrap; }
  .plot { position: relative; height: 260px; min-width: 0; }
  .plot i { position: absolute; left: 0; right: 0; border-top: 1px solid var(--divider-color); }
  .bars { position: absolute; inset: 0; display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; align-items: end; }
  .col { height: 100%; display: flex; align-items: flex-end; gap: 2px; }
  .bar { flex: 1; background: var(--primary-color); border-radius: 4px 4px 0 0; }
  .kcal-body .col.on .bar { background: var(--accent-color); }
  .ticks { grid-column: 2; display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; margin-top: 4px; }
  .tick.on { font-weight: 700; color: var(--primary-text-color); }
  /* Three fixed hues, checked for colour-vision separation in both modes. */
  .s1 { background: #2a78d6; }
  .s2 { background: #eb6834; }
  .s3 { background: #199e70; }
  .legend { display: flex; gap: 10px; font-size: 0.8em; color: var(--secondary-text-color); }
  .key { display: inline-flex; align-items: center; gap: 4px; }
  .key i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
  @media (prefers-color-scheme: dark) {
    .s1 { background: #3987e5; }
    .s2 { background: #d95926; }
    .s3 { background: #199e70; }
  }
  .tick { font-size: 0.8em; display: flex; flex-direction: column; align-items: center; line-height: 1.1; color: var(--secondary-text-color); }
  .none { color: var(--secondary-text-color); padding: 12px 0; }
  button.icon { border: none; padding: 4px; color: var(--secondary-text-color); }
  button { font: inherit; cursor: pointer; border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); border-radius: 6px; padding: 8px 4px; display: inline-flex; align-items: center; justify-content: center; gap: 2px; min-width: 0; overflow: hidden; }
  ha-icon { --mdc-icon-size: 20px; }
`;

customElements.get("meal-recorder-panel") || customElements.define("meal-recorder-panel", MealRecorderPanel);
