-- Content service schema, version 1.
-- Applied once by migrate.py and recorded in schema_migrations. Never edit this file after it
-- has run anywhere: put every change in a new, higher-numbered file instead.

-- Spanish text and headwords are compared accent- and case-sensitively (CS_AS), so "si" and
-- "sí", or "Él" and "él", stay different, as they were in SQLite in Assignment 1.
CREATE TABLE sentences (
    id            INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_sentences PRIMARY KEY,
    spanish_text  NVARCHAR(500) COLLATE Latin1_General_100_CS_AS NOT NULL
                  CONSTRAINT ux_sentences_spanish_text UNIQUE,
    english_text  NVARCHAR(500)  NOT NULL,
    grammar_note  NVARCHAR(1000) NULL,         -- typed by the learner, or from grammar_rules
    source        NVARCHAR(200)  NOT NULL,     -- 'user' or the Tatoeba attribution
    created_at    DATETIME2(0)   NOT NULL
);

CREATE TABLE words (
    id              INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_words PRIMARY KEY,
    headword        NVARCHAR(500) COLLATE Latin1_General_100_CS_AS NOT NULL   -- lowercase surface form
                    CONSTRAINT ux_words_headword UNIQUE,
    meaning         NVARCHAR(500) NULL,        -- NULL until the learner fills it in
    frequency_rank  INT NULL                   -- from the seed build; NULL for words only in user sentences
);

CREATE TABLE sentence_words (
    sentence_id  INT NOT NULL CONSTRAINT fk_sentence_words_sentence REFERENCES sentences (id) ON DELETE CASCADE,
    word_id      INT NOT NULL CONSTRAINT fk_sentence_words_word REFERENCES words (id) ON DELETE CASCADE,
    CONSTRAINT pk_sentence_words PRIMARY KEY (sentence_id, word_id)
);

-- One row that /health updates, to prove the database accepts writes and not only reads.
CREATE TABLE health_check (
    id          INT NOT NULL CONSTRAINT pk_health_check PRIMARY KEY,
    checked_at  DATETIME2(0) NULL
);
GO

-- Example sentences for a word card look sentences up by word.
CREATE INDEX ix_sentence_words_word ON sentence_words (word_id);

INSERT INTO health_check (id, checked_at) VALUES (1, NULL);
