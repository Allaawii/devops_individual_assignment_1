# Frase: a contextual Spanish spaced-repetition trainer

*Frase* is Spanish for "sentence". It's a web app for learning Spanish from real sentences, not isolated word lists. Every sentence becomes flashcards (one for the sentence and one for each new word), and a spaced-repetition algorithm decides when each card comes back.

IE University · SDD/DevOps. Assignment 1 built it as one Flask process with SQLite. Assignment 2 splits it into two services with their own SQL Server databases, runs them in containers, and deploys them to Azure through GitHub Actions.

**Live:** https://aalsamaraieu2024ui.z28.web.core.windows.net

The services scale to zero and the databases pause after an hour without use. The first request after a quiet period can take up to about a minute while both wake up; the UI says "The service is starting up" until then.

## Features

- **Daily goal at first start:** you choose how many new cards a day you want (5, 10, 20, 30, or your own number from 1 to 100). Change it any time from the dashboard.
- **Level quiz:** 8 multiple-choice questions place you at one of five levels, from Starter to Advanced. Cards below your level are marked as known, so you don't spend time on sentences that are too easy.
- **3,000 real sentences built in:** five difficulty levels of 600 Tatoeba sentences, from *Tiene un libro.* to *Quizá Tom no quiere que encontremos a María.* Each sentence stores its level, shown on the Sentences page.
- **Add your own sentences:** Spanish plus English. A grammar note is added automatically when one of 13 rules matches (for example *Hay que + infinitive*), and the sentence's content words are extracted.
- **Review:** the front first, then the translation, grammar note and the sentence's 3 rarest words (or, for a word card, its meaning and up to 3 example sentences). Rate it **Again**, **Hard**, **Good** or **Easy**; "What the buttons do" shows when the card will come back for each rating.
- **Scheduling:** SM-2 by default, or a Leitner box system with `SCHEDULER=leitner`. Overdue cards come first, then new cards up to your daily goal.
- **Words page:** add your own meaning for any word. It appears on that word's card and in the key words.
- **Light and dark mode, works on phones.** No emojis, no build step: plain HTML, CSS and JavaScript modules.

## Architecture

```
services/
  content/      sentences, words, tokenizer, grammar rules, level quiz, seed (port 8001 locally)
  scheduler/    cards, reviews, SM-2 and Leitner, daily goal, placement result (port 8002 locally)
ui/             static pages; config.js says where the two services are
db/init.sql     local only: creates both databases and one user per service
docker-compose.yml   SQL Server + both services + the UI, for running everything locally
infra/setup.sh  the one-time Azure setup (run by hand once; see below)
.github/workflows/pipeline.yml   CI on every push and pull request, CD on main
tests/integration/   tests across the two services, run against the compose stack
system.yaml     both services, their environment variables and the calls between them
docs/diagrams.md     before and after architecture, deployment, sequences, one database per service
```

- **Two services that share no code.** Each has its own `requirements.txt`, Dockerfile, migrations, tests and `openapi.yaml`. `migrate.py` and the database helpers are copied on purpose, so neither service can break the other (ADR-6).
- **Each service owns its database.** Content owns `sentences`, `words` and `sentence_words`; the scheduler owns `cards`, `reviews` and `settings`. Cards refer to sentences and words by ID only; no query or foreign key crosses the two databases (ADR-3, ADR-7).
- **The scheduler pulls new sentences.** When it runs out of new cards it calls content's `GET /sentences/feed?after_id=<newest sentence it has a card for>&limit=20` and creates a sentence card plus one card per new word. Content never calls the scheduler.
- **The scheduler calls 4 content endpoints:** the feed, `GET /sentences/{id}` and `GET /words/{id}` for the text of a card, and `POST /placement/score` for the quiz. Every call has a 2-second timeout (5 seconds for scoring) and is tried once. If content does not answer, the scheduler returns a designed `503 {"error": "content_unavailable", ...}`, and everything it can do alone (dashboard numbers, daily goal) keeps working.
- **The UI calls both services directly** (no API gateway, ADR-10). Each service allows exactly one CORS origin, the UI's address.
- **Every service starts the same way:** connect to the database (retrying for up to 90 s while a paused database resumes), apply any new migrations, seed an empty content database, then serve. There is no manual setup step.
- **Patterns kept from Assignment 1:** Facade (`ContentService`, `ReviewService`), Strategy (`SM2Strategy`, `LeitnerStrategy`), Repository with in-memory fakes for tests, one connection and one transaction per request.

Design decisions are in [ADR.md](ADR.md), diagrams in [docs/diagrams.md](docs/diagrams.md), AI assistance in [AI_USAGE.md](AI_USAGE.md), and the API contracts in `services/*/openapi.yaml`.

## Run everything locally

Requires Docker Desktop.

```bash
docker compose up --build
```

