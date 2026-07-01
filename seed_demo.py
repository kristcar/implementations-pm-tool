"""
Seed demo data using the real project template.
All projects pull tasks from the project_templates table, same as the UI.
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
    """statuses: list of (title_substring, status)"""
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

    # ── 1. Hydrant — 80% complete, pre go-live ───────────────────────────
    p1 = models.create_project({
        "name": "Hydrant",
        "merchant_name": "Hydrant",
        "template_type": "standard",
        "ie_owner": "Kristin Caras",
        "platform": "Shopify Plus",
        "contract_start_date": "2026-04-15",
        "target_go_live_date": "2026-06-14",
        "notes": "High-priority merchant. Hydration subscription bundles. ESP is Klaviyo.",
    })
    mark_tasks(p1, [
        ("Schedule Call", "complete"),
        ("Advanced Coding", "complete"),
        ("Merchant - Download Recharge", "complete"),
        ("Enable Plus", "complete"),
        ("Merchant - Review your Settings", "complete"),
        ("Duplicate Theme", "complete"),
        ("Configure Bundles", "complete"),
        ("Additional Growth", "complete"),
        ("Merchant - Run Test Transaction", "complete"),
        ("Adjust customer portal", "complete"),
        ("Configure customer notifications", "complete"),
        ("Final Call", "complete"),
        ("Set the subscription widget live", "in_progress"),
        ("Open Risk", "not_started"),
        ("Transition merchant", "not_started"),
        ("Complete Customer Effort", "not_started"),
        ("Congratulations", "not_started"),
    ])
    # Mark milestones complete through Configure Customer Experience
    db = get_db()
    db.execute(
        "UPDATE milestones SET status='complete', actual_date=target_date WHERE project_id=? AND name != 'Test & Go-Live' AND name != 'Handoff'",
        (p1,)
    )
    db.commit()
    db.close()

    # ── 2. Graza Olive Oil — mid-implementation ──────────────────────────
    p2 = models.create_project({
        "name": "Graza Olive Oil",
        "merchant_name": "Graza",
        "template_type": "standard",
        "ie_owner": "Marcus Webb",
        "platform": "Shopify Plus",
        "contract_start_date": "2026-05-01",
        "target_go_live_date": "2026-06-30",
        "notes": "Migrating from Bold Subscriptions. Custom portal required. Large subscriber base (~40k active).",
    })
    mark_tasks(p2, [
        ("Schedule Call", "complete"),
        ("Advanced Coding", "complete"),
        ("Merchant - Download Recharge", "complete"),
        ("Enable Plus", "complete"),
        ("Merchant - Review your Settings", "complete"),
        ("Duplicate Theme", "complete"),
        ("Configure Bundles", "in_progress"),
        ("Additional Growth", "not_started"),
        ("Merchant - Run Test Transaction", "not_started"),
        ("Adjust customer portal", "not_started"),
        ("Configure customer notifications", "not_started"),
        ("Final Call", "not_started"),
        ("Set the subscription widget live", "not_started"),
        ("Open Risk", "not_started"),
        ("Transition merchant", "not_started"),
        ("Complete Customer Effort", "not_started"),
        ("Congratulations", "not_started"),
    ])
    db = get_db()
    db.execute(
        "UPDATE milestones SET status='complete', actual_date=target_date WHERE project_id=? AND name IN ('Kickoff and Confirm Scope','Recharge/Shopify Configuration')",
        (p2,)
    )
    db.commit()
    db.close()

    # ── 3. Olipop — just kicked off ──────────────────────────────────────
    p3 = models.create_project({
        "name": "Olipop",
        "merchant_name": "Olipop",
        "template_type": "standard",
        "ie_owner": "Priya Nair",
        "platform": "Shopify Plus",
        "contract_start_date": "2026-06-16",
        "target_go_live_date": "2026-08-15",
        "notes": "New logo win. Subscribe & Save on sparkling tonics. Loyalty integration with Yotpo.",
    })
    mark_tasks(p3, [
        ("Schedule Call", "complete"),
        ("Advanced Coding", "not_started"),
        ("Merchant - Download Recharge", "in_progress"),
    ])
    db = get_db()
    db.execute(
        "UPDATE milestones SET status='complete', actual_date=target_date WHERE project_id=? AND name='Kickoff and Confirm Scope'",
        (p3,)
    )
    db.commit()
    db.close()

    # ── 4. Brightland — on hold ───────────────────────────────────────────
    p4 = models.create_project({
        "name": "Brightland",
        "merchant_name": "Brightland",
        "template_type": "standard",
        "ie_owner": "Kristin Caras",
        "platform": "Shopify",
        "contract_start_date": "2026-05-01",
        "target_go_live_date": "2026-07-30",
        "notes": "On hold — merchant migrating to Shopify Plus internally. Resume expected late July 2026.",
    })
    mark_tasks(p4, [
        ("Schedule Call", "complete"),
        ("Advanced Coding", "complete"),
        ("Merchant - Download Recharge", "complete"),
        ("Enable Plus", "complete"),
        ("Merchant - Review your Settings", "complete"),
    ])
    db = get_db()
    db.execute("UPDATE projects SET status='on_hold' WHERE id=?", (p4,))
    db.execute(
        "UPDATE milestones SET status='complete', actual_date=target_date WHERE project_id=? AND name IN ('Kickoff and Confirm Scope','Recharge/Shopify Configuration')",
        (p4,)
    )
    db.commit()
    db.close()

    # ── 5. Caraway Home — complete ────────────────────────────────────────
    p5 = models.create_project({
        "name": "Caraway Home",
        "merchant_name": "Caraway",
        "template_type": "standard",
        "ie_owner": "Marcus Webb",
        "platform": "Shopify Plus",
        "contract_start_date": "2026-01-06",
        "target_go_live_date": "2026-03-06",
        "notes": "Launched 2 days ahead of schedule. Prepaid annual model. Strong merchant engagement.",
    })
    mark_tasks(p5, [
        ("Schedule Call", "complete"),
        ("Advanced Coding", "complete"),
        ("Merchant - Download Recharge", "complete"),
        ("Enable Plus", "complete"),
        ("Merchant - Review your Settings", "complete"),
        ("Duplicate Theme", "complete"),
        ("Configure Bundles", "complete"),
        ("Additional Growth", "complete"),
        ("Merchant - Run Test Transaction", "complete"),
        ("Adjust customer portal", "complete"),
        ("Configure customer notifications", "complete"),
        ("Final Call", "complete"),
        ("Set the subscription widget live", "complete"),
        ("Open Risk", "complete"),
        ("Transition merchant", "complete"),
        ("Complete Customer Effort", "complete"),
        ("Congratulations", "complete"),
    ])
    db = get_db()
    db.execute("UPDATE projects SET status='complete', actual_go_live_date='2026-03-04' WHERE id=?", (p5,))
    db.execute(
        "UPDATE milestones SET status='complete', actual_date=target_date WHERE project_id=?", (p5,)
    )
    db.commit()
    db.close()

    print("Demo seeded from real template — 5 projects:")
    print(f"  {p1}. Hydrant         — 80% done, pre go-live")
    print(f"  {p2}. Graza           — mid-implementation, bundles in progress")
    print(f"  {p3}. Olipop          — just kicked off")
    print(f"  {p4}. Brightland      — on hold")
    print(f"  {p5}. Caraway Home    — complete (launched early)")


if __name__ == "__main__":
    seed()
