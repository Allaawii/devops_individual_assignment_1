// Small helpers to build pages. Text is always added as text, never as HTML, so a sentence
// someone typed can never run as code in the page.

// el("a", {href: "x.html", class: "btn"}, "Label") builds <a href="x.html" class="btn">Label</a>.
// Props starting with "on" become event listeners; false, null and undefined props are left out.
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === false || value === null || value === undefined) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === false || child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// Replace everything inside `target` with the given nodes.
export function show(target, ...nodes) {
  target.replaceChildren(...nodes.flat().filter(Boolean));
}

// A friendly error box, with a "Try again" button when `retry` is given.
export function errorBox(error, retry) {
  return el("div", { class: "notice", role: "alert" },
    el("p", {}, error.message),
    retry && el("button", { type: "button", class: "btn-ghost btn-sm", onclick: retry }, "Try again"));
}

export function loading() {
  return el("p", { class: "loading" }, "Loading...");
}

// The ?page= number in the address (1 when missing or not a number).
export function pageNumber() {
  return Math.max(1, Number.parseInt(new URLSearchParams(location.search).get("page"), 10) || 1);
}

// "Previous" and "Next" links for a paged list.
export function pager(file, number, hasNext) {
  return el("nav", { class: "pager" },
    number > 1 && el("a", { class: "btn btn-ghost btn-sm", href: `${file}?page=${number - 1}` }, "Previous"),
    el("span", { class: "muted small" }, `Page ${number}`),
    hasNext && el("a", { class: "btn btn-ghost btn-sm", href: `${file}?page=${number + 1}` }, "Next"));
}

export function plural(count, word) {
  return `${count} ${count === 1 ? word : word + "s"}`;
}

// A word chip: the headword, plus its meaning when the learner has written one.
export function wordChip(word) {
  return el("li", {}, el("span", { lang: "es" }, word.headword),
    word.meaning && el("span", { class: "muted" }, ` · ${word.meaning}`));
}
