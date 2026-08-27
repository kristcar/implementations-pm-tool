from database import get_db
from datetime import date, timedelta


def get_project(project_id):
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    db.close()
    return row


def list_ie_owners():
    db = get_db()
    from_table = {r["name"] for r in db.execute("SELECT name FROM ie_owners").fetchall()}
    from_projects = {r["ie_owner"] for r in db.execute(
        "SELECT DISTINCT ie_owner FROM projects WHERE ie_owner IS NOT NULL AND ie_owner != ''"
    ).fetchall()}
    db.close()
    return sorted(from_table | from_projects)


def add_ie_owner(name):
    db = get_db()
    db.execute("INSERT OR IGNORE INTO ie_owners (name) VALUES (?)", (name.strip(),))
    db.commit()
    db.close()


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
           contract_start_date, target_go_live_date, notes, salesforce_link)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            data.get("salesforce_link", ""),
        ),
    )
    project_id = c.lastrowid
    _instantiate_template(db, project_id, data["template_type"], date.today().isoformat(), data.get("target_go_live_date"))
    db.commit()
    db.close()
    return project_id


def _instantiate_template(db, project_id, template_type, start_date_str, target_date_str=None):
    c = db.cursor()
    rows = c.execute(
        "SELECT * FROM project_templates WHERE template_type = ? ORDER BY id",
        (template_type,),
    ).fetchall()

    try:
        start = date.fromisoformat(start_date_str) if start_date_str else date.today()
    except (ValueError, TypeError):
        start = date.today()

    try:
        target = date.fromisoformat(target_date_str) if target_date_str else None
    except (ValueError, TypeError):
        target = None

    # Build cumulative prefix-sum offsets: task i's offset = sum of durations of all tasks before it
    # This means task 0 starts at day 0 (today) and each subsequent task is placed after the previous one's duration
    durations = [row["days_offset"] for row in rows]
    cum_offsets = []
    running = 0
    for d in durations:
        cum_offsets.append(running)
        running += d
    total_natural = running  # sum of all durations = natural project length

    total_span = (target - start).days if target else None

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

    for i, row in enumerate(rows):
        gname = row["group_name"]
        if target and total_natural > 0 and total_span is not None:
            scaled_days = round(cum_offsets[i] / total_natural * total_span)
        else:
            scaled_days = cum_offsets[i]
        due = (start + timedelta(days=scaled_days)).isoformat()
        c.execute(
            """INSERT INTO tasks (project_id, task_group_id, title, description, owner, due_date, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, groups[gname], row["task_title"], row["task_description"], row["owner"], due, row["sort_order"]),
        )

    # Derive milestones from task groups — name and date match what was actually created
    group_rows = c.execute(
        "SELECT id, name, sort_order FROM task_groups WHERE project_id=? ORDER BY sort_order",
        (project_id,)
    ).fetchall()
    for i, g in enumerate(group_rows):
        last = c.execute(
            "SELECT MAX(due_date) as last_due FROM tasks WHERE task_group_id=? AND due_date IS NOT NULL",
            (g["id"],)
        ).fetchone()
        target_date = last["last_due"] if last and last["last_due"] else start.isoformat()
        c.execute(
            "INSERT INTO milestones (project_id, name, target_date, status, sort_order) VALUES (?,?,?,?,?)",
            (project_id, g["name"], target_date, "upcoming", i),
        )


def update_project(project_id, data):
    db = get_db()
    db.execute(
        """UPDATE projects SET name=?, merchant_name=?, ie_owner=?, platform=?,
           status=?, contract_start_date=?, target_go_live_date=?, actual_go_live_date=?,
           notes=?, salesforce_link=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
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
            data.get("salesforce_link") or None,
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

    # Auto-derive status from task group completion
    group_stats = {}
    groups = db.execute(
        "SELECT tg.id, tg.name, COUNT(t.id) as total, SUM(CASE WHEN t.status='complete' THEN 1 ELSE 0 END) as done "
        "FROM task_groups tg LEFT JOIN tasks t ON t.task_group_id = tg.id "
        "WHERE tg.project_id = ? GROUP BY tg.id", (project_id,)
    ).fetchall()
    for g in groups:
        group_stats[g["name"]] = {"total": g["total"], "done": g["done"]}

    result = []
    for row in rows:
        m = dict(row)
        stats = group_stats.get(m["name"])
        if stats and stats["total"] > 0:
            if stats["done"] == stats["total"]:
                m["status"] = "complete"
            elif stats["done"] > 0:
                m["status"] = "upcoming"
            else:
                m["status"] = "upcoming"
        result.append(m)

    db.close()
    return result


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


def complete_all_tasks(project_id):
    from datetime import datetime
    db = get_db()
    db.execute(
        "UPDATE tasks SET status='complete', completed_at=? WHERE project_id=? AND status != 'complete'",
        (datetime.utcnow().isoformat(), project_id),
    )
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
