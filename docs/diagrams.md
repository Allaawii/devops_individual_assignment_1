# Diagrams

## Before: the Assignment 1 monolith

One Flask process and one SQLite file. The two domains lived in one codebase and never imported each other: `create_app()` wired them together, and new sentences reached the scheduler through an in-process Observer call.

```mermaid
flowchart TB
    browser["Browser<br/>(server-rendered Jinja pages)"]

    subgraph process["One process: python app.py"]
        root["create_app()<br/>composition root"]
        content_service["ContentService<br/>(sentences, words, quiz)"]
        review_service["ReviewService<br/>(cards, reviews, goal)"]
        db["db.py<br/>one connection per request"]
    end

    sqlite[("One SQLite file<br/>all six tables")]

    browser -->|HTTP| process
    root -.->|"builds and subscribes"| content_service
    root -.-> review_service
    content_service -.->|"Observer: on_sentence_added()"| review_service
    content_service --> db
    review_service --> db
    db --> sqlite
```

## After: two services, two databases, a static UI

Each service has its own code, image, migrations and database. The only connection between them is HTTP: the scheduler calls 4 content endpoints, each with a timeout. Content never calls the scheduler.

```mermaid
flowchart TB
    browser["Browser"]
    ui["UI: static HTML, CSS, JS<br/>config.js = the two service URLs"]

    subgraph content_svc["content service"]
        content_api["JSON API<br/>/sentences, /sentences/feed, /words,<br/>/placement/quiz, /placement/score, /health"]
        content_service["ContentService<br/>tokenizer, grammar rules, placement"]
    end

    subgraph scheduler_svc["scheduler service"]
        scheduler_api["JSON API<br/>/review/next, /review/{id}, /goal,<br/>/placement, /stats, /health"]
        review_service["ReviewService<br/>SM-2 or Leitner"]
        client["HttpContentClient<br/>2 s timeout, no retries"]
    end

    content_db[("content database<br/>sentences, words, sentence_words")]
    scheduler_db[("scheduler database<br/>cards, reviews, settings")]

    browser --> ui
    ui -->|"fetch + CORS"| content_api
    ui -->|"fetch + CORS"| scheduler_api
    content_api --> content_service --> content_db
    scheduler_api --> review_service --> scheduler_db
    review_service --> client
    client -->|"GET /sentences/feed, GET /sentences/{id},<br/>GET /words/{id}, POST /placement/score"| content_api
```

## Deployment

Everything on the right lives in one resource group, `rg-aalsamara-ieu2024` (Azure for Students, France Central). The pipeline signs in as the managed identity `aalsamara-ieu2024-github` through OIDC; that identity is Contributor on this resource group only.

```mermaid
flowchart LR
    push["merge to main"] --> ci["CI jobs<br/>test x2, validate,<br/>integration"]
    ci --> images["images<br/>build, tag with SHA"]
    images --> ghcr[("GHCR<br/>frase-content:SHA<br/>frase-scheduler:SHA")]
    images --> deploy["deploy<br/>(OIDC sign-in)"]
    deploy --> ui_job["ui<br/>config.js + upload"]
    deploy --> smoke["smoke<br/>/health x2"]

    subgraph rg["rg-aalsamara-ieu2024"]
        storage["Storage static website<br/>aalsamaraieu2024ui"]
        subgraph env["Container Apps env"]
            content_app["aalsamara-ieu2024-content<br/>0-1 replicas"]
            scheduler_app["aalsamara-ieu2024-scheduler<br/>0-1 replicas"]
        end
        subgraph sql["SQL server aalsamara-ieu2024-sql"]
            content_db[("content-db<br/>serverless, free offer")]
            scheduler_db[("scheduler-db<br/>serverless, free offer")]
        end
        logs["Log Analytics<br/>request log lines"]
    end

    deploy -->|"update image to :SHA"| content_app
    deploy -->|"update image to :SHA"| scheduler_app
    ghcr -.->|pull| env
    ui_job -->|"upload ui/"| storage
    scheduler_app -->|CONTENT_URL| content_app
    content_app -->|content_svc| content_db
    scheduler_app -->|scheduler_svc| scheduler_db
    env -.-> logs
```

