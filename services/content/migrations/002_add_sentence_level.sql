-- Content service schema, version 2: store each seed sentence's difficulty level.
-- Applied once by migrate.py, in one transaction together with its row in schema_migrations.
-- Never edit this file after it has run anywhere: put every change in a new, higher-numbered file.
--
-- Until now the placement quiz cut the seed into five equal bands in Python on every request,
-- relying on id order being easiest first. This migration stores the band as a column, so the
-- level is data that the API returns and the quiz reads.
--
-- 0 = Starter, 1 = Beginner, 2 = Elementary, 3 = Intermediate, 4 = Advanced.
-- Sentences the learner typed in (source = 'user') have no level and stay NULL.

ALTER TABLE sentences ADD level TINYINT NULL
    CONSTRAINT ck_sentences_level CHECK (level BETWEEN 0 AND 4);
GO

-- The data change. The seed was imported easiest first, so a sentence's position in id order
-- among the seed sentences gives its band: position * 5 / total, with integer division.
-- With the 3,000 bundled sentences that is 600 per level. The seed loader computes the same
-- value in Python (content.placement.seed_level) for a database that is seeded after this runs.
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (ORDER BY id) - 1 AS position,
           COUNT(*) OVER () AS total
    FROM sentences
    WHERE source <> 'user'
)
UPDATE s
SET level = r.position * 5 / r.total
FROM sentences s
JOIN ranked r ON r.id = s.id;
