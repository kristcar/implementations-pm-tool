from database import get_db
from datetime import date, timedelta


def get_project(project_id):
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    db.close()
    return row


def list_ie_owners():
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT ie_owner FROM projects WHERE ie_owner IS NOT NULL AND ie_owner != '' ORDER BY ie_owner"
    ).fetchall()
    db.close()
    return [r["ie_owner"] for r in rows]


def list_projects(status=None):
    db = get_db()
    if status and status != "all":
        rows = db.execute(
            "SELECT * FROM projects WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    db.close()
    return rows


def create_project(data):
    db = get_db()
    c = db.cursor()
    c.execute(
        """INSERT INTO projects (name, merchant_name, template_type, status, ie_owner, platform,
           contract_start_date, target_go_live_date, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"],
            data.get("merchant_name", data["name"]),
            data["template_type"],
            "active",
            data.get("ie_owner", ""),
            data.get("platform", ""),
            data.get("contract_start_date", ""),
            data.get("target_go_live_date", ""),
            data.get("notes", ""),
        ),
    )
    project_id = c.lastrowid
    _instantiate_template(db, project_id, data["template_type"], data.get("contract_start_date"))
    db.commit()
    db.close()
    return project_id


def _instantiate_template(db, project_id, template_type, start_date_str):
    c = db.cursor()
    rows = c.execute(
        "SELECT * FROM project_templates WHERE template_type = ? ORDER BY id",
        (template_type,),
    ).fetchall()

    try:
        start = date.fromisoformat(start_date_str) if start_date_str else date.today()
    except (ValueError, TypeError):
        start = date.today()

    groups = {}
    group_order = 0
    for row in rows:
        gname = row["group_name"]
        if gname not in groups:
            c.execute(
                "INSERT INTO task_groups (project_id, name, sort_order) VALUES (?, ?, ?)",
                (project_id, gname, group_order),
            )
            groups[gname] = c.lastrowid
            group_order += 1

    for row in rows:
        gname = row["group_name"]
        due = (start + timedelta(days=row["days_offset"])).isoformat()
        c.execute(
            """INSERT INTO tasks (project_id, task_group_id, title, description, owner, due_date, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, groups[gname], row["task_title"], row["task_description"], row["owner"], due, row["sort_order"]),
        )

    # Create standard milestones based on template
    milestones_standard = [
        ("Kickoff and Confirm Scope", 7),
        ("Recharge/Shopify Configuration", 14),
        ("Configure Subscription Checkout Flow", 21),
        ("Configure Customer Experience", 35),
        ("Test & Go-Live", 56),
        ("Handoff", 60),
    ]
    milestones_enterprise = [
        ("Kickoff Call", 14),
        ("Solution Design Approved", 35),
        ("Migration Plan Approved", 50),
        ("Configuration Complete", 80),
        ("UAT Sign-off", 100),
        ("Migration Complete", 115),
        ("Go-Live", 125),
        ("Project Closed", 160),
    ]
    ms_list = milestones_enterprise if template_type == "enterprise" else milestones_standard
    for i, (name, offset) in enumerate(ms_list):
        target = (start + timedelta(days=offset)).isoformat()
        c.execute(
            "INSERT INTO milestones (project_id, name, target_date, status, sort_order) VALUES (?,?,?,?,?)",
            (project_id, name, target, "upcoming", i),
        )


def update_project(project_id, data):
    db = get_db()
    db.execute(
        """UPDATE projects SET name=?, merchant_name=?, ie_owner=?, platform=?,
           status=?, contract_start_date=?, target_go_live_date=?, actual_go_live_date=?,
           notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (
            data.get("name"),
            data.get("merchant_name"),
            data.get("ie_owner"),
            data.get("platform"),
            data.get("status"),
            data.get("contract_start_date"),
            data.get("target_go_live_date"),
            data.get("actual_go_live_date") or None,
            data.get("notes"),
            project_id,
        ),
    )
    db.commit()
    db.close()


def delete_project(project_id):
    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()
    db.close()


def get_tasks_grouped(project_id):
    db = get_db()
    groups = db.execute(
        "SELECT * FROM task_groups WHERE project_id = ? ORDER BY sort_order", (project_id,)
    ).fetchall()
    result = []
    for g in groups:
        tasks = db.execute(
            "SELECT * FROM tasks WHERE task_group_id = ? ORDER BY sort_order, id", (g["id"],)
        ).fetchall()
        total = len(tasks)
        done = sum(1 for t in tasks if t["status"] == "complete")
        result.append({"group": g, "tasks": tasks, "total": total, "done": done})
    ungrouped = db.execute(
        "SELECT * FROM tasks WHERE project_id = ? AND task_group_id IS NULL ORDER BY sort_order, id",
        (project_id,),
    ).fetchall()
    if ungrouped:
        total = len(ungrouped)
        done = sum(1 for t in ungrouped if t["status"] == "complete")
        result.append({"group": {"id": None, "name": "Other"}, "tasks": ungrouped, "total": total, "done": done})
    db.close()
    return result


def get_milestones(project_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM milestones WHERE project_id = ? ORDER BY sort_order, target_date", (project_id,)
    ).fetchall()
    db.close()
    return rows


def add_milestone(project_id, name, target_date):
    db = get_db()
    c = db.cursor()
    c.execute(
        "SELECT COALESCE(MAX(sort_order),0)+1 FROM milestones WHERE project_id=?", (project_id,)
    )
    sort_order = c.fetchone()[0]
    c.execute(
        "INSERT INTO milestones (project_id, name, target_date, status, sort_order) VALUES (?,?,?,?,?)",
        (project_id, name, target_date, "upcoming", sort_order),
    )
    db.commit()
    db.close()


def update_milestone(milestone_id, data):
    db = get_db()
    db.execute(
        "UPDATE milestones SET name=?, target_date=?, actual_date=?, status=? WHERE id=?",
        (data.get("name"), data.get("target_date"), data.get("actual_date") or None, data.get("status"), milestone_id),
    )
    db.commit()
    db.close()


def delete_milestone(milestone_id):
    db = get_db()
    db.execute("DELETE FROM milestones WHERE id = ?", (milestone_id,))
    db.commit()
    db.close()


def add_task(project_id, data):
    db = get_db()
    c = db.cursor()
    c.execute(
        """INSERT INTO tasks (project_id, task_group_id, title, description, owner, due_date, notes, sort_order)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            data.get("task_group_id") or None,
            data["title"],
            data.get("description", ""),
            data.get("owner", "ie"),
            data.get("due_date") or None,
            data.get("notes", ""),
            9999,
        ),
    )
    task_id = c.lastrowid
    db.commit()
    db.close()
    return task_id


