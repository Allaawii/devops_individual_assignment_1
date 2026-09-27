# Diagrams

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
```

The content domain owns `sentences`, `words` and `sentence_words`.
The scheduler domain owns `cards` and `reviews`.
