// Add a sentence. Content stores it and its words; the scheduler pulls it as new cards later.
import { content } from "./api.js";
import { el, show } from "./dom.js";

const page = document.getElementById("page");

function render() {
  const alert = el("p", { class: "alert", hidden: true });
  const form = el("form", { class: "form", onsubmit: (event) => save(event, form, alert) },
    el("label", { class: "field" }, "Spanish",
      el("input", { name: "spanish", lang: "es", placeholder: "Ojalá llueva mañana.", required: true })),
    el("label", { class: "field" }, "English",
      el("input", { name: "english", placeholder: "I hope it rains tomorrow.", required: true })),
    el("label", { class: "field" }, "Grammar note ",
      el("span", { class: "hint" }, "Optional. Left blank, it is filled in when a grammar rule matches."),
      el("input", { name: "grammar_note" })),
    el("div", { class: "actions" }, el("button", { type: "submit" }, "Save sentence")));

  show(page, el("div", { class: "narrow" },
    el("div", { class: "page-head" }, el("h1", {}, "Add a sentence"),
      el("p", {}, "Found a sentence you like? Save it and it becomes cards: one for the sentence and one for each new word.")),
    el("div", { class: "panel" }, alert, form)));
}

async function save(event, form, alert) {
  event.preventDefault();
  const data = new FormData(form);
  try {
    const sentence = await content("/sentences", { method: "POST", body: {
      spanish: data.get("spanish"), english: data.get("english"), grammar_note: data.get("grammar_note") || null,
    } });
    location.href = `sentence.html?id=${sentence.id}`;
  } catch (error) {
    alert.textContent = error.message;
    alert.hidden = false;
  }
}

render();
