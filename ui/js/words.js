// Words, 50 a page: the ones still missing a meaning first, most common first. A meaning
// typed here shows on the back of the word's card.
import { content } from "./api.js";
import { el, errorBox, pageNumber, pager, show } from "./dom.js";

const page = document.getElementById("page");

async function load() {
  try {
    const list = await content(`/words?page=${pageNumber()}`);
    show(page,
      el("div", { class: "page-head" }, el("h1", {}, "Words"),
        el("p", {}, "Add your own meaning and it shows on the word's card. Words still missing a meaning come first, most common first.")),
      list.items.length === 0
        ? el("div", { class: "panel center" }, el("p", { class: "muted" }, "Words appear here once you add a sentence."),
            el("a", { class: "btn", href: "add.html" }, "Add a sentence"))
        : [el("div", { class: "table-wrap" }, el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "Word"), el("th", { class: "hide-small" }, "Rank"), el("th", {}, "Meaning"))),
            el("tbody", {}, list.items.map(row)))),
          pager("words.html", list.page, list.has_next)]);
  } catch (error) {
    show(page, errorBox(error, load));
  }
}

function row(word) {
  const input = el("input", { name: "meaning", value: word.meaning ?? "", placeholder: "Meaning...",
                              "aria-label": `Meaning of ${word.headword}` });
  const status = el("span", { class: "saved", "aria-live": "polite" });
  const save = async (event) => {
    event.preventDefault();
    status.textContent = "";
    try {
      const saved = await content(`/words/${word.id}/meaning`, { method: "PUT", body: { meaning: input.value || null } });
      input.value = saved.meaning ?? "";
      status.textContent = "Saved";
    } catch (error) {
      status.textContent = error.message;
    }
  };
  return el("tr", {},
    el("td", { lang: "es" }, word.headword),
    el("td", { class: "hide-small rank" }, word.frequency_rank ? `#${word.frequency_rank}` : "-"),
    el("td", {}, el("form", { class: "inline", onsubmit: save }, input,
      el("button", { type: "submit", class: "btn-ghost btn-sm" }, "Save"), status)));
}

load();
