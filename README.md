# Golf Performance Tracker

A command-line application for logging golf rounds and analysing performance over time. Built as a hands-on project to demonstrate relational database design and SQL querying in Python.

---

## What It Does

- Log rounds with date, course, hole count, par, and a score per hole
- Review and correct hole scores before saving — no data is written until you confirm
- View a history of all rounds with score relative to par
- Drill into the hole-by-hole breakdown of any round
- See aggregate stats (average, best, worst) split by 9-hole and 18-hole rounds
- Visualise a score trend chart across your last 10 rounds
- Edit round details (date, course, par), fix individual hole scores, or delete a round entirely

---

## Technologies

| Technology | Role |
|---|---|
| **Python 3** | Application logic and CLI interface |
| **SQLite** | Embedded relational database (no server required) |
| **sqlite3** | Python standard library module for SQLite access |

SQLite was chosen deliberately — it stores the entire database in a single file (`golf.db`), which makes it ideal for local tools and portfolio projects. No installation, no configuration, no running database server.

---

## Installation

No third-party packages are required. Everything used (`sqlite3`, `datetime`, `re`) ships with Python.

**Prerequisites:** Python 3.7 or higher.

Clone or download this repository, then navigate into the project folder:

```bash
cd golf_tracker
```

That's it.

---

## Running the App

```bash
python golf_tracker.py
```

On first run, `golf.db` is created automatically in the same directory. The main menu will appear:

```
1. Add round
2. View all rounds
3. Hole-by-hole detail
4. Stats
5. Score trend (last 10 rounds)
6. Edit or delete a round
7. Quit
```

### Date format

All dates are entered and displayed in Australian format: **DD-MM-YYYY** (e.g. `20-05-2026`).

When entering a date, the app accepts flexible separators (`-`, `/`, `.`, or space) and both `DD-MM-YYYY` and `YYYY-MM-DD` order. Dates are stored internally as `YYYY-MM-DD` so that SQLite's `ORDER BY date` sorts them correctly, then converted to `DD-MM-YYYY` for all display.

### Back to menu

At any input prompt in any function, type **`b`** or **`back`** to immediately cancel the current operation and return to the main menu. No data is saved.

### Adding a round

After entering all hole scores, the app shows a full scorecard summary and asks:

```
Would you like to correct any scores before saving? (y/n):
```

Type `y` to fix any hole before the round is committed to the database. The loop repeats until you're happy, then asks for final save confirmation.

---

## Project Structure

```
golf_tracker/
├── golf_tracker.py   # All application and database logic
├── golf.db           # SQLite database file (created on first run)
└── README.md
```

---

## Database Schema

The database uses two tables in a one-to-many relationship: one round has many hole scores. Dates are stored as `YYYY-MM-DD` text (ISO format) for correct lexicographic sorting in SQLite.

```
rounds
──────────────────────────────────────
id          INTEGER  PRIMARY KEY
date        TEXT     stored as YYYY-MM-DD, displayed as DD-MM-YYYY
course      TEXT     e.g. "Moore Park"
holes       INTEGER  9 or 18
total_score INTEGER
par         INTEGER  e.g. 72

hole_scores
──────────────────────────────────────
round_id    INTEGER  REFERENCES rounds(id)
hole        INTEGER  1–18
score       INTEGER
```

---

## SQL Concepts Demonstrated

This project touches a range of SQL fundamentals relevant to data engineering work:

**Schema design**
- `CREATE TABLE IF NOT EXISTS` for idempotent setup scripts
- `PRIMARY KEY AUTOINCREMENT` for surrogate keys
- `NOT NULL` and `DEFAULT` constraints to enforce data integrity
- `REFERENCES` (foreign key) to model a one-to-many relationship between rounds and hole scores

**Writing data**
- `INSERT INTO` with named columns and parameterised `?` placeholders (prevents SQL injection)
- `executemany()` for efficient bulk inserts
- Transaction control with `commit()`

**Reading data**
- `SELECT` with explicit column lists rather than `SELECT *`
- `WHERE` for row filtering (e.g. filter by round id, filter by hole count)
- `ORDER BY` with `ASC`/`DESC` for sorting results
- `LIMIT` to cap result sets (used for the trend chart)
- Derived expressions in `ORDER BY` — e.g. `ORDER BY (total_score - par)` to rank rounds by performance relative to par rather than raw score
- `SUM()` aggregate function to recalculate a round total from its hole scores after an edit

**Modifying and deleting data**
- `UPDATE ... SET ... WHERE` to edit existing rows in place — used for correcting round details (date, course, par) and individual hole scores
- `DELETE FROM ... WHERE` to remove specific rows
- Two-step delete: because a foreign key constraint prevents deleting a round that still has `hole_scores` rows referencing it, child rows must be deleted before the parent. `DELETE FROM hole_scores WHERE round_id=?` runs first, then `DELETE FROM rounds WHERE id=?`. This is the manual equivalent of `ON DELETE CASCADE`

**Schema evolution**
- `ALTER TABLE ... ADD COLUMN` to add a column to an existing table without losing data, wrapped in a `try/except` to make it safe to run against both new and pre-existing databases

**Relational thinking**
- Separating round metadata from hole-level detail into two tables keeps the schema normalised — adding a 19th hole score doesn't require changing the `rounds` table structure
- Linking data across tables via a shared key (`round_id`) rather than duplicating round information on every hole row

---

## Example Output

**View all rounds:**
```
  #  Date          Course                     Holes  Score  To Par
------------------------------------------------------------------
  1  20-05-2026    Moore Park                    18     76      +4
  2  18-04-2026    Bexley Golf                   18     68      -4
```

**Hole-by-hole detail (Bexley Golf, round #2):**
```
18-04-2026  |  Bexley Golf  |  18 holes  |  Total: 68

  Hole  1: 4    Hole  2: 4    Hole  3: 3    Hole  4: 4    Hole  5: 4
  Hole  6: 3    Hole  7: 5    Hole  8: 3    Hole  9: 4    Hole 10: 4
  Hole 11: 4    Hole 12: 3    Hole 13: 4    Hole 14: 4    Hole 15: 3
  Hole 16: 5    Hole 17: 3    Hole 18: 4
```

**Score trend:**
```
--- Score vs Par: Last 2 Rounds ---

  +4 |      * 
  +3 |        
  +2 |        
  +1 |        
   E |        
  -1 |        
  -2 |        
  -3 |        
  -4 |  *     
     +--------
        1   2

      18-04  20-05

  First 1 rounds avg : -4.0 to par
  Last  1 rounds avg : +4.0 to par
  Trend: declined by 8.0 strokes (to par)
```

---

## Possible Extensions

- Export rounds to CSV for analysis in pandas or a BI tool
- Add a `par` column per hole in `hole_scores` to track hole-level performance
- Port the storage layer to PostgreSQL by swapping the `sqlite3` connection for `psycopg2` — the SQL queries are standard enough that very little else would change
- Add a handicap index calculator based on the World Handicap System formula