Open http://localhost:8080. Compose starts SQL Server, runs `db/init.sql` to create the `content` and `scheduler` databases and their users, then starts content on port 8001, the scheduler on 8002 and the UI on 8080. On its first start content applies its migrations and imports the 3,000 seed sentences. `docker compose down` stops everything and keeps the data in the `sqlserver-data` volume; `docker compose down -v` deletes it too.

The passwords in `docker-compose.yml` are local-only defaults (for example `LocalDevOnly_Content1`). To use your own, put `MSSQL_SA_PASSWORD`, `CONTENT_DB_PASSWORD` and `SCHEDULER_DB_PASSWORD` in a `.env` file next to it; `.env` is ignored by git. SQL Server's port is not published, so only the containers can reach it.

### Run one service on its own

Each service only needs a SQL Server database it can reach:

```bash
cd services/content
python -m venv .venv && .venv/Scripts/activate      # Windows; source .venv/bin/activate elsewhere
pip install -r requirements-dev.txt
DATABASE_URL=mssql://content_svc:<password>@localhost:1433/content python app.py
```

The scheduler is the same from `services/scheduler`, plus `CONTENT_URL` pointing at a running content service. Without content, it still starts and answers `/health`, `/stats` and `/goal`; review and placement return the 503.

### Environment variables

| Variable | Service | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | both | none (required, secret) | `mssql://user:password@host:1433/database` |
| `PORT` | both | `8000` | Port the service listens on |
| `CORS_ORIGIN` | both | `http://localhost:8080` | The one origin allowed to call it from a browser |
| `GIT_SHA` | both | `dev` | Version shown by `/health` (the pipeline sets the commit SHA) |
| `DB_RETRY_SECONDS` | both | `90` | How long startup keeps trying to reach the database |
| `CONTENT_URL` | scheduler | `http://content:8000` | Where the content service is |
| `CONTENT_TIMEOUT_S` | scheduler | `2.0` | Longest wait for one call to content |
| `SCHEDULER` | scheduler | `sm2` | `sm2` or `leitner` |
| `NEW_CARDS_PER_DAY` | scheduler | `15` | Daily goal until the learner picks one |

## Tests and coverage

Inside a service folder:

```bash
pip install -r requirements-dev.txt
ruff check .
pytest --cov
```

The tests that need SQL Server (repositories, migrations, startup) skip unless `TEST_DATABASE_URL` points at one, for example `mssql://sa:<password>@localhost:1433/master` with a local SQL Server container. CI always runs them against a real SQL Server and fails if any is skipped (`REQUIRE_SQL_TESTS`). In CI: **content 209 tests, scheduler 155 tests, both 99% coverage** (the pipeline fails below 70%).