def get_task(task_id):
    db = get_db()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    db.close()
    return row


def update_task_status(task_id, status):
    from datetime import datetime
    db = get_db()
    completed_at = datetime.utcnow().isoformat() if status == "complete" else None
    db.execute(
        "UPDATE tasks SET status=?, completed_at=? WHERE id=?",
        (status, completed_at, task_id),
    )
    db.commit()
    db.close()


def update_task(task_id, data):
    db = get_db()
    db.execute(
        "UPDATE tasks SET title=?, description=?, owner=?, due_date=?, notes=?, status=? WHERE id=?",
        (
            data.get("title"),
            data.get("description"),
            data.get("owner"),
            data.get("due_date") or None,
            data.get("notes"),
            data.get("status"),
            task_id,
        ),
    )
    db.commit()
    db.close()


def delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    db.close()


def overdue_task_count(project_id):
    from datetime import date
    today = date.today().isoformat()
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM tasks WHERE project_id=? AND status != 'complete' AND due_date < ?",
        (project_id, today),
    ).fetchone()
    db.close()
    return row["cnt"] or 0


def project_progress(project_id):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as total, SUM(CASE WHEN status='complete' THEN 1 ELSE 0 END) as done FROM tasks WHERE project_id=?",
        (project_id,),
    ).fetchone()
    db.close()
    total = row["total"] or 0
    done = row["done"] or 0
    pct = int(done / total * 100) if total else 0
    return {"total": total, "done": done, "pct": pct}
