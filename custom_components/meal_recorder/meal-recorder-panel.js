// The Meals sidebar page: person, month and day pickers, buttons to step a day
// or a month, and the day's items (the meal-recorder-card). The pickers and
// buttons work through the integration's select and button entities.

import "./meal-recorder-card.js";

const PICKERS = [
  ["select.meals_person", "Person"],
  ["select.meals_month", "Month"],
  ["select.meals_day", "Day"],
];
const STEPS = [
  ["button.meals_previous_month", "mdi:chevron-double-left", "Month"],
  ["button.meals_previous_day", "mdi:chevron-left", "Day"],
  ["button.meals_next_day", "mdi:chevron-right", "Day"],
  ["button.meals_next_month", "mdi:chevron-double-right", "Month"],
];

class MealRecorderPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._menu.hass = hass;
    this._card.hass = hass;
    this._updatePickers();
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
      <div class="toolbar"><span class="menu"></span><div class="title">Meals</div></div>
      <div class="content">
        <ha-card class="controls">
          <div class="pickers">
            ${PICKERS.map(([entity, label]) => `<label>${label}<select data-entity="${entity}"></select></label>`).join("")}
          </div>
          <div class="steps">
            ${STEPS.map(([entity, icon, label]) => `<button data-entity="${entity}"><ha-icon icon="${icon}"></ha-icon>${label}</button>`).join("")}
          </div>
        </ha-card>
        <div class="items"></div>
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
}

const STYLE = `
  :host { display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color); }
  .toolbar { display: flex; align-items: center; height: 56px; padding: 0 12px; gap: 8px; background: var(--app-header-background-color); color: var(--app-header-text-color, white); border-bottom: var(--app-header-border-bottom, none); }
  .title { font-size: 20px; }
  .content { max-width: 720px; margin: 0 auto; padding: 16px; display: grid; gap: 16px; }
  .controls { padding: 16px; display: grid; gap: 12px; }
  .pickers { display: grid; grid-template-columns: 2fr 1.2fr 1fr; gap: 8px; }
  label { display: flex; flex-direction: column; gap: 2px; font-size: 0.85em; color: var(--secondary-text-color); }
  select { font: inherit; font-size: 1rem; padding: 6px 8px; border: 1px solid var(--divider-color); border-radius: 6px; background: var(--card-background-color); color: var(--primary-text-color); min-width: 0; }
  .steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  button { font: inherit; cursor: pointer; border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); border-radius: 6px; padding: 8px 4px; display: inline-flex; align-items: center; justify-content: center; gap: 2px; }
  ha-icon { --mdc-icon-size: 20px; }
`;

customElements.get("meal-recorder-panel") || customElements.define("meal-recorder-panel", MealRecorderPanel);
