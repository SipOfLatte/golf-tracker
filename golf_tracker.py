#!/usr/bin/env python3
import sqlite3
from datetime import date

DB = "golf.db"


class BackToMenu(Exception):
    """Raised by ask() when the user types 'b' or 'back' at any prompt."""


def ask(prompt):
    """Wrapper around input() that raises BackToMenu if the user types 'b' or 'back'."""
    val = input(prompt).strip()
    if val.lower() in ("b", "back"):
        raise BackToMenu
    return val


def parse_date(raw):
    """
    Accept DD-MM-YYYY or YYYY-MM-DD with any of - / . or space as separator.
    Stores as YYYY-MM-DD internally — ISO format that SQLite sorts correctly.
    Returns None if the input can't be interpreted as a real calendar date.
    """
    import re
    parts = re.split(r'[-/. ]', raw.strip())
    if len(parts) != 3:
        return None
    a, b, c = parts
    try:
        if len(a) == 4:      # YYYY-MM-DD
            iso = f"{a}-{b.zfill(2)}-{c.zfill(2)}"
        else:                 # DD-MM-YYYY
            iso = f"{c}-{b.zfill(2)}-{a.zfill(2)}"
        date.fromisoformat(iso)  # raises ValueError if the date isn't real
        return iso
    except ValueError:
        return None


def fmt_date(iso):
    """Convert YYYY-MM-DD (storage) to DD-MM-YYYY (Australian display format)."""
    y, m, d = iso.split('-')
    return f"{d}-{m}-{y}"


def connect():
    """
    Open (or create) the SQLite database file and set up the schema.

    SQLite stores the entire database in a single file on disk. The first time
    this runs, it creates golf.db from scratch. On every subsequent run it just
    opens the existing file — your data is preserved between sessions.
    """
    conn = sqlite3.connect(DB)

    # PRAGMA is a SQLite-specific command that tweaks database behaviour.
    # Foreign keys are disabled by default in SQLite for historical reasons,
    # so we turn them on explicitly. This means SQLite will refuse to insert a
    # hole_score row that references a round_id that doesn't exist in rounds.
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executescript("""
        -- CREATE TABLE IF NOT EXISTS means: create this table only when it
        -- doesn't already exist. Safe to run every startup without wiping data.

        CREATE TABLE IF NOT EXISTS rounds (
            -- INTEGER PRIMARY KEY tells SQLite to auto-assign a unique integer
            -- ID to each row. AUTOINCREMENT ensures IDs never get reused even
            -- if a row is deleted.
            id          INTEGER PRIMARY KEY AUTOINCREMENT,

            -- TEXT NOT NULL means this column stores text and must always have
            -- a value — SQLite will reject an INSERT that leaves it blank.
            date        TEXT NOT NULL,
            course      TEXT NOT NULL,

            -- INTEGER stores whole numbers. We use it for holes (9 or 18),
            -- the total score, and the course par.
            holes       INTEGER NOT NULL,
            total_score INTEGER NOT NULL,

            -- DEFAULT 72 means if no par value is provided during an INSERT,
            -- SQLite automatically fills in 72.
            par         INTEGER NOT NULL DEFAULT 72
        );

        CREATE TABLE IF NOT EXISTS hole_scores (
            -- REFERENCES rounds(id) is a foreign key constraint: every
            -- round_id stored here must match an id that exists in rounds.
            -- This prevents orphaned scores for rounds that don't exist.
            round_id    INTEGER NOT NULL REFERENCES rounds(id),
            hole        INTEGER NOT NULL,
            score       INTEGER NOT NULL
        );
    """)

    # ALTER TABLE adds a new column to an existing table — useful when we need
    # to extend the schema after data has already been stored. If the column
    # already exists SQLite raises an OperationalError, so we catch and ignore
    # it. This keeps the app safe whether the DB is brand new or pre-existing.
    try:
        conn.execute("ALTER TABLE rounds ADD COLUMN par INTEGER NOT NULL DEFAULT 72")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already present — nothing to do

    return conn


