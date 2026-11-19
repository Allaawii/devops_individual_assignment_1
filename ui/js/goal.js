// Daily goal: how many new cards a day. Asked on the first visit, changeable any time.
import { scheduler } from "./api.js";
import { el, errorBox, show } from "./dom.js";

const page = document.getElementById("page");
const PRESETS = [[5, "Light"], [10, "Steady"], [20, "Serious"], [30, "Intense"]];

async function load() {
  try {
    render(await scheduler("/goal"));
  } catch (error) {
    show(page, errorBox(error, load));
  }
}

function render(goal) {
  const firstTime = goal.goal === null;
  const current = goal.goal ?? goal.default;
  const alert = el("p", { class: "alert", hidden: true });
  const form = el("form", { class: "form", onsubmit: (event) => save(event, form, alert) },
    el("div", { class: "choices" }, PRESETS.map(([amount, name], index) =>
      el("label", { class: "choice" },
        el("input", { type: "radio", name: "goal", value: amount, checked: amount === current }),
        el("span", { class: "choice-number" }, amount),
        el("span", { class: "choice-name" }, name),
        el("span", { class: "choice-sub" }, "cards per day"),
        el("span", { class: "bars", "aria-hidden": "true" },
          PRESETS.map((_, step) => el("i", { class: step <= index ? "on" : false })))))),
    el("label", { class: "field" }, "Or choose your own number ",
      el("span", { class: "hint" }, `Between ${goal.min} and ${goal.max}. It wins over the choice above.`),
      el("input", { type: "number", name: "custom", min: goal.min, max: goal.max, inputmode: "numeric",
                    placeholder: "e.g. 15" })),
    el("div", { class: "actions" },
      el("button", { type: "submit", class: "btn-lg" }, firstTime ? "Start learning" : "Save goal")));

  show(page, el("div", { class: "narrow panel" },
    el("h1", {}, firstTime ? "Welcome to Frase" : "Daily goal"),
    el("p", { class: "muted" }, firstTime
      ? "How much do you want to learn each day? This sets how many new cards (words and sentences) you get per day. Cards you have already seen keep coming back when they are due, so a smaller goal also means shorter sessions later."
      : `You currently get ${current} new cards a day. Change it any time.`),
    alert, form));
}

async function save(event, form, alert) {
  event.preventDefault();
  const data = new FormData(form);
  const chosen = Number.parseInt(data.get("custom") || data.get("goal"), 10);
  try {
    await scheduler("/goal", { method: "PUT", body: { goal: chosen } });
    const stats = await scheduler("/stats");
    // A new learner goes on to the level quiz; someone changing their goal goes back home.
    location.href = stats.level === null ? "placement.html" : "index.html";
  } catch (error) {
    alert.textContent = error.message;
    alert.hidden = false;
  }
}

load();
