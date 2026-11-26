# Architecture Decision Records
## 1. Flask with stdlib sqlite3
Date: 2026-09-28
Status: Superseded by 7 (SQLite replaced by SQL Server; Flask and hand-written SQL stay)
Context: A small single-user web app with 5 tables.
Decision: Use Flask with Jinja templates, and Python's built-in sqlite3 with hand-written SQL kept in the repository files.
Alternatives considered: FastAPI (async and API features go unused, needs extra packages); Django and SQLAlchemy (too much abstraction for 5 tables, and they hide the SQL).
Consequences: Only 3 dependencies and every query is visible. The cost is writing SQL by hand, but it stays inside the repositories.

## 2. Content and scheduler as separate domains
Date: 2026-09-30
Status: Decided
Context: The review scheduler may later need to scale separately from content authoring, so the two parts should be easy to split apart.
Decision: Keep trainer/content and trainer/scheduler as packages that never import each other. Each has one facade (ContentService, ReviewService), and new sentences reach the scheduler only through an Observer subscription made in create_app().
Alternatives considered: One shared services.py handling both (rejected: content and scheduling code would get tangled and could not be split later).
Consequences: Each domain can change or move on its own; a later split turns the observer into a message broker and facade calls into HTTP. The cost is a little extra wiring in create_app().

## 3. Cross-domain references by ID only
Date: 2026-09-30
Status: Decided
Context: The scheduler's cards table must point at content's words and sentences, but ADR-2 requires the scheduler's tables to be movable to their own database later.
Decision: cards stores word_id and sentence_id as plain IDs with no foreign key. Foreign keys are used only inside each domain, and partial unique indexes allow one card per word or sentence.
Alternatives considered: Foreign keys from cards to words and sentences (rejected: they tie both domains to one database and block a split).
Consequences: The scheduler's tables can move independently. The cost is possible orphaned cards if content were deleted, so v1 has no "delete sentence" feature.

## 4. Test pure logic and services with fakes
Date: 2026-10-02
Status: Decided
Context: The core logic must be checked quickly and repeatably, and scheduling results depend on the date.
Decision: Scheduling strategies are pure and take today as a parameter; services depend on abstract repositories, so their tests use in-memory fakes; the SQLite repositories are tested separately against a temporary database. Routes and seed loading are excluded from the coverage number (.coveragerc) and only smoke-tested.
Alternatives considered: Mainly end-to-end tests through Flask requests (rejected: slower, and a failure is hard to trace to one piece).
Consequences: Fast tests (251 in about 10 s) with 100% coverage of the trainer package. The cost is keeping the fakes in line with the real repositories, and the coverage number openly leaves out the routes.

## 5. No gamification
Date: 2026-10-02
Status: Decided
Context: The target learners plateaued on gamified apps; the goal is long-term retention, not daily engagement.
Decision: No streaks, hearts, points or leaderboards. The dashboard only shows cards due, new cards left today, and reviews done today.
Alternatives considered: Streaks and leaderboards (rejected: they reward opening the app rather than remembering, and punish missed days). Also considered and deferred: user login, multiple languages, a stats dashboard.
Consequences: A simpler app focused on reviewing. The cost is less outside motivation for learners who enjoy game elements.

## 6. Two services over HTTP, with the scheduler pulling new sentences
Date: 2026-11-15
Status: Decided
Context: Assignment 2 splits the monolith at the seam from ADR-2. Content owns sentences and words, the scheduler owns cards and reviews, and each must deploy, scale to zero and fail on its own. The in-process Observer cannot cross a process boundary, and no message broker is allowed.
Decision: Two Flask services, each with its own database and no shared code (migrate.py and the database helpers are copied on purpose). The scheduler calls content's JSON API over HTTP, always with a timeout. New cards are pulled: when the scheduler runs out of new cards it calls GET /sentences/feed?after_id=<highest sentence id it has a card for>. Review text and placement scoring go through the scheduler on the server; the dashboard calls both services from the browser. When content is down, review and placement return a designed 503 JSON error and everything the scheduler owns keeps working.
Alternatives considered: Push, where content calls the scheduler for every new sentence (rejected: content would depend on the scheduler being up, and one failed call loses that card for good). One shared database (rejected: it undoes the split). A shared Python package (rejected: every change would mean redeploying both services).
Consequences: Content does not know the scheduler exists, and a failed pull is simply tried again on the next review. The costs: a new sentence becomes a card only when the scheduler next runs out of new cards (the same order learners saw in Assignment 1); "new left today" can only show the daily allowance; and the two copies of the migration runner must be kept in step by hand.

## 7. SQL Server per service, with versioned migrations run at startup
Date: 2026-11-17
Status: Decided
Context: Each service needs its own database that survives restarts and redeploys, both in a local container and on Azure SQL serverless. The schema must be able to change later without manual steps, and a SQLite file (ADR-1) cannot be shared by containers that scale to zero.
Decision: SQL Server through pymssql with hand-written SQL (no ORM), one database per service, each reached by its own user that exists only in that database and has only the rights its migrations need (db_ddladmin, db_datareader, db_datawriter, REFERENCES). Schema changes are numbered SQL files applied by a small runner (migrate.py) at every startup, forward only: applied versions are recorded in schema_migrations, and each file runs in one transaction with its version row. Startup retries the connection for about 90 s, because a paused serverless database takes time to resume. Local Docker Compose uses clearly labelled local-only passwords that can be overridden from an ignored .env; Azure passwords live only in GitHub secrets.
Alternatives considered: Alembic (rejected: brings SQLAlchemy and hides the SQL that ADR-1 kept visible). CREATE TABLE IF NOT EXISTS at startup as in Assignment 1 (rejected: cannot change an existing table or show what ran). A manual migration step before deploying (rejected: easy to forget, and the app must start with no manual steps).
Consequences: A new database and an existing one reach the same schema the same way, and the log says which migrations ran. The costs: a migration cannot be undone, so a mistake is fixed with a new file; the scheduler's "new left today" now shows what is left of the daily goal, because sentences not pulled yet are not in its database; and resetting one database without the other breaks the card-to-sentence mapping, since no foreign key can cross databases.

