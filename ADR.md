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