"""
Migration: Update VegetationComponent parameters in SQLite DB.

Changes
-------
1. Remove   vegetation_decay_rate        (no longer used in new model)
2. Add      vegetation_erodibility_factor
3. Add      vegetation_interception_factor
4. Add      base_runoff_rate
5. Update   initial_vegetation_cover default  0.3 → 0.1
6. Update   vegetation_growth_rate  default   0.01 → 0.05
7. Update   component description

Usage
-----
    python migrate_vegetation_params.py

Set DB_PATH below to point at your SQLite file before running.
"""

import sqlite3
import sys
import os
import shutil
from datetime import datetime

# ── CONFIGURE THIS ────────────────────────────────────────────────────────────
DB_PATH = r"C:\Users\spi82\Landscape Simulation Projects\QT\landEvolve\app\data\db\app_data.db"
# ─────────────────────────────────────────────────────────────────────────────

COMPONENT_NAME = "VegetationComponent"

NEW_DESCRIPTION = (
    "Vegetation cover model with static or dynamic behaviour. "
    "Dynamic mode uses logistic growth with channel suppression driven by "
    "drainage area. Vegetation reduces erosion through two mechanisms: "
    "erodibility reduction (root cohesion) and runoff reduction (interception)."
)

# Parameters to remove
REMOVE_KEYS = [
    "vegetation_decay_rate",
]

# Parameters to add: (key, type, validation, default_value)
ADD_PARAMS = [
    ("vegetation_erodibility_factor",   "QDoubleSpinBox", "0.0|1.0|0.01",   "0.8"),
    ("vegetation_interception_factor",  "QDoubleSpinBox", "0.0|1.0|0.01",   "0.4"),
    ("base_runoff_rate",                "QDoubleSpinBox", "0.0|10.0|0.01",  "0.55"),
]

# Parameters to update defaults: (key, new_default)
UPDATE_DEFAULTS = [
    ("initial_vegetation_cover", "0.1"),
    ("vegetation_growth_rate",   "0.05"),
]


def backup(db_path):
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{db_path}.backup_{ts}"
    shutil.copy2(db_path, backup)
    print(f"  Backup created: {backup}")
    return backup


def get_component_id(cur, name):
    cur.execute("SELECT id FROM component WHERE name = ?", (name,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Component '{name}' not found in component table.")
    return row[0]


def run_migration(db_path):
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at '{db_path}'")
        print("       Set DB_PATH at the top of this script and try again.")
        sys.exit(1)

    print(f"\nMigrating: {db_path}")
    backup(db_path)

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    try:
        comp_id = get_component_id(cur, COMPONENT_NAME)
        print(f"  Found {COMPONENT_NAME} with id={comp_id}")

        # 1. Update component description
        cur.execute(
            "UPDATE component SET description = ? WHERE id = ?",
            (NEW_DESCRIPTION, comp_id),
        )
        print(f"  Updated component description")

        # 2. Remove old parameters
        for key in REMOVE_KEYS:
            cur.execute(
                "DELETE FROM component_param WHERE component_id = ? AND key = ?",
                (comp_id, key),
            )
            removed = cur.rowcount
            if removed:
                print(f"  Removed param: {key}")
            else:
                print(f"  Param not found (skipped): {key}")

        # 3. Update defaults on existing params
        for key, new_default in UPDATE_DEFAULTS:
            cur.execute(
                "UPDATE component_param SET default_value = ? "
                "WHERE component_id = ? AND key = ?",
                (new_default, comp_id, key),
            )
            if cur.rowcount:
                print(f"  Updated default: {key} → {new_default}")
            else:
                print(f"  Param not found for default update (skipped): {key}")

        # 4. Add new parameters (skip if already present)
        for key, typ, validation, default in ADD_PARAMS:
            cur.execute(
                "SELECT id FROM component_param WHERE component_id = ? AND key = ?",
                (comp_id, key),
            )
            if cur.fetchone():
                print(f"  Already exists (skipped): {key}")
                continue

            cur.execute(
                "INSERT INTO component_param (component_id, key, type, validation, default_value) "
                "VALUES (?, ?, ?, ?, ?)",
                (comp_id, key, typ, validation, default),
            )
            print(f"  Added param: {key} = {default}")

        con.commit()
        print("\nMigration complete.\n")

    except Exception as e:
        con.rollback()
        print(f"\nERROR: {e}")
        print("Changes rolled back. Your database is unchanged.")
        sys.exit(1)

    finally:
        con.close()


def verify(db_path):
    print("Verifying final state...")
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    comp_id = get_component_id(cur, COMPONENT_NAME)

    cur.execute(
        "SELECT key, type, validation, default_value "
        "FROM component_param WHERE component_id = ? ORDER BY id",
        (comp_id,),
    )
    rows = cur.fetchall()

    print(f"\n  {COMPONENT_NAME} parameters:")
    print(f"  {'key':<35} {'type':<20} {'validation':<20} {'default'}")
    print(f"  {'-'*35} {'-'*20} {'-'*20} {'-'*10}")
    for key, typ, validation, default in rows:
        print(f"  {key:<35} {typ:<20} {validation:<20} {default}")

    cur.execute("SELECT description FROM component WHERE id = ?", (comp_id,))
    desc = cur.fetchone()[0]
    print(f"\n  Description: {desc}\n")

    con.close()


if __name__ == "__main__":
    run_migration(DB_PATH)
    verify(DB_PATH)