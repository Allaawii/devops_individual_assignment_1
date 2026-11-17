-- Scheduler service schema, version 1.
-- Applied once by migrate.py and recorded in schema_migrations. Never edit this file after it
-- has run anywhere: put every change in a new, higher-numbered file instead.

-- word_id and sentence_id are ids in the content service's database. A foreign key cannot
-- cross databases, so there is none (ADR-3); content never deletes, so the ids stay valid.
CREATE TABLE cards (
    id             INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_cards PRIMARY KEY,   -- id order = introduction order
    card_type      NVARCHAR(10) NOT NULL CONSTRAINT ck_cards_type CHECK (card_type IN (N'word', N'sentence')),
    word_id        INT NULL,
    sentence_id    INT NULL,
    ease_factor    FLOAT NOT NULL CONSTRAINT df_cards_ease DEFAULT 2.5,
    interval_days  INT   NOT NULL CONSTRAINT df_cards_interval DEFAULT 0,
    repetitions    INT   NOT NULL CONSTRAINT df_cards_repetitions DEFAULT 0,   -- SM-2 streak; Leitner box
    due_date       DATE  NULL,                                                 -- NULL = new, never reviewed
    CONSTRAINT ck_cards_one_target CHECK (
        (card_type = N'word' AND word_id IS NOT NULL AND sentence_id IS NULL)
        OR (card_type = N'sentence' AND sentence_id IS NOT NULL AND word_id IS NULL))
);

CREATE TABLE reviews (
    id                  INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_reviews PRIMARY KEY,
    card_id             INT NOT NULL CONSTRAINT fk_reviews_card REFERENCES cards (id) ON DELETE CASCADE,
    reviewed_at         DATETIME2(0) NOT NULL,
    quality             TINYINT NOT NULL CONSTRAINT ck_reviews_quality CHECK (quality BETWEEN 0 AND 5),
    resulting_interval  INT   NOT NULL,
    resulting_ease      FLOAT NOT NULL
);

-- Learner preferences: the daily goal and the placement level. "key" is a reserved word in T-SQL.
CREATE TABLE settings (
    setting_key    NVARCHAR(50)  NOT NULL CONSTRAINT pk_settings PRIMARY KEY,
    setting_value  NVARCHAR(200) NOT NULL
);

-- One row that /health updates, to prove the database accepts writes and not only reads.
CREATE TABLE health_check (
    id          INT NOT NULL CONSTRAINT pk_health_check PRIMARY KEY,
    checked_at  DATETIME2(0) NULL
);
GO

-- Filtered unique indexes: one card per word and per sentence. A plain UNIQUE constraint
-- would also allow only one NULL, and every word card has a NULL sentence_id.
CREATE UNIQUE INDEX ux_cards_word ON cards (word_id) WHERE word_id IS NOT NULL;
CREATE UNIQUE INDEX ux_cards_sentence ON cards (sentence_id) WHERE sentence_id IS NOT NULL;
CREATE INDEX ix_cards_due ON cards (due_date);
CREATE INDEX ix_reviews_card ON reviews (card_id);
CREATE INDEX ix_reviews_reviewed_at ON reviews (reviewed_at);

INSERT INTO health_check (id, checked_at) VALUES (1, NULL);
