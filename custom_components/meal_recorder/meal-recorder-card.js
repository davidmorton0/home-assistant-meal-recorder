// The Meal Recorder item list: a day's items from sensor.meals_day, with an
// edit and a delete button on each, and a button to add an item.
//
//   type: custom:meal-recorder-card
//   entity: sensor.meals_day   # optional, this is the default

const MEALS = ["breakfast", "lunch", "dinner", "snack"];
const NUMBERS = [
  ["mass", "Mass (g)"],
  ["kcal", "kcal"],
  ["protein", "Protein (g)"],
  ["carbohydrate", "Carb (g)"],
  ["fat", "Fat (g)"],
];

const escape = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const capitalise = (text) => text.charAt(0).toUpperCase() + text.slice(1);

class MealRecorderCard extends HTMLElement {
  setConfig(config) {
    this._config = { entity: "sensor.meals_day", ...config };
    this._form = null; // { id: null for a new item, values: {...}, error, busy }
    this._confirm = null; // id of the item waiting for "are you sure"
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config.entity];
    if (state !== this._state) {
      this._state = state;
      this._render();
    }
  }

  getCardSize() {
    return 6;
  }

  static getStubConfig() {
    return { entity: "sensor.meals_day" };
  }

  // Actions -------------------------------------------------------------

  _startAdd() {
    const now = new Date();
    const time = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    this._form = {
      id: null,
      values: { date: this._state.attributes.date, time, meal: "snack", name: "", portion: "", mass: "", kcal: "", protein: "", carbohydrate: "", fat: "" },
    };
    this._confirm = null;
    this._render();
  }

  _startEdit(id) {
    const item = this._items().find((i) => i.id === id);
    if (!item) return;
    this._form = { id, values: { ...item } };
    this._confirm = null;
    this._render();
  }

  async _save() {
    const v = this._form.values;
    const data = {
      created_at: `${v.date}T${v.time}:00`,
      name: v.name,
      meal: v.meal,
      portion: v.portion || "",
    };
    for (const [field] of NUMBERS) data[field] = v[field] === "" ? NaN : Number(v[field]);
    const missing = NUMBERS.filter(([field]) => Number.isNaN(data[field])).map(([, label]) => label);
    if (!v.name.trim() || !v.date || !v.time || missing.length) {
      this._form.error = `Fill in ${[!v.name.trim() && "the name", !v.date && "the date", !v.time && "the time", ...missing].filter(Boolean).join(", ")}.`;
      this._render();
      return;
    }
    if (this._form.id) data.id = this._form.id;
    else data.person = this._state.attributes.person;
    await this._call(this._form.id ? "update_item" : "add_item", data, () => {
      this._form = null;
    });
  }

  async _delete(id) {
    await this._call("delete_item", { id }, () => {
      this._confirm = null;
    });
  }

  async _call(service, data, done) {
    const target = this._form || {};
    target.busy = true;
    target.error = null;
    this._render();
    try {
      await this._hass.callService("meal_recorder", service, data);
      done();
    } catch (err) {
      const message = err?.message || String(err);
      if (this._form) this._form.error = message;
      else this._error = message;
    }
    target.busy = false;
    this._render();
  }

  // Rendering -----------------------------------------------------------

  _items() {
    return this._state?.attributes.items || [];
  }

  _render() {
    if (!this.shadowRoot) return;
    const state = this._state;
    if (!state) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">${escape(this._config.entity)} not found</div></ha-card>`;
      return;
    }
    const a = state.attributes;
    const day = new Date(`${a.date}T00:00:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    const totals = a.totals || {};
    const items = this._items();

    const sections = MEALS.map((meal) => {
      const rows = items.filter((item) => item.meal === meal);
      const kcal = a.meal_totals?.[meal]?.kcal ?? 0;
      return `
        <div class="meal">
          <div class="meal-head"><span>${capitalise(meal)}</span><span>${kcal} kcal</span></div>
          ${rows.length ? rows.map((item) => this._row(item)).join("") : `<div class="none">Nothing recorded</div>`}
        </div>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head">
          <div>
            <div class="title">${escape(a.person)}</div>
            <div class="sub">${escape(day)}</div>
          </div>
          <button class="primary" data-action="add" ${this._form ? "disabled" : ""}><ha-icon icon="mdi:plus"></ha-icon>Add item</button>
        </div>
        ${this._form && !this._form.id ? this._formHtml() : ""}
        ${this._error ? `<div class="error">${escape(this._error)}</div>` : ""}
        ${sections}
        <div class="total">
          <strong>Day total ${totals.kcal ?? 0} kcal</strong>
          <span>protein ${totals.protein ?? 0}g · carb ${totals.carbohydrate ?? 0}g · fat ${totals.fat ?? 0}g</span>
        </div>
      </ha-card>`;
    this._bind();
  }

  _row(item) {
    if (this._form && this._form.id === item.id) return this._formHtml();
    if (this._confirm === item.id) {
      return `
        <div class="row confirm">
          <span>Delete <strong>${escape(item.name)}</strong>?</span>
          <span class="actions">
            <button data-action="cancel-delete">Cancel</button>
            <button class="danger" data-action="confirm-delete" data-id="${escape(item.id)}">Delete</button>
          </span>
        </div>`;
    }
    return `
      <div class="row">
        <span class="time">${escape(item.time)}</span>
        <span class="name">${escape(item.name)}${item.portion ? `<span class="portion">${escape(item.portion)} · ${item.mass} g</span>` : `<span class="portion">${item.mass} g</span>`}</span>
        <span class="kcal">${item.kcal} kcal<span class="macros">protein ${item.protein}g · carb ${item.carbohydrate}g · fat ${item.fat}g</span></span>
        <span class="actions">
          <button class="icon" title="Edit" data-action="edit" data-id="${escape(item.id)}" ${this._form ? "disabled" : ""}><ha-icon icon="mdi:pencil"></ha-icon></button>
          <button class="icon" title="Delete" data-action="delete" data-id="${escape(item.id)}" ${this._form ? "disabled" : ""}><ha-icon icon="mdi:delete"></ha-icon></button>
        </span>
      </div>`;
  }

  _formHtml() {
    const { values: v, error, busy, id } = this._form;
    const input = (field, label, type = "text", extra = "") =>
      `<label>${label}<input name="${field}" type="${type}" value="${escape(v[field])}" ${extra}></label>`;
    return `
      <form class="form">
        <div class="form-title">${id ? "Edit item" : "Add item"}</div>
        ${input("name", "Name", "text", 'maxlength="200" required')}
        ${input("portion", "Portion", "text", 'maxlength="100"')}
        <label>Meal<select name="meal">${MEALS.map((m) => `<option value="${m}" ${v.meal === m ? "selected" : ""}>${capitalise(m)}</option>`).join("")}</select></label>
        <div class="pair">${input("date", "Date", "date")}${input("time", "Time", "time")}</div>
        <div class="numbers">${NUMBERS.map(([field, label]) => input(field, label, "number", 'min="0" step="0.1" inputmode="decimal"')).join("")}</div>
        ${error ? `<div class="error">${escape(error)}</div>` : ""}
        <div class="form-actions">
          <button type="button" data-action="cancel-form" ${busy ? "disabled" : ""}>Cancel</button>
          <button type="submit" class="primary" ${busy ? "disabled" : ""}>${busy ? "Saving…" : "Save"}</button>
        </div>
      </form>`;
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-action]").forEach((el) =>
      el.addEventListener("click", (event) => {
        const { action, id } = el.dataset;
        this._error = null;
        if (action === "add") this._startAdd();
        else if (action === "edit") this._startEdit(id);
        else if (action === "delete") { this._confirm = id; this._render(); }
        else if (action === "cancel-delete") { this._confirm = null; this._render(); }
        else if (action === "confirm-delete") this._delete(id);
        else if (action === "cancel-form") { this._form = null; this._render(); }
        event.preventDefault();
      })
    );
    const form = root.querySelector("form");
    if (form) {
      form.addEventListener("input", (event) => {
        this._form.values[event.target.name] = event.target.value;
      });
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._save();
      });
    }
  }
}

const STYLE = `
  ha-card { padding: 16px; }
  .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }
  .title { font-size: 1.3em; font-weight: 500; }
  .sub, .none, .portion, .macros, .time { color: var(--secondary-text-color); }
  .meal { margin-top: 12px; }
  .meal-head { display: flex; justify-content: space-between; font-weight: 500; padding: 4px 0; border-bottom: 1px solid var(--divider-color); }
  .none { padding: 6px 0; font-style: italic; }
  /* Wraps onto a second line in a narrow card, rather than squeezing the name. */
  .row { display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--divider-color); }
  .row.confirm { justify-content: space-between; background: color-mix(in srgb, var(--error-color) 10%, transparent); padding: 6px 8px; }
  .time { flex: 0 0 3.2em; }
  .name, .kcal { display: flex; flex-direction: column; min-width: 0; overflow-wrap: anywhere; }
  .name { flex: 1 1 9em; }
  .kcal { flex: 0 1 auto; margin-left: auto; text-align: right; }
  .macros { white-space: nowrap; }
  .portion, .macros { font-size: 0.85em; }
  .actions { display: flex; gap: 4px; }
  button { font: inherit; cursor: pointer; border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); border-radius: 6px; padding: 6px 12px; display: inline-flex; align-items: center; gap: 4px; }
  button:disabled { opacity: 0.5; cursor: default; }
  button.icon { border: none; padding: 6px; color: var(--secondary-text-color); }
  button.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  button.danger { background: var(--error-color); border-color: var(--error-color); color: #fff; }
  ha-icon { --mdc-icon-size: 20px; }
  .form { display: grid; gap: 8px; padding: 12px; margin: 8px 0; border: 1px solid var(--divider-color); border-radius: 8px; }
  .form-title { font-weight: 500; }
  label { display: flex; flex-direction: column; font-size: 0.85em; color: var(--secondary-text-color); gap: 2px; }
  input, select { font: inherit; font-size: 1rem; padding: 6px 8px; border: 1px solid var(--divider-color); border-radius: 6px; background: var(--card-background-color); color: var(--primary-text-color); min-width: 0; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .numbers { display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); gap: 8px; }
  .form-actions { display: flex; justify-content: flex-end; gap: 8px; }
  .error { color: var(--error-color); padding: 4px 0; }
  .total { display: flex; flex-direction: column; margin-top: 12px; gap: 2px; }
  .total span { color: var(--secondary-text-color); }
`;

customElements.get("meal-recorder-card") || customElements.define("meal-recorder-card", MealRecorderCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "meal-recorder-card", name: "Meal Recorder", description: "A day's meal items, with add, edit and delete." });