## 8. Serverless hosting on Azure, created once by a script and then changed only by the pipeline
Date: 2026-11-25
Status: Decided
Context: The system runs in my own Azure for Students subscription, in one resource group, rg-aalsamara-ieu2024, and in one region from the five that subscription allows. It must cost close to nothing while nobody uses it, and after a one-time setup only the pipeline may change anything. Scaling to zero has a price: the first request after a quiet period starts a container, and that container may find its database paused. Resuming takes up to about a minute, and until then connections fail (error 40613, or a pymssql connection timeout) while Azure answers the browser with 503 "App port is not ready".
Decision: Each service runs as a Container App (Consumption plan, external HTTPS ingress, 0.25 vCPU and 0.5 GiB, minimum 0 and maximum 1 replica) in one environment, aalsamara-ieu2024-env, whose Log Analytics workspace keeps the logs. Each service has its own Azure SQL serverless database on the free offer (General Purpose, Gen5, 0.5 to 1 vCore, locally redundant backups; the offer fixes auto-pause at 60 minutes and the size at 32 GB) on one logical server, aalsamara-ieu2024-sql, and connects as a contained user of its own database with only db_ddladmin, db_datareader, db_datawriter and REFERENCES, the rights the migrations need. The UI is a static website on the storage account aalsamaraieu2024ui, and its address is the only CORS origin. Images live on GHCR as public packages. The pipeline signs in as a user-assigned managed identity, aalsamara-ieu2024-github, with Contributor on the resource group only, through GitHub's OIDC token, so no Azure password exists anywhere. infra/setup.sh creates all of this once; on every deploy the pipeline sets the connection string as a Container Apps secret and updates the image, the environment variables and the replica limits. Startup retries the database for about 90 s (1, 2, 4, 8, 16, 30, 29 s), gunicorn gives a worker 120 s to start, the UI waits 10 s per call and shows "starting up, try again" for Azure's 503, and the post-deploy check polls /health for up to 4 minutes. Migrations run at startup, which is safe only because there is never more than one replica.
Alternatives considered: Bicep or Terraform (rejected for now: one setup script is enough for this handful of resources, and every line of it can be explained; IaC would pay off with several environments). Azure Container Registry (rejected: fixed monthly cost, and GHCR is free). A Static Web App for the UI (rejected: a storage static website is the setup the course asks for and is billed per GB and per request). Keeping one replica always running (rejected: it removes cold starts but bills all the time).
Consequences: Idle, the containers cost nothing, the databases stay inside the free offer's monthly allowance and then pause, and the storage account and the log workspace bill only per GB. The first visit after a quiet period is slow and may need one "try again" while the database resumes. At 100 times the traffic: raise the replica limit, and move migrations out of startup into a single deploy step (or take a lock such as sp_getapplock) so two replicas never migrate at once; keep one replica warm; pool database connections instead of opening one per request; let the scheduler cache content's sentence text; leave the free offer for a database that does not pause and has a wider vCore range; and put a CDN in front of the static website.

## 9. One pipeline: CI gates every push, CD runs only after CI passes on main
Date: 2026-11-19
Status: Decided
Context: Every push must be tested and every merge to main deployed with no manual step, but a deploy must never ship a commit whose checks failed. Three things cannot be proven by the unit tests alone: that the hand-written SQL runs on SQL Server (the unit tests use in-memory fakes), that the two real services agree on their HTTP contract (the scheduler's tests use a fake content client), and that the system behaves as designed when content is down. CI must also never touch Azure SQL, because every connection wakes the database and is billed.
Decision: One GitHub Actions workflow, pipeline.yml, on every push and pull request. CI is three jobs. "test", once per service: ruff, then pytest against a throwaway SQL Server container whose password is generated in the run, failing below 70% coverage and failing (not skipping) if a SQL Server test cannot run. "validate": system.yaml against system.schema.json and both openapi.yaml files against the OpenAPI specification; a unit test in each service also checks that openapi.yaml lists exactly the routes Flask serves. "integration": builds every image, starts the real compose stack, runs the cross-seam tests (the scheduler pulls from content and shows content's text unchanged, quiz answers are scored by content), checks the startup log for "migration applied" and, after a restart, "migrations: nothing to apply", then stops content and checks the designed 503 while the scheduler keeps serving its own data. The CD jobs run only on main and need all three CI jobs, so a deploy always follows green CI on the same commit.
Alternatives considered: Separate CI and CD workflows linked by workflow_run (rejected: harder to see that CD deployed the commit CI tested). A stub in place of content for the cross-seam test (rejected: it would only check the scheduler against my own picture of content's API, which the fake client in the unit tests already does). Running the SQL tests against SQLite (rejected: the dialect differs, and SQL Server is what runs in production).
Consequences: One run shows whether lint, tests, coverage, the contracts and the partial-failure behaviour all hold. Deliberately not tested: the UI's JavaScript (checked by hand in the browser), Azure itself (the post-deploy health check covers the deployment), load, and cold-start timing. The cost is a slower run, a few minutes, mostly starting SQL Server in two jobs.