- **Pure logic** (scheduling algorithms, tokenizer, grammar rules, placement quiz, seed builder) is tested directly; the algorithms take `today` as a parameter.
- **Services and routes** use in-memory fake repositories, and the scheduler uses a fake content client, so these tests need no database or network.
- **SQL Server tests** cover every repository, the migration runner (including that a failed migration leaves nothing behind, and that migration 002 backfills existing rows correctly) and a full first start with the real seed.
- **`test_openapi.py`** fails if a Flask route is missing from the service's `openapi.yaml`.
- **Integration tests** (`tests/integration/`) run against the whole compose stack: 7 cross-service tests (the pull, review, placement, CORS) and 4 with content stopped (the 503, and that the scheduler's own endpoints still work).

## Database migrations

Each service keeps numbered SQL files in `migrations/` (`001_init.sql`, `002_add_sentence_level.sql`, ...). At startup `migrate.py` applies the ones not yet listed in the `schema_migrations` table, in name order, each in one transaction together with its row in that table, and logs `migration applied: <name>` (or `migrations: nothing to apply`). Files are never edited once applied; a fix is a new file. The recovery plan for a bad migration is in ADR-7.

`002_add_sentence_level.sql` changes data: it adds `sentences.level` and fills it for every existing seed sentence from its position in id order (600 per level for the 3,000 seed sentences). The learner's own sentences keep `NULL`. It was deployed to the live Azure database after the seed had been imported there.

## CI/CD

One workflow, [.github/workflows/pipeline.yml](.github/workflows/pipeline.yml):

| Job | Runs on | What it does |
|---|---|---|
| `test` (once per service) | every push and pull request | ruff, then pytest with coverage against a SQL Server container whose password is generated for the run |
| `validate` | every push and pull request | both `openapi.yaml` files, and `system.yaml` against `system.schema.json` |
| `integration` | every push and pull request | builds both images, starts the compose stack, runs the integration tests, checks the migration log lines and the restart, stops content and checks the 503 |
| `images` | push to `main`, after the 3 jobs above pass | builds both images and pushes them to GHCR tagged with the commit SHA (and `latest`) |
| `deploy` | after `images` | signs in to Azure as a managed identity through OIDC (no stored Azure password), stores each `DATABASE_URL` as a Container Apps secret and deploys the SHA-tagged images |
| `ui` | after `deploy` | writes `config.js` with the two service URLs and uploads `ui/` to the storage static website |
| `smoke` | after `deploy` | calls both `/health` endpoints every 10 s for up to 4 minutes and fails the run if either is not 200 |

Nothing reaches Azure unless CI passed on the same commit. `/health` returns `{"status": "ok", "db": "ok", "version": "<commit SHA>"}`, so the deployed version can be checked against the commit. Every request is logged as one line with method, path, status and duration (`az containerapp logs show --name aalsamara-ieu2024-content --resource-group rg-aalsamara-ieu2024`).

## Azure

| Resource | Name |
|---|---|
| Resource group (my Azure for Students subscription, France Central) | `rg-aalsamara-ieu2024` |
| Container Apps environment (with its Log Analytics workspace) | `aalsamara-ieu2024-env` |
| Container Apps, 0 to 1 replicas each | `aalsamara-ieu2024-content`, `aalsamara-ieu2024-scheduler` |
| SQL server and two serverless databases (free offer) | `aalsamara-ieu2024-sql`: `aalsamara-ieu2024-content-db`, `aalsamara-ieu2024-scheduler-db` |
| Storage account with static website hosting (the UI) | `aalsamaraieu2024ui` |
| Managed identity the pipeline signs in as | `aalsamara-ieu2024-github` |

Cost: the databases use the free offer, which pauses them when the monthly free amount runs out instead of billing (`--free-limit-exhaustion-behavior AutoPause`), and pauses them after 60 minutes without use. The Container Apps scale to zero when idle.

### One-time setup

Done once, before the first deploy; after that only the pipeline changes anything. `infra/setup.sh` does all of it and can be run again safely (it skips whatever already exists). From a shell with the Azure CLI, GitHub CLI and `sqlcmd`, signed in to both (`az login`, `gh auth login`):

```bash
LOCATION=francecentral bash infra/setup.sh
```

It asks for three passwords without showing them (the SQL admin's and one per service user) and never prints them. The steps, numbered as in the course's deployment guide and in the script's output:

1. Shows the subscription and checks that `LOCATION` is one of the regions it allows.
2. Registers the resource providers and creates the resource group `rg-aalsamara-ieu2024`.
3. Creates the storage account and turns on static website hosting for the UI.
4. Creates the SQL server and the two serverless databases on the free offer, and lets Azure services through its firewall. Then, through a temporary firewall rule for this machine that is removed at the end, it creates a contained user per database (`content_svc`, `scheduler_svc`) with only `db_ddladmin`, `db_datareader`, `db_datawriter` and `REFERENCES`: enough to run that service's migrations, and nothing on the other database.
5. Creates the Container Apps environment and both apps (0 to 1 replicas, external ingress on port 8000) with a placeholder image.
6. Creates the managed identity, gives it Contributor on the resource group only, and adds federated credentials so GitHub Actions runs on `main` can sign in as it.
7. Stores the GitHub secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `CONTENT_DB_PASSWORD`, `SCHEDULER_DB_PASSWORD`) and variables (`PREFIX`, `RESOURCE_GROUP`, `UI_STORAGE`) with `gh`.
8. (The first deploy is the pipeline's job, not the script's.)
9. Gives the course professors Reader on the resource group.

Then a push to `main` deploys everything.

## Data

Example sentences come from the [Tatoeba Project](https://tatoeba.org), licensed **CC BY 2.0 FR**, through the Spanish-English export at manythings.org/anki. They are real sentences written by people. The attribution is stored with every sentence and shown on its page.

The seed files in `services/content/seed/` were built offline, once, from the downloaded export (`raw/` is not committed):

```bash
cd services/content
python -m content.seed_build ../../raw/spa-eng.zip --per-level 600
```

The builder keeps sentences of 3-12 words without digits, ranks every word by how many sentences use it, and rates each sentence by its rarest word (Tom and Mary don't count). It fills five levels of 600 sentences and lists them easiest first, which is the order the levels come from:

| Level | Rarest word's rank | Example |
|---|---|---|
| Starter | 1-300 | *Tiene un libro.* |
| Beginner | 301-1,000 | *Desearía poder nadar.* |
| Elementary | 1,001-2,500 | *Estaba perdido entre la multitud.* |
| Intermediate | 2,501-5,000 | *Está escrito con lápiz, así que se puede borrar.* |
| Advanced | 5,001-10,000 | *Quizá Tom no quiere que encontremos a María.* |

## Scope and known limitations

- Spanish only, with English as the base language. One learner, no login: anyone with the URL uses the same cards.
- Words are not lemmatized, so *hablo* and *hablas* are separate words.
- No "delete sentence", because cards in the other database refer to sentences by ID (ADR-3).
- Resetting one database without the other breaks the card-to-sentence mapping; reset both together.
- The first request after an idle hour is slow (cold start plus database resume), by design, to keep the cost at zero.