def add_round(conn):
    """Collect a new round from the user and write it to the database."""
    print("Type 'b' at any prompt to return to the menu.\n")

    # Keep prompting until the user provides a parseable date.
    today_display = fmt_date(str(date.today()))
    while True:
        raw = ask(f"Date (DD-MM-YYYY) [{today_display}]: ")
        if not raw:
            d = str(date.today())
            break
        d = parse_date(raw)
        if d:
            break
        print("  Unrecognised date — try DD-MM-YYYY, e.g. 20-05-2026.")

    course = ask("Course name: ")
    holes  = int(ask("Holes (9/18): "))
    par    = int(ask("Course par: "))

    print(f"\nEnter score for each of {holes} holes:")
    scores = []
    for h in range(1, holes + 1):
        scores.append(int(ask(f"  Hole {h:>2}: ")))

    # Correction loop — show the full scorecard and let the user fix any hole
    # before the round is committed to the database.
    while True:
        print()
        for h, s in enumerate(scores, 1):
            print(f"  Hole {h:>2}: {s}")
        total = sum(scores)
        diff = total - par
        diff_str = f"+{diff}" if diff > 0 else ("E" if diff == 0 else str(diff))
        print(f"  --------")
        print(f"  Total  : {total} ({diff_str})")

        if ask("\nWould you like to correct any scores before saving? (y/n): ").lower() != "y":
            break
        hole_num = int(ask(f"Which hole (1-{holes})? "))
        if 1 <= hole_num <= holes:
            scores[hole_num - 1] = int(ask(f"New score for hole {hole_num}: "))
        else:
            print(f"  Hole must be between 1 and {holes}.")

    total = sum(scores)
    if ask("\nSave this round? (y/n): ").lower() != "y":
        return

    # INSERT INTO adds a new row to the named table.
    # Listing column names explicitly (date, course, ...) means the order of
    # VALUES must match that list — good practice so adding columns later
    # doesn't silently corrupt inserts.
    # The ? placeholders are filled in safely by SQLite from the tuple, which
    # prevents SQL injection attacks.
    cur = conn.execute(
        "INSERT INTO rounds (date, course, holes, total_score, par) VALUES (?,?,?,?,?)",
        (d, course, holes, total, par)
    )

    # lastrowid gives us the auto-assigned id of the row we just inserted.
    # We need it so each hole_score row can reference this specific round.
    rid = cur.lastrowid

    # executemany runs the same INSERT once for every tuple in the list,
    # which is much faster than calling execute() inside a Python loop.
    # Each hole_score row links back to this round via round_id = rid.
    conn.executemany(
        "INSERT INTO hole_scores VALUES (?,?,?)",
        [(rid, i + 1, s) for i, s in enumerate(scores)]
    )

    # commit() finalises all the changes above as a single transaction.
    # Until commit() is called, the inserts exist only in memory and won't
    # survive a crash or power loss.
    conn.commit()
    print(f"Saved (round #{rid})")


def rel_str(score, par):
    """Format a score relative to par as +3, -1, or E (even)."""
    diff = score - par
    return f"+{diff}" if diff > 0 else ("E" if diff == 0 else str(diff))


def view_rounds(conn):
    """
    Print a summary table of every round in chronological order and return the
    row list so callers can map a display number back to the real database id.

    ORDER BY date ASC sorts oldest first so the list reads as a timeline
    (ASC = ascending / oldest first; DESC would be newest first).
    Display numbers (#1, #2, …) are generated by enumerate so they are always
    sequential — gaps in the underlying id column caused by deletions never
    appear in the output.

    Returns the list of rows so callers can do: rid = rows[num - 1][0]
    """
    rows = conn.execute(
        "SELECT id, date, course, holes, total_score, par FROM rounds ORDER BY date ASC"
    ).fetchall()

    if not rows:
        print("No rounds yet.")
        return rows

    print(f"\n{'#':>3}  {'Date':<12}  {'Course':<25}  Holes  Score  To Par")
    print("-" * 66)
    for i, r in enumerate(rows, 1):
        print(f"{i:>3}  {fmt_date(r[1]):<12}  {r[2]:<25}  {r[3]:>5}  {r[4]:>5}  {rel_str(r[4], r[5]):>6}")

    return rows


