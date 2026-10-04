PRAGMA foreign_keys = ON;

-- ===== content domain =====
CREATE TABLE IF NOT EXISTS sentences (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  spanish_text  TEXT NOT NULL UNIQUE,
  english_text  TEXT NOT NULL,
  grammar_note  TEXT,                               -- manual, or from grammar_rules
  source        TEXT NOT NULL,                      -- 'user' or the Tatoeba attribution string
  created_at    TEXT NOT NULL                       -- ISO-8601
);

CREATE TABLE IF NOT EXISTS words (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  headword        TEXT NOT NULL UNIQUE,             -- lowercase surface form
  meaning         TEXT,                             -- NULL until the learner fills it in
  frequency_rank  INTEGER                           -- from seed build; NULL for user-only words
);

CREATE TABLE IF NOT EXISTS sentence_words (
  sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
  word_id     INTEGER NOT NULL REFERENCES words(id)     ON DELETE CASCADE,
  PRIMARY KEY (sentence_id, word_id)
);

-- ===== scheduler domain =====
CREATE TABLE IF NOT EXISTS cards (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,  -- id order = introduction order
  card_type     TEXT NOT NULL CHECK (card_type IN ('word', 'sentence')),
  word_id       INTEGER,        -- ID reference into content: deliberately NO foreign key
  sentence_id   INTEGER,        -- same
  ease_factor   REAL    NOT NULL DEFAULT 2.5,
  interval_days INTEGER NOT NULL DEFAULT 0,
  repetitions   INTEGER NOT NULL DEFAULT 0,         -- SM-2 streak; Leitner box number
  due_date      TEXT,                               -- NULL = new, never reviewed
  CHECK ( (card_type = 'word'     AND word_id IS NOT NULL AND sentence_id IS NULL)
       OR (card_type = 'sentence' AND sentence_id IS NOT NULL AND word_id IS NULL) )
);

-- Partial unique indexes, because UNIQUE(word_id) would still allow many NULLs in SQLite
CREATE UNIQUE INDEX IF NOT EXISTS ux_cards_word     ON cards(word_id)     WHERE word_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_cards_sentence ON cards(sentence_id) WHERE sentence_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_cards_due ON cards(due_date);

CREATE TABLE IF NOT EXISTS reviews (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id            INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
  reviewed_at        TEXT    NOT NULL,
  quality            INTEGER NOT NULL CHECK (quality BETWEEN 0 AND 5),
  resulting_interval INTEGER NOT NULL,
  resulting_ease     REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_reviews_card ON reviews(card_id);

-- Learner preferences, e.g. the daily goal chosen at first start
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
