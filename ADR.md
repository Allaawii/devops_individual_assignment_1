# Architecture Decision Records
## 1. Flask with stdlib sqlite3
Date: 2026-09-28
Status: Decided
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