def view_detail(conn):
    """
    Show the score for every individual hole in a chosen round.

    We use two separate queries:
      1. Fetch the round summary from rounds using its id.
      2. Fetch all matching hole rows from hole_scores using round_id.

    WHERE filters rows to only those that match a condition — here, only the
    round whose id equals the one the user typed. Without WHERE, SELECT would
    return every row in the table.
    """
    rows = view_rounds(conn)
    if not rows:
        return
    print("Type 'b' at any prompt to return to the menu.")
    num = int(ask("\nRound # for hole detail: "))
    if not 1 <= num <= len(rows):
        print("Invalid round number.")
        return
    # Map the display number to the real database id using the returned list.
    rid = rows[num - 1][0]

    # fetchone() returns a single row (or None if no row matched).
    # We only expect one round per id because id is a PRIMARY KEY.
    row = conn.execute("SELECT * FROM rounds WHERE id=?", (rid,)).fetchone()
    if not row:
        print("Not found.")
        return

    print(f"\n{fmt_date(row[1])}  |  {row[2]}  |  {row[3]} holes  |  Total: {row[4]}")

    # JOIN would be another way to fetch this data alongside the round in one
    # query, but two simple queries are easier to read here.
    # ORDER BY hole ensures holes print in order 1→18, not insertion order.
    hs = conn.execute(
        "SELECT hole, score FROM hole_scores WHERE round_id=? ORDER BY hole",
        (rid,)
    ).fetchall()
    for h, s in hs:
        print(f"  Hole {h:>2}: {s}")


def view_trend(conn):
    """
    Plot score-vs-par for the last 10 rounds as an ASCII chart and summarise
    whether performance is improving or declining.

    We use score relative to par (not raw score) so that 9-hole and 18-hole
    rounds land on the same scale.

    LIMIT 10 tells SQLite to return at most 10 rows instead of the full table.
    Combined with ORDER BY date DESC this gives us the 10 most recent rounds.
    We then reverse the list in Python so the chart reads oldest → newest.
    """
    rows = conn.execute(
        "SELECT date, total_score, par FROM rounds ORDER BY date DESC LIMIT 10"
    ).fetchall()

    if len(rows) < 2:
        print("Need at least 2 rounds to show a trend.")
        return

    rows = list(reversed(rows))  # oldest → newest for left-to-right chart
    n = len(rows)
    diffs = [r[1] - r[2] for r in rows]  # score relative to par per round

    hi = max(diffs)
    lo = min(diffs)
    if hi == lo:
        hi += 1  # ensure the chart has at least two rows of height

    print(f"\n--- Score vs Par: Last {n} Rounds ---\n")

    # Draw one row per score level from the highest down to the lowest.
    # Each column represents one round; a * marks where that round's score sits.
    for level in range(hi, lo - 1, -1):
        if level > 0:
            label = f"+{level}"
        elif level == 0:
            label = "  E"
        else:
            label = str(level)
        marks = "".join("  * " if d == level else "    " for d in diffs)
        print(f"{label:>4} |{marks}")

    print("     +" + "----" * n)
    print("      " + "".join(f"{i + 1:>4}" for i in range(n)))
    print("\n      " + "  ".join(fmt_date(r[0])[:5] for r in rows))  # DD-MM date labels

    # Compare the first half of rounds against the second half.
    # A lower average relative to par means improvement (fewer strokes over par).
    mid = n // 2
    avg_early = sum(diffs[:mid]) / mid
    avg_late  = sum(diffs[n - mid:]) / mid
    change = avg_late - avg_early
    direction = "improved" if change < 0 else ("declined" if change > 0 else "flat")

    print(f"\n  First {mid} rounds avg : {avg_early:+.1f} to par")
    print(f"  Last  {mid} rounds avg : {avg_late:+.1f} to par")
    if direction == "flat":
        print("  Trend: no change")
    else:
        print(f"  Trend: {direction} by {abs(change):.1f} strokes (to par)")


