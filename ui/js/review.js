// Review: one card at a time from the scheduler, which also fetches the card's text from content.
// If content is down the scheduler answers with a designed 503, shown here as a calm notice.
import { scheduler } from "./api.js";
import { el, errorBox, loading, plural, show, wordChip } from "./dom.js";

const page = document.getElementById("page");

// [button label, quality sent to the scheduler, what pressing it means]
const RATINGS = [
  ["Again", 0, "I forgot it"],
  ["Hard", 3, "I remembered it with effort"],
  ["Good", 4, "I remembered it"],
  ["Easy", 5, "It was too easy"],
];

let current = null; // the card on screen: {id, reveal}, used by the keyboard shortcuts

async function load() {
  current = null;
  show(page, loading());
  try {
    const next = await scheduler("/review/next");
    show(page, next.card ? cardView(next) : doneView(next.progress));
  } catch (error) {
    show(page, unavailableView(error));
  }
}

function cardView({ card, content, intervals, progress }) {
  const isSentence = card.card_type === "sentence";
  const reveal = el("details", { class: "reveal" },
    el("summary", {}, "Show answer"),
    el("div", { class: "back" },
      isSentence ? sentenceBack(content) : wordBack(content),
      el("div", { class: "ratings" }, RATINGS.map(([label, quality, meaning], index) =>
        el("button", { type: "button", class: `rate rate-${label.toLowerCase()}`, title: meaning,
                       onclick: () => rate(card.id, quality) },
          el("kbd", {}, index + 1), label))),
      helpView(intervals)));
  current = { id: card.id, reveal };

  return el("div", { class: "narrow" },
    el("div", { class: "session" },
      el("progress", { value: progress.done, max: progress.done + progress.remaining, "aria-label": "Today's progress" }),
      el("span", {}, `${progress.done} done · ${progress.remaining} to go`)),
    el("article", { class: "panel flashcard" },
      el("span", { class: `kind kind-${card.card_type}` }, isSentence ? "Sentence card" : "Word card"),
      el("p", { class: "front", lang: "es" }, isSentence ? content.sentence.spanish_text : content.word.headword),
      reveal),
    el("p", { class: "keys" }, "Keyboard: S shows the answer, 1 to 4 rate it."));
}

function sentenceBack({ sentence, key_words: keyWords }) {
  return [
    el("p", { class: "answer" }, sentence.english_text),
    sentence.grammar_note && el("p", { class: "note" }, sentence.grammar_note),
    keyWords.length > 0 && el("div", { class: "key-words" },
      el("span", { class: "key-label" }, "Key words"), el("ul", { class: "chips" }, keyWords.map(wordChip))),
  ];
}

function wordBack({ word, examples }) {
  return [
    word.meaning && el("p", { class: "answer" }, word.meaning),
    el("ul", { class: "examples" }, examples.map((example) => el("li", {},
      el("span", { lang: "es" }, example.spanish_text), el("span", { class: "muted small" }, example.english_text)))),
    !word.meaning && el("p", { class: "small" }, el("a", { href: "words.html" }, "Add a meaning for this word")),
  ];
}

function helpView(intervals) {
  return el("details", { class: "help" },
    el("summary", {}, "What the buttons do"),
    el("ul", {}, RATINGS.map(([label, quality, meaning]) => {
      const days = intervals[String(quality)];
      return el("li", {}, el("strong", {}, label),
        `: ${meaning}. You will see this card again ${days === 1 ? "tomorrow" : `in ${days} days`}.`);
    })),
    el("p", { class: "muted" }, "The more often you remember a card, the longer it waits before coming back."));
}

function doneView(progress) {
  return el("div", { class: "narrow panel center" },
    el("h1", {}, "Done for today"),
    el("p", { class: "muted" }, progress.done === 0
      ? "There is nothing to review right now. Add a sentence and its cards appear here."
      : `You reviewed ${plural(progress.done, "card")} today. Your next cards will be due tomorrow or later. ¡Buen trabajo!`),
    el("div", { class: "actions" },
      el("a", { class: "btn", href: "add.html" }, "Add a sentence"),
      el("a", { class: "btn btn-ghost", href: "index.html" }, "Back to today")));
}

function unavailableView(error) {
  const title = error.code === "content_unavailable" ? "Sentences are not available right now" : "Reviews are not available right now";
  return el("div", { class: "narrow panel center" },
    el("h1", {}, title),
    errorBox(error, load),
    el("p", { class: "small" }, el("a", { href: "index.html" }, "Back to today")));
}

async function rate(cardId, quality) {
  current = null; // ignore further key presses until the next card is shown
  for (const button of page.querySelectorAll(".rate")) button.disabled = true;
  try {
    await scheduler(`/review/${cardId}`, { method: "POST", body: { quality } });
    await load();
  } catch (error) {
    show(page, unavailableView(error));
  }
}

document.addEventListener("keydown", (event) => {
  if (!current || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.key.toLowerCase() === "s") {
    current.reveal.open = true;
  } else if (current.reveal.open && ["1", "2", "3", "4"].includes(event.key)) {
    rate(current.id, RATINGS[Number(event.key) - 1][1]);
  }
});

load();
