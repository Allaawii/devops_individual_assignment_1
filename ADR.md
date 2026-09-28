# Architecture Decision Records
## 1. Flask with stdlib sqlite3
Date: 28/9/2026
Status: Decided
Context: A small single-user web app with 5 tables.
Decision: Use Flask with Jinja templates, and Python's built-in sqlite3 with hand-written SQL kept in the repository files.
Alternatives considered: FastAPI (async and API features go unused, needs extra packages); Django and SQLAlchemy (too much abstraction for 5 tables, and they hide the SQL).
Consequences: Only 3 dependencies and every query is visible. The cost is writing SQL by hand, but it stays inside the repositories.