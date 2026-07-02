"""
Seed demo data using the real project template.
Run: python3 seed_demo.py
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "pm_tool.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def mark_tasks(project_id, statuses):
    db = get_db()
    tasks = db.execute("SELECT * FROM tasks WHERE project_id = ?", (project_id,)).fetchall()
    for task in tasks:
        for substr, status in statuses:
            if substr.lower() in task["title"].lower():
                completed_at = datetime.utcnow().isoformat() if status == "complete" else None
                db.execute(
                    "UPDATE tasks SET status=?, completed_at=? WHERE id=?",
                    (status, completed_at, task["id"]),
                )
                break
    db.commit()
    db.close()


def complete_all(project_id):
    db = get_db()
    db.execute(
        "UPDATE tasks SET status='complete', completed_at=? WHERE project_id=?",
        (datetime.utcnow().isoformat(), project_id)
    )
    db.execute("UPDATE milestones SET status='complete', actual_date=target_date WHERE project_id=?", (project_id,))
    db.commit()
    db.close()


def seed():
    from database import init_db
    import models

    init_db()

    db = get_db()
    db.execute("DELETE FROM tasks")
    db.execute("DELETE FROM task_groups")
    db.execute("DELETE FROM milestones")
    db.execute("DELETE FROM projects")
    db.commit()
    db.close()

    projects = [
        # ── Kristin Caras ────────────────────────────────────────────────
        {
            "data": {
                "name": "Hydrant", "merchant_name": "Hydrant",
                "template_type": "optimized_activation", "ie_owner": "Kristin Caras",
                "contract_start_date": "2026-04-15", "target_go_live_date": "2026-07-08",
                "notes": "Hydration subscription bundles. ESP is Klaviyo.",
            },
            "pct": 75, "status": "active",
        },
        {
            "data": {
                "name": "Brightland", "merchant_name": "Brightland",
                "template_type": "optimized_subscription_migration", "ie_owner": "Kristin Caras",
                "contract_start_date": "2026-05-01", "target_go_live_date": "2026-06-25",
                "notes": "Migrating from Bold. Past go-live target.",
            },
            "pct": 45, "status": "active",
        },
        {
            "data": {
                "name": "Caraway Home", "merchant_name": "Caraway Home",
                "template_type": "optimized_activation", "ie_owner": "Kristin Caras",
                "contract_start_date": "2026-01-06", "target_go_live_date": "2026-03-06",
                "actual_go_live_date": "2026-03-04",
                "notes": "Launched 2 days ahead of schedule.",
            },
            "pct": 100, "status": "complete",
        },

        {
            "data": {
                "name": "Jolie", "merchant_name": "Jolie",
                "template_type": "optimized_subscription_migration", "ie_owner": "Kristin Caras",
                "contract_start_date": "2026-05-20", "target_go_live_date": "2026-07-25",
                "notes": "Migrating from Recharge v1. Filtered showerhead subscription.",
            },
            "pct": 50, "status": "active",
        },

        {
            "data": {
                "name": "Blueland", "merchant_name": "Blueland",
                "template_type": "optimized_activation", "ie_owner": "Kristin Caras",
                "contract_start_date": "2026-03-01", "target_go_live_date": "2026-05-01",
                "notes": "Project cancelled — merchant paused ReCharge rollout indefinitely.",
            },
            "pct": 25, "status": "cancelled",
        },

        # ── Marcus Webb ──────────────────────────────────────────────────
        {
            "data": {
                "name": "Graza Olive Oil", "merchant_name": "Graza Olive Oil",
                "template_type": "optimized_activation", "ie_owner": "Marcus Webb",
                "contract_start_date": "2026-05-01", "target_go_live_date": "2026-06-15",
                "notes": "Custom portal required. Overdue — go-live target missed.",
            },
            "pct": 40, "status": "active", "late": True,
        },
        {
            "data": {
                "name": "Liquid IV", "merchant_name": "Liquid IV",
                "template_type": "recharge_strategic_migration", "ie_owner": "Marcus Webb",
                "contract_start_date": "2026-03-10", "target_go_live_date": "2026-06-20",
                "notes": "Strategic migration. Complex bundle logic.",
            },
            "pct": 60, "status": "active",
        },
        {
            "data": {
                "name": "Magic Spoon", "merchant_name": "Magic Spoon",
                "template_type": "optimized_activation", "ie_owner": "Marcus Webb",
                "contract_start_date": "2025-10-01", "target_go_live_date": "2025-12-15",
                "actual_go_live_date": "2025-12-18",
                "notes": "Launched 3 days late.",
            },
            "pct": 100, "status": "complete",
        },
        {
            "data": {
                "name": "Nguyen Coffee", "merchant_name": "Nguyen Coffee",
                "template_type": "optimized_subscription_migration", "ie_owner": "Marcus Webb",
                "contract_start_date": "2025-11-01", "target_go_live_date": "2026-01-10",
                "actual_go_live_date": "2026-01-10",
                "notes": "Launched on schedule.",
            },
            "pct": 100, "status": "complete",
        },

        # ── Priya Nair ───────────────────────────────────────────────────
        {
            "data": {
                "name": "Olipop", "merchant_name": "Olipop",
                "template_type": "optimized_activation", "ie_owner": "Priya Nair",
                "contract_start_date": "2026-06-01", "target_go_live_date": "2026-07-14",
                "notes": "Subscribe & Save on sparkling tonics. Loyalty integration with Yotpo.",
            },
            "pct": 20, "status": "active",
        },
        {
            "data": {
                "name": "Hex Clad", "merchant_name": "Hex Clad",
                "template_type": "recharge_strategic_migration", "ie_owner": "Priya Nair",
                "contract_start_date": "2026-04-01", "target_go_live_date": "2026-07-05",
                "notes": "High-value cookware brand. Multi-storefront.",
            },
            "pct": 55, "status": "active",
        },
        {
            "data": {
                "name": "Buoy Health", "merchant_name": "Buoy Health",
                "template_type": "optimized_subscription_migration", "ie_owner": "Priya Nair",
                "contract_start_date": "2026-05-15", "target_go_live_date": "2026-06-28",
                "notes": "Small team, fast timeline.",
            },
            "pct": 35, "status": "active",
        },
        {
            "data": {
                "name": "Cometeer", "merchant_name": "Cometeer",
                "template_type": "optimized_activation", "ie_owner": "Priya Nair",
                "contract_start_date": "2025-09-01", "target_go_live_date": "2025-11-01",
                "actual_go_live_date": "2025-10-28",
                "notes": "Launched 4 days early.",
            },
            "pct": 100, "status": "complete",
        },
        {
            "data": {
                "name": "Fly By Jing", "merchant_name": "Fly By Jing",
                "template_type": "optimized_subscription_migration", "ie_owner": "Priya Nair",
                "contract_start_date": "2025-12-01", "target_go_live_date": "2026-02-01",
                "actual_go_live_date": "2026-02-05",
                "notes": "Launched 4 days late.",
            },
            "pct": 100, "status": "complete",
        },
    ]

    import models

    for proj in projects:
        data = proj["data"]
        display_type = data["template_type"]
        # Use "standard" for task instantiation — update display type after
        data["template_type"] = "standard"
        pid = models.create_project(data)

        # Restore display template_type
        db = get_db()
        db.execute("UPDATE projects SET template_type=? WHERE id=?", (display_type, pid))
        db.commit()
        db.close()

        pct = proj["pct"]
        db = get_db()
        tasks = db.execute("SELECT id FROM tasks WHERE project_id = ? ORDER BY id", (pid,)).fetchall()
        db.close()
        n_complete = int(len(tasks) * pct / 100)
        db = get_db()
        for i, task in enumerate(tasks):
            status = "complete" if i < n_complete else "not_started"
            completed_at = datetime.utcnow().isoformat() if status == "complete" else None
            db.execute("UPDATE tasks SET status=?, completed_at=? WHERE id=?", (status, completed_at, task["id"]))
        db.commit()
        db.close()

        db = get_db()
        if proj["status"] == "complete":
            actual = data.get("actual_go_live_date", data.get("target_go_live_date"))
            db.execute("UPDATE projects SET status='complete', actual_go_live_date=? WHERE id=?", (actual, pid))
            db.execute("UPDATE milestones SET status='complete', actual_date=target_date WHERE project_id=?", (pid,))
        if proj.get("late"):
            db.execute(
                "UPDATE tasks SET due_date='2026-06-01' WHERE project_id=? AND status != 'complete'", (pid,)
            )
        else:
            # Clear due dates on incomplete tasks so they don't show as overdue
            db.execute(
                "UPDATE tasks SET due_date=NULL WHERE project_id=? AND status != 'complete'", (pid,)
            )
        db.execute("UPDATE projects SET status=? WHERE id=?", (proj["status"], pid))
        db.commit()
        db.close()

    print(f"Demo seeded: {len(projects)} projects across 3 IEs.")


if __name__ == "__main__":
    seed()
