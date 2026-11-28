// All sentences, 50 a page, in the order they were added (the seed is easiest first).
import { content } from "./api.js";
import { el, errorBox, pageNumber, pager, show } from "./dom.js";

const page = document.getElementById("page");
// The level a seed sentence stores (migration 002); the learner's own sentences have none.
const LEVEL_NAMES = ["Starter", "Beginner", "Elementary", "Intermediate", "Advanced"];

async function load() {
  try {
    const list = await content(`/sentences?page=${pageNumber()}`);
    show(page,
      el("div", { class: "page-head" },
        el("h1", {}, "Sentences ", el("span", { class: "count" }, `(${list.total})`)),
        el("p", {}, "Every sentence you are learning, easiest first. Open one to see its words.")),
      list.items.length === 0
        ? el("div", { class: "panel center" }, el("p", { class: "muted" }, "Start your collection."),
            el("a", { class: "btn", href: "add.html" }, "Add a sentence"))
        : [el("div", { class: "table-wrap" }, el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "Spanish"), el("th", { class: "hide-small" }, "English"),
              el("th", {}, "Level"))),
            el("tbody", {}, list.items.map((sentence) => el("tr", {},
              el("td", { lang: "es" }, el("a", { href: `sentence.html?id=${sentence.id}` }, sentence.spanish_text)),
              el("td", { class: "hide-small muted" }, sentence.english_text),
              el("td", { class: "muted" }, sentence.level === null ? "Your own" : LEVEL_NAMES[sentence.level])))))),
          pager("sentences.html", list.page, list.has_next)]);
  } catch (error) {
    show(page, errorBox(error, load));
  }
}

load();
