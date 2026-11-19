// One sentence (sentence.html?id=N): its translation, grammar note, words and source.
import { content } from "./api.js";
import { el, errorBox, show, wordChip } from "./dom.js";

const page = document.getElementById("page");
const id = Number.parseInt(new URLSearchParams(location.search).get("id"), 10);

async function load() {
  try {
    const { sentence, words } = await content(`/sentences/${id}`);
    document.title = `${sentence.spanish_text} · Frase`;
    show(page, el("div", { class: "narrow" },
      backLink(),
      el("article", { class: "panel" },
        el("h1", { class: "sentence-title", lang: "es" }, sentence.spanish_text),
        el("p", { class: "answer" }, sentence.english_text),
        sentence.grammar_note && el("p", { class: "note" }, sentence.grammar_note),
        el("h2", {}, "Words in this sentence"),
        words.length > 0 ? el("ul", { class: "chips" }, words.map(wordChip)) : el("p", { class: "muted" }, "No content words."),
        el("h2", {}, "Source"),
        el("p", { class: "source" }, sentence.source === "user" ? "Added by you" : sentence.source))));
  } catch (error) {
    show(page, el("div", { class: "narrow" }, backLink(), errorBox(error, error.status === 404 ? null : load)));
  }
}

function backLink() {
  return el("p", { class: "small" }, el("a", { href: "sentences.html" }, "All sentences"));
}

load();