def view_stats(conn):
    """
    Show average, best, and worst scores for 9-hole and 18-hole rounds separately.

    WHERE holes=? filters to only the rows where the holes column equals the
    value we pass in (9 or 18). This lets us produce separate stats for each
    round length without needing two separate tables.

    ORDER BY (total_score - par) sorts by score relative to par so the best
    round (lowest over par, or furthest under par) always appears first.
    """
    for holes in (18, 9):
        rows = conn.execute(
            "SELECT total_score, par, course, date FROM rounds WHERE holes=? ORDER BY (total_score - par)",
            (holes,)
        ).fetchall()

        if not rows:
            continue  # skip this hole-count if the player has no rounds for it

        scores = [r[0] for r in rows]
        pars   = [r[1] for r in rows]
        diffs  = [s - p for s, p in zip(scores, pars)]
        avg_score = sum(scores) / len(scores)
        avg_diff  = sum(diffs)  / len(diffs)
        avg_diff_str = f"+{avg_diff:.1f}" if avg_diff > 0 else ("E" if avg_diff == 0 else f"{avg_diff:.1f}")

        # Because we sorted by (total_score - par), rows[0] is the best round
        # and rows[-1] is the worst.
        best  = rows[0]
        worst = rows[-1]

        print(f"\n{holes}-hole rounds ({len(rows)} played)")
        print(f"  Average score : {avg_score:.1f}  ({avg_diff_str} avg to par)")
        print(f"  Best round    : {best[0]} ({rel_str(best[0], best[1])})  —  {best[2]}, {fmt_date(best[3])}")
        print(f"  Worst round   : {worst[0]} ({rel_str(worst[0], worst[1])})  —  {worst[2]}, {fmt_date(worst[3])}")


def manage_round(conn):
    """
    Let the user edit round details, edit individual hole scores, or delete a
    round entirely. Presents the round list first so the user can see the IDs.
    """
    rows = view_rounds(conn)
    if not rows:
        return

    print("Type 'b' at any prompt to return to the menu.")
    num = int(ask("\nRound # to edit or delete: "))
    if not 1 <= num <= len(rows):
        print("Invalid round number.")
        return
    # Map the display number to the real database id using the returned list.
    rid = rows[num - 1][0]

    # Fetch the full row for the chosen round so we can show current values
    # and use them as defaults when the user skips a field.
    row = conn.execute(
        "SELECT id, date, course, holes, total_score, par FROM rounds WHERE id=?",
        (rid,)
    ).fetchone()
    if not row:
        print("Round not found.")
        return

    id_, date_, course, holes, total_score, par = row
    print(f"\nRound #{id_}  |  {fmt_date(date_)}  |  {course}  |  {holes} holes  |  Score: {total_score}  |  Par: {par}")
    print("""
  1. Edit round details (date, course name, par)
  2. Edit a hole score
  3. Delete this round""")

    choice = ask("\nChoice: ")

    if choice == "1":
        _edit_round_details(conn, id_, date_, course, par)

    elif choice == "2":
        _edit_hole_score(conn, id_, holes)

    elif choice == "3":
        _delete_round(conn, id_, date_, course)


def _edit_round_details(conn, rid, date_, course, par):
    """
    Update the date, course name, or par for an existing round using UPDATE.

    UPDATE modifies existing rows in place — unlike INSERT which adds new rows.
    SET lists the columns to change and their new values.
    WHERE restricts the update to only the row whose id matches; without WHERE,
    every row in the table would be overwritten.

    Pressing Enter without typing keeps the current value.
    """
    print("Press Enter to keep the current value.\n")
    raw_date   = ask(f"Date   [{fmt_date(date_)}]: ")
    new_date   = parse_date(raw_date or date_) or date_
    new_course = ask(f"Course [{course}]: ") or course
    raw_par    = ask(f"Par    [{par}]: ")
    new_par    = int(raw_par) if raw_par else par

    conn.execute(
        "UPDATE rounds SET date=?, course=?, par=? WHERE id=?",
        (new_date, new_course, new_par, rid)
    )
    conn.commit()
    print("Round details updated.")


