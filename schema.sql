-- =============================================================================
-- schema.sql — Golf Performance Tracker
-- =============================================================================
-- This file documents the full database schema and every category of SQL query
-- used in the application. It is written for someone learning SQL and can be
-- run directly in any SQLite client (e.g. DB Browser for SQLite, sqlite3 CLI).
-- =============================================================================


-- =============================================================================
-- SETUP
-- =============================================================================

-- PRAGMA is a SQLite-specific command for changing database settings.
-- Foreign key enforcement is OFF by default in SQLite for backwards-
-- compatibility reasons, so we must enable it explicitly each session.
-- Without this, SQLite would allow hole_scores rows to reference round IDs
-- that do not exist, silently corrupting the data.
PRAGMA foreign_keys = ON;


-- =============================================================================
-- CREATE TABLES
-- =============================================================================

-- CREATE TABLE IF NOT EXISTS means: only create this table when it does not
-- already exist. Running this script on an existing database is safe — it will
-- not wipe or overwrite any stored data.

CREATE TABLE IF NOT EXISTS rounds (
    -- INTEGER PRIMARY KEY tells SQLite this column is the unique identifier for
    -- each row. SQLite auto-assigns an incrementing integer (1, 2, 3 …) when a
    -- new row is inserted and no id value is provided.
    -- AUTOINCREMENT adds a guarantee that IDs are never reused, even after a
    -- row is deleted. Without it, a deleted id could be reassigned to a new row.
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    -- TEXT is SQLite's string type. NOT NULL means this column must always have
    -- a value — an INSERT that omits it or passes NULL will be rejected.
    -- Dates are stored as text in YYYY-MM-DD format so that ORDER BY date
    -- produces correct chronological ordering (lexicographic sort = date sort
    -- when the format is year-first).
    date        TEXT    NOT NULL,
    course      TEXT    NOT NULL,

    -- INTEGER stores whole numbers with no decimal point.
    holes       INTEGER NOT NULL,   -- 9 or 18
    total_score INTEGER NOT NULL,

    -- DEFAULT 72 means if a row is inserted without supplying a par value,
    -- SQLite automatically stores 72. The column is still NOT NULL — the
    -- default simply provides the value when the caller does not.
    par         INTEGER NOT NULL DEFAULT 72
);

CREATE TABLE IF NOT EXISTS hole_scores (
    -- REFERENCES rounds(id) is a foreign key constraint.
    -- It means every value stored in round_id must match an id that exists in
    -- the rounds table. SQLite will reject any INSERT or UPDATE that would
    -- create an orphaned row — a hole score with no parent round.
    round_id    INTEGER NOT NULL REFERENCES rounds(id),

    hole        INTEGER NOT NULL,   -- hole number, 1–18
    score       INTEGER NOT NULL    -- strokes taken on that hole
);


-- =============================================================================
-- SCHEMA EVOLUTION
-- =============================================================================

-- ALTER TABLE adds a new column to an existing table without dropping or
-- recreating it, so all existing data is preserved.
-- The par column was added after the initial schema was deployed. Running this
-- on a database that already has the column will raise an error, which the
-- application catches and ignores in Python.
ALTER TABLE rounds ADD COLUMN par INTEGER NOT NULL DEFAULT 72;


-- =============================================================================
-- INSERT — adding data
-- =============================================================================

-- INSERT INTO adds a new row to the named table.
-- Listing column names explicitly (rather than relying on column order) means
-- the statement keeps working correctly if columns are ever added or reordered.
-- The VALUES clause supplies one value per listed column, in the same order.
INSERT INTO rounds (date, course, holes, total_score, par)
VALUES ('2026-04-18', 'Bexley Golf', 18, 68, 72);

-- After inserting a round we need its auto-assigned id so we can attach hole
-- scores to it. In SQLite this is retrieved with last_insert_rowid().
-- In the Python app this is accessed via cursor.lastrowid.
SELECT last_insert_rowid();

-- INSERT a single hole score. round_id must match an id that exists in rounds
-- (enforced by the foreign key constraint above).
INSERT INTO hole_scores (round_id, hole, score)
VALUES (1, 1, 4);

