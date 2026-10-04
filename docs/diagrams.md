# Diagrams

## Architecture

One Flask process and one SQLite file. The two domains never import each other: `create_app()`
(the composition root) builds both facades and subscribes the scheduler to new sentences (ADR-2).
The review routes are the only code that calls both facades: `ReviewService` picks the card by ID,
then `ContentService` supplies the text to show.

```mermaid
flowchart TB
    browser["Browser<br/>(Jinja pages, one CSS file, no JavaScript)"]

    subgraph process["One process: python app.py"]
        root["create_app()<br/>composition root"]

        subgraph content["trainer/content"]
            content_routes["content routes<br/>/sentences, /words"]
            content_service["ContentService<br/>Facade + Observer subject"]
            helpers["tokenizer · grammar_rules · placement<br/>(pure functions)"]
            content_repos["SentenceRepository<br/>WordRepository"]
        end

        subgraph scheduler["trainer/scheduler"]
            review_routes["review routes<br/>/, /goal, /placement, /review"]
            review_service["ReviewService<br/>Facade + Observer listener"]
            strategy["SchedulingStrategy<br/>SM2Strategy or LeitnerStrategy"]
            scheduler_repos["CardRepository · ReviewLog<br/>SettingsStore"]
        end

        db["db.py<br/>one connection and one transaction per request"]
    end

    sqlite[("SQLite<br/>$DATA_DIR/trainer.db")]
    seed[/"seed/sentences.tsv, words.tsv<br/>(3,000 Tatoeba sentences)"/]

    browser -->|HTTP| content_routes
    browser -->|HTTP| review_routes
    content_routes --> content_service
    review_routes --> review_service
    review_routes -.->|"card text by ID"| content_service
    content_service --> helpers
    content_service --> content_repos
    content_service -.->|"on_sentence_added(sentence_id, word_ids)"| review_service
    review_service --> strategy
    review_service --> scheduler_repos
    content_repos --> db
    scheduler_repos --> db
    db --> sqlite
    root -.->|"builds, wires, subscribes"| content_service
    root -.->|"builds, picks strategy from SCHEDULER"| review_service
    seed -->|"first start, only if the database is empty"| root
```

Solid arrows are calls. Dashed arrows are the wiring done once at startup, the Observer
notification, and the one place where a route reads from the other domain.

## Adding a sentence: from the form to the new cards

```mermaid
sequenceDiagram
    participant B as Browser
    participant R as content route
    participant C as ContentService
    participant W as WordRepository
    participant S as ReviewService
    participant K as CardRepository
    participant D as db.py teardown

    B->>R: POST /sentences/new
    R->>C: add_sentence(spanish, english, note)
    C->>C: validate, tag_grammar(), extract_words()
    C->>W: get_or_create(word) and link(sentence, word)
    C->>S: on_sentence_added(sentence_id, word_ids)
    S->>K: ensure_sentence_card(), ensure_word_cards()
    R-->>B: 302 redirect to /sentences/<id>
    D->>D: commit (or roll back if anything raised)
```

## Entity-relationship diagram

Solid lines are real foreign keys, which exist only inside a domain.
Dashed lines are plain ID references across the domain boundary, with no foreign key (see ADR-3).

```mermaid
erDiagram
    SENTENCES ||--o{ SENTENCE_WORDS : "contains"
    WORDS     ||--o{ SENTENCE_WORDS : "appears in"
    SENTENCES ||..o| CARDS : "sentence_id (ID only, no FK)"
    WORDS     ||..o| CARDS : "word_id (ID only, no FK)"
    CARDS     ||--o{ REVIEWS : "reviewed as"

    SENTENCES {
        int  id PK
        text spanish_text UK
        text english_text
        text grammar_note "nullable"
        text source "'user' or Tatoeba attribution"
        text created_at "ISO-8601"
    }
    WORDS {
        int  id PK
        text headword UK "lowercase"
        text meaning "nullable until the learner fills it in"
        int  frequency_rank "nullable; from the seed build"
    }
    SENTENCE_WORDS {
        int sentence_id PK, FK
        int word_id PK, FK
    }
    CARDS {
        int  id PK "id order = introduction order"
        text card_type "'word' or 'sentence'"
        int  word_id "partial unique index"
        int  sentence_id "partial unique index"
        real ease_factor "default 2.5"
        int  interval_days "default 0"
        int  repetitions "SM-2 streak or Leitner box"
        text due_date "NULL = new card"
    }
    REVIEWS {
        int  id PK
        int  card_id FK
        text reviewed_at
        int  quality "0-5"
        int  resulting_interval
        real resulting_ease
    }
    SETTINGS {
        text key PK "'new_cards_per_day' or 'level'"
        text value
    }
```

The content domain owns `sentences`, `words` and `sentence_words`.
The scheduler domain owns `cards`, `reviews` and `settings` (the learner's daily goal and quiz level).