## The pull: how the scheduler gets new cards

```mermaid
sequenceDiagram
    participant U as UI
    participant S as scheduler
    participant SD as scheduler database
    participant C as content
    participant CD as content database

    U->>S: GET /review/next
    S->>SD: a due card? a new card left today?
    SD-->>S: no new card stored
    S->>SD: newest sentence id that has a card (max_sentence_id)
    S->>C: GET /sentences/feed?after_id=<that id>&limit=20 (2 s timeout)
    C->>CD: next 20 sentences in id order, with their word ids
    C-->>S: [{id, word_ids}, ...]
    S->>SD: a sentence card plus a card per new word (unique indexes skip words that already have one)
    S->>C: GET /sentences/{id} (the text to show)
    C-->>S: sentence, words, key words
    S-->>U: 200 card, text, rating previews, today's numbers
```

## When content is down

```mermaid
sequenceDiagram
    participant U as UI
    participant S as scheduler
    participant C as content (stopped)

    U->>S: GET /review/next
    S->>C: GET /sentences/{id} (2 s timeout, tried once)
    C--xS: connection refused or timeout
    S-->>U: 503 {"error": "content_unavailable", "message": ...}
    Note over U: shows the message and a "Try again" button
    U->>S: GET /stats
    S-->>U: 200 (the scheduler's own data still works)
```

## One database per service

Solid lines are real foreign keys, which exist only inside one database. Dashed lines are plain IDs that point into the other service's database, with no foreign key possible (ADR-3, ADR-7). Content never deletes sentences or words, so those IDs stay valid.

```mermaid
erDiagram
    SENTENCES ||--o{ SENTENCE_WORDS : "contains"
    WORDS     ||--o{ SENTENCE_WORDS : "appears in"
    SENTENCES ||..o| CARDS : "sentence_id (ID only, other database)"
    WORDS     ||..o| CARDS : "word_id (ID only, other database)"
    CARDS     ||--o{ REVIEWS : "reviewed as"

    SENTENCES {
        int      id PK
        nvarchar spanish_text UK "accent- and case-sensitive"
        nvarchar english_text
        nvarchar grammar_note "nullable"
        nvarchar source "'user' or Tatoeba attribution"
        datetime2 created_at
        tinyint  level "0-4, added by migration 002; NULL for the learner's own"
    }
    WORDS {
        int      id PK
        nvarchar headword UK "lowercase"
        nvarchar meaning "nullable until the learner fills it in"
        int      frequency_rank "nullable; from the seed build"
    }
    SENTENCE_WORDS {
        int sentence_id PK, FK
        int word_id PK, FK
    }
    CARDS {
        int      id PK "id order = introduction order"
        nvarchar card_type "'word' or 'sentence'"
        int      word_id "filtered unique index"
        int      sentence_id "filtered unique index"
        float    ease_factor "default 2.5"
        int      interval_days "default 0"
        int      repetitions "SM-2 streak or Leitner box"
        date     due_date "NULL = new card"
    }
    REVIEWS {
        int       id PK
        int       card_id FK
        datetime2 reviewed_at
        tinyint   quality "0-5"
        int       resulting_interval
        float     resulting_ease
    }
    SETTINGS {
        nvarchar setting_key PK "'new_cards_per_day', 'level', 'level_name'"
        nvarchar setting_value
    }
```

The content database (`sentences`, `words`, `sentence_words`) belongs to the content service, and the scheduler database (`cards`, `reviews`, `settings`) to the scheduler. Each database also has `schema_migrations` (which migrations ran) and `health_check` (one row that `/health` writes to).
