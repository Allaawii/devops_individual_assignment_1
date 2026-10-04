# Frase: a contextual Spanish spaced-repetition trainer

*Frase* is Spanish for "sentence". It's a web app for learning Spanish from real sentences, not isolated word lists. Every sentence becomes flashcards (one for the sentence and one for each new word), and a spaced-repetition algorithm decides when each card comes back.

IE University · SDD/DevOps Assignment 1.

## Features

- **Daily goal at first start:** you choose how many new cards a day you want (5, 10, 20, 30, or your own number from 1 to 100). Change it any time from the dashboard.
- **Level quiz:** 8 multiple-choice questions place you at one of five levels, from Starter to Advanced. Cards below your level are marked as known, so you don't spend time on sentences that are too easy (details below).
- **3,000 real sentences built in:** five difficulty tiers of 600 Tatoeba sentences, from *Tiene un libro.* to *Quizá Tom no quiere que encontremos a María.*
- **Add your own sentences:** Spanish plus English. A grammar note is added automatically when one of 13 rules matches (for example *Hay que + infinitive*), and the sentence's content words are extracted.
- **Automatic flashcards:** each new sentence gets a sentence card, plus a word card for every word that doesn't have one yet.
- **Review:** the card's front is shown first. "Show answer" reveals the translation, the grammar note and the sentence's **key words** (its 3 rarest words), or, for a word card, the word's meaning and up to 3 example sentences. Rate it **Again**, **Hard**, **Good** or **Easy**. The four buttons look the same until you hover over one, so none of them nudges your answer, and "What the buttons do" shows when the card will come back for each rating.
- **Scheduling:** SM-2 by default (intervals of 1 day, 6 days, then growing by the card's ease), or a Leitner box system with `SCHEDULER=leitner`. Overdue cards come first, then new cards up to your daily goal.
- **Dashboard:** cards waiting today with a progress ring, due now, new cards left today, reviewed today, total sentences, your daily goal and your level.
- **Words page:** add your own meaning for any word. It appears on that word's card and next to it in the key words.
- **No JavaScript, light and dark mode, works on phones, keyboard shortcuts** (Alt+S shows the answer, Alt+1 to Alt+4 rate it; Alt+Shift in Firefox).

### The level quiz

The built-in sentences are stored easiest first and cut into five equal bands, one per level. The quiz asks 2 questions from each of the four easier bands. You move up one level for every band, counted from the easiest, where both answers were right.

- **The wrong options are look-alikes,** so recognising one word isn't enough. They share Spanish words with the question and English words with the answer, and they're about the same length. For *¿Qué hora es?* the options are "What time / What year / What day / What month is it?".
- **No ambiguous answers:** a sentence that might mean the same as the question (its words are a subset or superset of the question's) is never used as a wrong option.
- **"I'm not sure" counts as wrong,** so guessing doesn't skip material you don't know.
- **Skipped cards aren't deleted.** They come back once for a quick check, spread over two to six months so they never pile up on one day.
- You can skip the quiz ("Skip, I'm a beginner") or retake it from the dashboard.

## Setup and run

Requires Python 3.10 or newer. Everything runs in one process with one SQLite file. There's no other service to install and no setup step.

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000. The app binds to `0.0.0.0` and runs with `debug=False`. On first start it creates `$DATA_DIR/trainer.db` with all tables and imports the built-in sentences. The first visit asks for a daily goal, then offers the level quiz.

### Environment variables (all optional)

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Server port |
| `DATA_DIR` | `./data` | Folder for `trainer.db` (created if missing) |
| `SCHEDULER` | `sm2` | `sm2` or `leitner`. An unknown value stops the app at startup with a clear error |
| `NEW_CARDS_PER_DAY` | `15` | New-card limit used until the learner chooses a daily goal |

Example: `PORT=9000 DATA_DIR=/tmp/trainer SCHEDULER=leitner python app.py`

To start over, stop the app and delete `$DATA_DIR/trainer.db`; the next start creates a fresh database and imports the sentences again.

## Tests and coverage

```bash
pytest --cov=trainer --cov-report=term-missing
```

251 tests, **100% coverage** of the `trainer` package. Run one file with `pytest tests/test_algorithms.py`, or one test with `pytest tests/test_algorithms.py::test_name`.

- **Pure logic is tested directly:** the scheduling algorithms, tokenizer, grammar rules, seed builder and placement quiz. The algorithms take `today` as a parameter, so tests fix the date.
- **Services use in-memory fakes:** the services are tested with fake repositories (`tests/fakes.py`), and the SQLite repositories are tested separately against a temporary database.
- **Pages are smoke-tested:** the pages, the seed import and the first-start flow (goal, quiz, review) go through Flask's test client.
- **What the coverage number leaves out:** as stated in ADR-4, the route files (`trainer/*/routes.py`) and the seed loader (`trainer/content/seed.py`) are excluded (`.coveragerc`).

## Architecture

```
app.py             entry point: python app.py
trainer/
  __init__.py      create_app(): the composition root that wires everything together
  config.py        environment variables -> Config
  db.py, schema.sql   one SQLite connection and one transaction per request
  content/         sentences, words, tokenizer, grammar rules, level quiz, seed builder and loader (ContentService)
  scheduler/       cards, reviews, SM-2 and Leitner, daily goal, placement (ReviewService)
  templates/, static/   Jinja pages and one CSS file
tests/             one test file per module, plus fakes and shared fixtures
docs/diagrams.md   architecture, sentence-to-cards sequence, and ER diagrams
```

- **Two domains that never import each other.** New sentences reach the scheduler only through an Observer subscription made in `create_app()` (ADR-2). Cards refer to words and sentences by ID only, with no cross-domain foreign keys (ADR-3). The review routes are the only code that uses both facades.
- **Patterns:**
  - Facade: `ContentService`, `ReviewService`.
  - Observer: content notifies the scheduler.
  - Strategy plus a registry: `SM2Strategy`, `LeitnerStrategy`.
  - Repository with dependency inversion: abstract repositories with SQLite implementations.
- **Transactions:** repositories never commit. The request teardown commits if the request succeeded and rolls back if it failed, so a sentence and its cards are saved together or not at all.

Design decisions are recorded in [ADR.md](ADR.md); diagrams are in [docs/diagrams.md](docs/diagrams.md); AI assistance is logged in [AI_USAGE.md](AI_USAGE.md).

## Data

Example sentences come from the [Tatoeba Project](https://tatoeba.org), licensed **CC BY 2.0 FR**, through the Spanish-English export at manythings.org/anki. They are real sentences written by people, not generated by AI. The attribution is stored with every sentence, shown on its page, and credited in every page footer.

**On first start the app imports 3,000 sentences (3,389 words, 6,389 cards) from the committed seed files** in `trainer/content/seed/`. The import runs in one transaction, and only if the database is empty. Measured on a laptop, the first start is ready in **about 1 s** including the import; later starts take about 0.5 s. The app never downloads anything at runtime.

The seed files were built offline, once, from the downloaded export (`raw/` is not committed):

```bash
python -m trainer.content.seed_build raw/spa-eng.zip --per-level 600
```

The builder keeps sentences of 3-12 words without digits, ranks every word by how many sentences use it, and rates each sentence by its rarest word. The names Tom and Mary, which appear in thousands of sentences, don't count as words. It then fills five tiers of 600 sentences, one per quiz level, and lists them easiest first:

| Tier | Rarest word's rank | Min. words | Avg. words | Example |
|---|---|---|---|---|
| Starter | 1-300 | 3 | 3.4 | *Tiene un libro.* |
| Beginner | 301-1,000 | 3 | 3.5 | *Desearía poder nadar.* |
| Elementary | 1,001-2,500 | 4 | 4.4 | *Estaba perdido entre la multitud.* |
| Intermediate | 2,501-5,000 | 6 | 6.9 | *Está escrito con lápiz, así que se puede borrar.* |
| Advanced | 5,001-10,000 | 7 | 8.3 | *Quizá Tom no quiere que encontremos a María.* |

- **Harder tiers need longer sentences,** so they bring harder grammar (subjunctive, conditionals) as well as rarer words.
- **Words past rank 10,000 are left out,** because they're mostly typos and one-off names.
- **Variety:** inside a tier, at most 3 sentences share the same rarest word, so the seed keeps introducing new vocabulary.
- **Spread:** the 600 are spaced evenly across the whole tier rather than taken from its easy end.

## Scope and known limitations

- Spanish only, with English as the base language. One learner, no login.
- Words are not lemmatized, so *hablo* and *hablas* are separate words.
- Grammar rules are deliberately conservative: a missing note is preferred over a wrong one.
- Word meanings start empty and are filled in by the learner. The export has sentence translations, not a dictionary.
- The level quiz only covers the built-in sentences. Retaking it at a lower level doesn't bring skipped cards back early; they still return for their scheduled check.
- No "delete sentence" in v1, because cards refer to content by ID only (ADR-3).
- One process by design (SQLite and per-request transactions); the app should not be run with several worker processes.