-- INSERT multiple hole scores at once using multiple VALUES rows.
-- This is more efficient than running a separate INSERT for each hole.
-- The Python app uses executemany() to achieve the same result.
INSERT INTO hole_scores (round_id, hole, score)
VALUES
    (1, 1,  4),
    (1, 2,  4),
    (1, 3,  3),
    (1, 4,  4),
    (1, 5,  4),
    (1, 6,  3),
    (1, 7,  5),
    (1, 8,  3),
    (1, 9,  4),
    (1, 10, 4),
    (1, 11, 4),
    (1, 12, 3),
    (1, 13, 4),
    (1, 14, 4),
    (1, 15, 3),
    (1, 16, 5),
    (1, 17, 3),
    (1, 18, 4);


-- =============================================================================
-- SELECT — reading data
-- =============================================================================

-- Retrieve every round in chronological order.
-- SELECT lists the columns to return — naming them explicitly is safer than
-- SELECT * because adding a new column won't silently change the result shape.
-- ORDER BY date ASC sorts oldest first (ASC = ascending; DESC = newest first).
SELECT id, date, course, holes, total_score, par
FROM rounds
ORDER BY date ASC;

-- Retrieve a single round by its id.
-- WHERE filters rows to only those matching the condition.
-- Without WHERE, every row in the table would be returned.
-- A PRIMARY KEY is unique, so this always returns at most one row.
SELECT id, date, course, holes, total_score, par
FROM rounds
WHERE id = 1;

-- Retrieve all hole scores for a specific round, in hole order.
-- WHERE round_id = 1 keeps only the rows belonging to round #1.
-- ORDER BY hole ensures the results come back 1, 2, 3 … rather than in
-- whatever order SQLite happens to store them.
SELECT hole, score
FROM hole_scores
WHERE round_id = 1
ORDER BY hole ASC;

-- Retrieve the 10 most recent rounds for the trend chart.
-- ORDER BY date DESC puts the newest dates first.
-- LIMIT 10 tells SQLite to stop after returning 10 rows, which is faster than
-- fetching all rows and discarding the rest in application code.
SELECT date, total_score, par
FROM rounds
ORDER BY date DESC
LIMIT 10;

-- Retrieve all 18-hole rounds ranked best to worst relative to par.
-- WHERE holes = 18 filters out 9-hole rounds so they are not mixed in.
-- ORDER BY (total_score - par) sorts by the difference — a score of 68 on a
-- par-72 course gives -4, which sorts before +4, placing better rounds first.
SELECT total_score, par, course, date
FROM rounds
WHERE holes = 18
ORDER BY (total_score - par) ASC;

-- Recalculate a round's total score by summing its hole scores.
-- SUM() is an aggregate function — it collapses many rows into a single value
-- by adding up the score column across all rows that match the WHERE clause.
-- This is used after editing a hole score to keep rounds.total_score in sync.
SELECT SUM(score)
FROM hole_scores
WHERE round_id = 1;


-- =============================================================================
-- UPDATE — modifying existing data
-- =============================================================================

-- UPDATE changes values in existing rows without deleting and re-inserting them.
-- SET lists the columns to change and their new values.
-- WHERE restricts which rows are affected — without WHERE, every row in the
-- table would be updated, which is almost never what you want.

-- Edit the date, course name, and par for a specific round.
UPDATE rounds
SET date   = '2026-04-18',
    course = 'Bexley Golf',
    par    = 72
WHERE id = 1;

-- Correct the score for a single hole.
-- Both conditions in the WHERE clause must be true (AND), so only the row
-- that belongs to round #1 AND is hole #3 will be changed.
UPDATE hole_scores
SET score = 3
WHERE round_id = 1
  AND hole = 3;

-- After correcting a hole score, update the round total to match.
-- In practice the app first runs the SUM() SELECT above to get the new total,
-- then passes that value in here.
UPDATE rounds
SET total_score = 68
WHERE id = 1;


-- =============================================================================
-- DELETE — removing data
-- =============================================================================

-- DELETE FROM removes every row that matches the WHERE condition.
-- There is no built-in undo, so the application always asks for confirmation
-- before running these statements.

-- Step 1: delete all hole scores that belong to the round being removed.
-- This must happen BEFORE deleting the round row itself. Because foreign keys
-- are enabled, SQLite will reject deleting a rounds row that still has
-- hole_scores rows referencing it — the child rows must go first.
-- This manual two-step is the equivalent of defining ON DELETE CASCADE on the
-- hole_scores table, which would make SQLite handle it automatically.
DELETE FROM hole_scores
WHERE round_id = 1;

-- Step 2: now that no hole_scores rows reference round #1, it is safe to
-- delete the round itself.
DELETE FROM rounds
WHERE id = 1;
