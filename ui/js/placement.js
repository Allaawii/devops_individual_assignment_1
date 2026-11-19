// Placement quiz. The questions come from content; the answers go to the scheduler, which asks
// content to score them and marks the easier material as known. Skipping works even if content is down.
import { content, scheduler } from "./api.js";
import { el, errorBox, plural, show } from "./dom.js";

const page = document.getElementById("page");
const DONT_KNOW = "dont-know"; // the "I'm not sure" choice; never counted as right

let levels = [];

async function load() {
  try {
    const quiz = await content("/placement/quiz");
    levels = quiz.levels;
    render(quiz.questions);
  } catch (error) {
    show(page, el("div", { class: "narrow" },
      el("div", { class: "page-head" }, el("h1", {}, "Find your level")),
      errorBox(error, load),
      el("div", { class: "actions" }, skipButton())));
  }
}

function render(questions) {
  const alert = el("p", { class: "alert", hidden: true });
  const form = el("form", { onsubmit: (event) => submit(event, form, alert) },
    questions.map((question, index) => el("fieldset", { class: "panel question" },
      el("legend", { class: "question-head" },
        el("span", { class: "qnum" }, index + 1), el("span", { lang: "es" }, question.spanish)),
      el("div", { class: "options" },
        question.options.map((option) => el("label", { class: "choice" },
          el("input", { type: "radio", name: question.field, value: option, required: true }), option)),
        el("label", { class: "choice choice-dunno" },
          el("input", { type: "radio", name: question.field, value: DONT_KNOW }), "I'm not sure")))),
    el("div", { class: "actions" },
      questions.length > 0 && el("button", { type: "submit", class: "btn-lg" }, "See my level"),
      skipButton(questions.length > 0 ? "Skip, I'm a beginner" : "Continue")));

  show(page, el("div", { class: "narrow" },
    el("div", { class: "page-head" }, el("h1", {}, "Find your level"),
      el("p", {}, questions.length > 0
        ? "Pick what each sentence means. Choose \"I'm not sure\" rather than guessing: the quiz then skips only what you really know."
        : "There aren't enough built-in sentences for a quiz yet, so you will start from the beginning.")),
    alert, form));
}

function skipButton(label = "Skip, I'm a beginner") {
  return el("button", { type: "button", class: "btn-ghost", onclick: () => place({ skip: true }) }, label);
}

function submit(event, form, alert) {
  event.preventDefault();
  const answers = Object.fromEntries(new FormData(form));
  place({ answers }, alert);
}

async function place(body, alert) {
  try {
    result(await scheduler("/placement", { method: "POST", body }));
  } catch (error) {
    if (!alert) return show(page, errorBox(error));
    alert.textContent = error.message;
    alert.hidden = false;
    window.scrollTo(0, 0);
  }
}

function result(outcome) {
  show(page, el("div", { class: "narrow panel center" },
    el("p", { class: "muted" }, "Your level"),
    el("h1", {}, outcome.level_name),
    levels.length > 0 && el("ol", { class: "ladder" }, levels.map((name, index) =>
      el("li", { class: index === outcome.level ? "current" : index < outcome.level ? "passed" : false }, name))),
    el("p", {}, outcome.skipped > 0
      ? `You already know the easiest material, so ${plural(outcome.skipped, "card")} were marked as known. They come back once for a quick check over the next few months; everything new starts at your level.`
      : "You will start from the beginning, with the most common words and short sentences."),
    el("div", { class: "actions" },
      el("a", { class: "btn btn-lg", href: "review.html" }, "Start learning"),
      el("a", { class: "btn btn-ghost", href: "index.html" }, "Go to today"))));
}

load();