def _edit_hole_score(conn, rid, holes):
    """
    Update the score for one hole and recalculate the round total.

    We use two UPDATE statements:
      1. Change the score for the specific hole in hole_scores.
      2. Recalculate and store the new total in rounds.

    For step 2 we use SUM(), an aggregate function that adds up all values in
    a column across the matching rows. This is safer than doing the arithmetic
    in Python because it stays in sync with whatever is actually in the database.
    """
    # Show current hole scores so the user knows what they're changing.
    hs = conn.execute(
        "SELECT hole, score FROM hole_scores WHERE round_id=? ORDER BY hole",
        (rid,)
    ).fetchall()
    print("\nCurrent scores:")
    for h, s in hs:
        print(f"  Hole {h:>2}: {s}")

    hole_num  = int(ask(f"\nHole to edit (1-{holes}): "))
    new_score = int(ask(f"New score for hole {hole_num}: "))

    # Update just the one row where both round_id and hole match.
    # Using AND in the WHERE clause means both conditions must be true —
    # the row must belong to this round AND be the correct hole number.
    conn.execute(
        "UPDATE hole_scores SET score=? WHERE round_id=? AND hole=?",
        (new_score, rid, hole_num)
    )

    # Recalculate the round total from the hole scores using SUM().
    # The subquery pattern here — SELECT SUM(...) FROM hole_scores WHERE ... —
    # reads "sum the score column for every hole_score row that belongs to
    # this round", giving us the fresh total in one query.
    new_total = conn.execute(
        "SELECT SUM(score) FROM hole_scores WHERE round_id=?",
        (rid,)
    ).fetchone()[0]

    conn.execute(
        "UPDATE rounds SET total_score=? WHERE id=?",
        (new_total, rid)
    )
    conn.commit()
    print(f"Hole {hole_num} updated. New round total: {new_total}")


def _delete_round(conn, rid, date_, course):
    """
    Permanently remove a round and all its hole scores.

    Because foreign keys are enabled, SQLite would reject deleting a round
    that still has hole_score rows referencing it. We therefore delete the
    child rows (hole_scores) before the parent row (rounds) — the order
    matters. This is the manual equivalent of ON DELETE CASCADE.

    DELETE FROM removes every row that matches the WHERE condition. There is
    no undo, which is why we ask for confirmation first.
    """
    confirm = ask(f"Delete round #{rid} ({fmt_date(date_)}, {course})? Cannot be undone. (y/n): ").lower()
    if confirm != "y":
        print("Cancelled.")
        return

    # Delete child rows first to satisfy the foreign key constraint.
    conn.execute("DELETE FROM hole_scores WHERE round_id=?", (rid,))
    # Now safe to delete the parent round row.
    conn.execute("DELETE FROM rounds WHERE id=?", (rid,))
    conn.commit()
    print(f"Round #{rid} deleted.")


MENU = """
1. Add round
2. View all rounds
3. Hole-by-hole detail
4. Stats
5. Score trend (last 10 rounds)
6. Edit or delete a round
7. Quit
"""


def main():
    """Entry point: open the database then loop on the menu until the user quits."""
    conn = connect()
    while True:
        print(MENU)
        c = input("Choice: ").strip()
        try:
            if   c == "1": add_round(conn)
            elif c == "2": view_rounds(conn)
            elif c == "3": view_detail(conn)
            elif c == "4": view_stats(conn)
            elif c == "5": view_trend(conn)
            elif c == "6": manage_round(conn)
            elif c == "7": break
        except BackToMenu:
            print("\nReturning to menu.")
    conn.close()


if __name__ == "__main__":
    main()
