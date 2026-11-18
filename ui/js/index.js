// Dashboard. The numbers come from the scheduler, the sentence count from content. The two
// are asked separately, so one service being down never blanks the other's part of the page.
import { content, scheduler } from "./api.js";
import { el, errorBox, plural, show } from "./dom.js";

const page = document.getElementById("page");

async function load() {
  const [stats, sentences] = await Promise.allSettled([scheduler("/stats"), content("/sentences?page=1")]);
  if (stats.status === "fulfilled" && stats.value.goal === null) {
    location.href = "goal.html"; // first visit: choose a daily goal first
    return;
  }
  const total = sentences.status === "fulfilled" ? sentences.value.total : null;
  show(page,
    stats.status === "fulfilled" ? today(stats.value, total) : errorBox(stats.reason, load),
    sentences.status === "rejected" && el("p", { class: "muted small" },
      `Sentence count unavailable: ${sentences.reason.message}`));
}

function today(stats, total) {
  const waiting = stats.due_now + stats.new_left_today;
  const planned = stats.reviewed_today + waiting;
  const percent = planned ? Math.floor((100 * stats.reviewed_today) / planned) : 100;
  return [
    stats.level === null && el("div", { class: "banner" },
      el("p", {}, el("strong", {}, "Not sure where to start? "),
        "A 2-minute quiz finds your level and skips what you already know."),
      el("a", { class: "btn btn-sm", href: "placement.html" }, "Find my level")),
    el("section", { class: "panel hero" },
      el("div", {}, el("h1", {}, "¡Hola!"), ...heroText(waiting, total)),
      el("div", { class: "ring", style: `--p: ${percent}`, role: "img", "aria-label": `${percent}% of today's cards done` },
        el("div", { class: "ring-inner" },
          el("span", { class: "ring-value" }, `${percent}%`), el("span", { class: "ring-label" }, "today")))),
    el("div", { class: "stats" },
      stat("stat-due", stats.due_now, "Due now"),
      stat("stat-new", stats.new_left_today, "New left today"),
      stat("stat-done", stats.reviewed_today, "Reviewed today"),
      stat("stat-total", total ?? "?", "Sentences")),
    el("div", { class: "meta" },
      el("span", { class: "pill" }, `Daily goal: ${stats.goal} new cards a day · `, el("a", { href: "goal.html" }, "Change")),
      stats.level !== null && el("span", { class: "pill" }, `Level: ${stats.level_name} · `,
        el("a", { href: "placement.html" }, "Retake quiz"))),
  ];
}

function heroText(waiting, total) {
  if (waiting > 0) {
    return [el("p", {}, "You have ", el("strong", {}, plural(waiting, "card")), " waiting today."),
            el("a", { class: "btn btn-lg", href: "review.html" }, "Start review")];
  }
  if (total === 0) {
    return [el("p", {}, "Start with a sentence you'd like to learn."),
            el("a", { class: "btn btn-lg", href: "add.html" }, "Add a sentence")];
  }
  return [el("p", {}, "Nothing left for today. Come back tomorrow. ¡Hasta mañana!"),
          el("a", { class: "btn btn-ghost", href: "add.html" }, "Add a sentence")];
}

function stat(kind, value, label) {
  return el("div", { class: `stat ${kind}` },
    el("span", { class: "stat-value" }, value), el("span", { class: "stat-label" }, label));
}

load();
