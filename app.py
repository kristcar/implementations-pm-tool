from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response, session
from functools import wraps
from database import init_db, migrate_db
import models

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-prod"

import os as _os
def _read_file(name, default=""):
    try:
        return open(_os.path.join(_os.path.dirname(__file__), name)).read().strip()
    except Exception:
        return default

@app.context_processor
def inject_env():
    env = _read_file("environment.txt", "production")
    version = _read_file("version.txt", "0.2")
    return {"app_environment": env, "app_version": version}


def _is_late(project, today):
    """Return True if the project should be considered Late."""
    from datetime import date as _date
    if project["status"] != "active":
        return False
    if project["template_type"] == "store_optimization":
        # Late if not done within 40 days of assignment date
        try:
            assigned = _date.fromisoformat(project["contract_start_date"])
            return today > assigned + __import__("datetime").timedelta(days=40)
        except (ValueError, TypeError):
            return False
    else:
        # Late if SSD (contract_start_date) is in the past
        try:
            ssd = _date.fromisoformat(project["contract_start_date"])
            return ssd < today
        except (ValueError, TypeError):
            return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("current_user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("ie_name", "").strip()
        if name:
            session["current_user"] = name
            return redirect(url_for("my_projects"))
        flash("Please select your name.", "danger")
    ie_owners = models.list_ie_owners()
    return render_template("login.html", ie_owners=ie_owners)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.before_request
def setup():
    pass


# ── Projects ──────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return redirect(url_for("project_list"))


@app.route("/projects")
@login_required
def project_list():
    status = request.args.get("status", "all")
    from datetime import date
    today = date.today()
    projects = models.list_projects(status)
    ie_owners = models.list_ie_owners()
    enriched = []
    for p in projects:
        prog = models.project_progress(p["id"])
        overdue = models.overdue_task_count(p["id"])
        try:
            start = date.fromisoformat(p["contract_start_date"]) if p["contract_start_date"] else None
            elapsed = (today - start).days if start else None
        except ValueError:
            elapsed = None
        is_late = _is_late(p, today)
        enriched.append({"project": p, "progress": prog, "overdue": overdue, "elapsed": elapsed, "is_late": is_late})

    def sort_key(item):
        s = item["project"]["status"]
        if s == "active" and item["is_late"]:
            return 0  # Late first
        if s == "active":
            return 1  # On Time second
        if s == "complete":
            return 2  # Done third
        return 3      # Cancelled last

    enriched.sort(key=sort_key)
    return render_template("projects/list.html", projects=enriched, active_status=status, ie_owners=ie_owners, today=today)


@app.route("/my-projects")
@login_required
def my_projects():
    from datetime import date
    current_user = session["current_user"]
    status = request.args.get("status", "all")
    all_projects = models.list_projects(status)
    projects = [p for p in all_projects if (p["ie_owner"] or "").strip() == current_user.strip()]
    enriched = []
    today = date.today()
    for p in projects:
        prog = models.project_progress(p["id"])
        overdue = models.overdue_task_count(p["id"])
        try:
            target = date.fromisoformat(p["contract_start_date"]) if p["contract_start_date"] else None
            days_until = (target - today).days if target else None
        except ValueError:
            days_until = None
        enriched.append({"project": p, "progress": prog, "overdue": overdue, "days_until": days_until})
    all_enriched = []
    for p in [p for p in models.list_projects("all") if (p["ie_owner"] or "").strip() == current_user.strip()]:
        prog = models.project_progress(p["id"])
        overdue = models.overdue_task_count(p["id"])
        try:
            target = date.fromisoformat(p["contract_start_date"]) if p["contract_start_date"] else None
            days_until = (target - today).days if target else None
        except ValueError:
            days_until = None
        all_enriched.append({"project": p, "progress": prog, "overdue": overdue, "days_until": days_until})

    total = len(all_enriched)
    complete = sum(1 for i in all_enriched if i["project"]["status"] == "complete")
    active_items = [i for i in all_enriched if i["project"]["status"] == "active"]
    late = sum(1 for i in active_items if i["days_until"] is not None and i["days_until"] < 0)
    on_time = len(active_items) - late
    avg_pct = round(sum(i["progress"]["pct"] for i in all_enriched) / total) if total else 0

    stats = {"total": total, "on_time": on_time, "late": late, "complete": complete, "avg_pct": avg_pct}

    return render_template("projects/my_projects.html", projects=enriched, active_status=status, current_user=current_user, stats=stats)


@app.route("/ie-owners/add", methods=["POST"])
def ie_owner_add():
    name = request.form.get("name", "").strip()
    if name:
        models.add_ie_owner(name)
        flash(f"IE '{name}' added.", "success")
    redirect_to = request.form.get("redirect_to")
    return redirect(redirect_to or request.referrer or url_for("project_list"))


@app.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    ie_owners = models.list_ie_owners()
    if request.method == "POST":
        data = request.form.to_dict()
        if not data.get("name"):
            flash("Project name is required.", "danger")
            return render_template("projects/new.html", ie_owners=ie_owners)
        project_id = models.create_project(data)
        flash("Project created successfully.", "success")
        return redirect(url_for("project_detail", project_id=project_id))
    return render_template("projects/new.html", ie_owners=ie_owners)


@app.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = models.get_project(project_id)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("project_list"))
    groups = models.get_tasks_grouped(project_id)
    milestones = models.get_milestones(project_id)
    progress = models.project_progress(project_id)
    timeline_message = _timeline_message(project)
    from datetime import date
    today = date.today()
    is_late = _is_late(project, today)
    ie_owners = models.list_ie_owners()
    db = models.get_db()
    last_task = db.execute(
        "SELECT MAX(due_date) as last_due FROM tasks WHERE project_id=? AND due_date IS NOT NULL",
        (project_id,)
    ).fetchone()
    projected_end = last_task["last_due"] if last_task else None
    db.close()
    return render_template(
        "projects/detail.html",
        project=project,
        groups=groups,
        milestones=milestones,
        progress=progress,
        timeline_message=timeline_message,
        is_late=is_late,
        ie_owners=ie_owners,
        projected_end=projected_end,
    )


def _timeline_message(project):
    from datetime import date
    today = date.today()

    def parse(d):
        try:
            return date.fromisoformat(d) if d else None
        except ValueError:
            return None

    target  = parse(project["target_go_live_date"])
    actual  = parse(project["actual_go_live_date"])
    start   = parse(project["contract_start_date"])
    status  = project["status"]

    if status == "complete" and actual and target:
        diff = (target - actual).days
        if diff > 0:
            return f"Launched {diff} day{'s' if diff != 1 else ''} ahead of schedule."
        elif diff < 0:
            return f"Launched {abs(diff)} day{'s' if abs(diff) != 1 else ''} behind schedule."
        else:
            return "Launched on schedule."

    if status == "active" and target:
        diff = (target - today).days
        if diff > 0:
            return f"{diff} days until go-live."
        elif diff == 0:
            return "Go-live is today!"
        else:
            return f"Go-live target was {abs(diff)} days ago."

    if start:
        diff = (today - start).days
        return f"Day {diff} of implementation."

    return None


@app.route("/projects/<int:project_id>/edit", methods=["POST"])
@login_required
def project_edit(project_id):
    project = models.get_project(project_id)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("project_list"))
    # Start from existing values so partial forms (e.g. status-only) don't blank fields
    data = dict(project)
    data.update({k: v for k, v in request.form.to_dict().items() if v != ""})
    models.update_project(project_id, data)
    flash("Project updated.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/reschedule", methods=["POST"])
@login_required
def project_reschedule(project_id):
    from datetime import date, timedelta
    project = models.get_project(project_id)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("project_list"))
    new_target_str = request.form.get("new_target_date", "").strip()
    try:
        new_target = date.fromisoformat(new_target_str)
    except (ValueError, TypeError):
        flash("Invalid date.", "danger")
        return redirect(url_for("project_detail", project_id=project_id))

    today = date.today()
    if new_target <= today:
        flash("New target date must be in the future.", "danger")
        return redirect(url_for("project_detail", project_id=project_id))

    db = models.get_db()
    c = db.cursor()

    # Fetch all incomplete tasks with due dates, ordered by due date
    incomplete = c.execute(
        "SELECT id, due_date FROM tasks WHERE project_id=? AND status != 'complete' AND due_date IS NOT NULL ORDER BY due_date",
        (project_id,)
    ).fetchall()

    if incomplete:
        dates = [date.fromisoformat(r["due_date"]) for r in incomplete]
        earliest = min(dates)
        latest = max(dates)
        span_old = max((latest - earliest).days, 1)
        span_new = (new_target - today).days

        for row, d in zip(incomplete, dates):
            # Position of this task within the old span (0.0 to 1.0)
            ratio = (d - earliest).days / span_old
            new_due = today + timedelta(days=round(ratio * span_new))
            c.execute("UPDATE tasks SET due_date=? WHERE id=?", (new_due.isoformat(), row["id"]))

    # Update project go-live target
    c.execute("UPDATE projects SET target_go_live_date=? WHERE id=?", (new_target.isoformat(), project_id))

    # Recalculate milestone dates from task groups
    groups = c.execute("SELECT id FROM task_groups WHERE project_id=?", (project_id,)).fetchall()
    for g in groups:
        last = c.execute(
            "SELECT MAX(due_date) as last_due FROM tasks WHERE task_group_id=? AND due_date IS NOT NULL",
            (g["id"],)
        ).fetchone()
        if last and last["last_due"]:
            c.execute(
                "UPDATE milestones SET target_date=? WHERE project_id=? AND name=(SELECT name FROM task_groups WHERE id=?)",
                (last["last_due"], project_id, g["id"])
            )

    db.commit()
    db.close()

    count = len(incomplete)
    flash(f"Rescheduled {count} incomplete task{'s' if count != 1 else ''} to align with new go-live: {new_target.isoformat()}.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def project_delete(project_id):
    models.delete_project(project_id)
    flash("Project deleted.", "success")
    return redirect(url_for("project_list"))


# ── Timeline ──────────────────────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/timeline")
@login_required
def project_timeline(project_id):
    project = models.get_project(project_id)
    if not project:
        return redirect(url_for("project_list"))
    milestones = models.get_milestones(project_id)
    groups = models.get_tasks_grouped(project_id)

    from datetime import date
    start_str = project["contract_start_date"]
    end_str = project["target_go_live_date"]

    try:
        timeline_start = date.fromisoformat(start_str)
    except (ValueError, TypeError):
        timeline_start = date.today()

    try:
        timeline_end = date.fromisoformat(end_str)
    except (ValueError, TypeError):
        from datetime import timedelta
        timeline_end = timeline_start + timedelta(days=90)

    span_days = max((timeline_end - timeline_start).days, 1)

    def pct(d_str):
        try:
            d = date.fromisoformat(d_str)
            offset = (d - timeline_start).days
            return max(0, min(100, int(offset / span_days * 100)))
        except (ValueError, TypeError):
            return 0

    ms_positioned = []
    for m in milestones:
        ms_positioned.append({
            "milestone": m,
            "left_pct": pct(m["target_date"]),
        })

    return render_template(
        "projects/timeline.html",
        project=project,
        milestones=ms_positioned,
        groups=groups,
        timeline_start=timeline_start,
        timeline_end=timeline_end,
    )


# ── Milestones ────────────────────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/milestones/add", methods=["POST"])
def milestone_add(project_id):
    name = request.form.get("name", "").strip()
    target_date = request.form.get("target_date", "")
    if name:
        models.add_milestone(project_id, name, target_date)
    return redirect(url_for("project_timeline", project_id=project_id))


@app.route("/milestones/<int:milestone_id>/edit", methods=["POST"])
def milestone_edit(milestone_id):
    data = request.form.to_dict()
    models.update_milestone(milestone_id, data)
    project_id = request.form.get("project_id")
    return redirect(url_for("project_timeline", project_id=project_id))


@app.route("/milestones/<int:milestone_id>/delete", methods=["POST"])
def milestone_delete(milestone_id):
    project_id = request.form.get("project_id")
    models.delete_milestone(milestone_id)
    return redirect(url_for("project_timeline", project_id=project_id))


# ── Project Notes ─────────────────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/notes")
@login_required
def project_notes(project_id):
    project = models.get_project(project_id)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("project_list"))
    db = models.get_db()
    notes = db.execute(
        "SELECT * FROM project_notes WHERE project_id=? ORDER BY created_at ASC",
        (project_id,)
    ).fetchall()
    # Next 4 incomplete tasks in order
    next_tasks = db.execute(
        """SELECT t.title, t.owner, t.due_date, tg.name as group_name
           FROM tasks t
           LEFT JOIN task_groups tg ON t.task_group_id = tg.id
           WHERE t.project_id=? AND t.status != 'complete'
           ORDER BY t.due_date ASC, t.id ASC
           LIMIT 4""",
        (project_id,)
    ).fetchall()
    # Merchant/shared tasks for email block (from all incomplete, not just next 4)
    merchant_tasks = db.execute(
        """SELECT t.title, t.owner, t.due_date, tg.name as group_name
           FROM tasks t
           LEFT JOIN task_groups tg ON t.task_group_id = tg.id
           WHERE t.project_id=? AND t.status != 'complete' AND t.owner IN ('merchant','shared')
           ORDER BY t.due_date ASC, t.id ASC
           LIMIT 2""",
        (project_id,)
    ).fetchall()
    db.close()
    return render_template("projects/notes.html", project=project, notes=notes,
                           next_tasks=next_tasks, merchant_tasks=merchant_tasks)


@app.route("/projects/<int:project_id>/notes/add", methods=["POST"])
@login_required
def project_notes_add(project_id):
    message = request.form.get("message", "").strip()
    if message:
        db = models.get_db()
        db.execute(
            "INSERT INTO project_notes (project_id, author, message) VALUES (?,?,?)",
            (project_id, session.get("current_user", "Unknown"), message)
        )
        db.commit()
        db.close()
    return redirect(url_for("project_notes", project_id=project_id))


@app.route("/projects/<int:project_id>/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def project_notes_delete(project_id, note_id):
    db = models.get_db()
    db.execute("DELETE FROM project_notes WHERE id=? AND project_id=?", (note_id, project_id))
    db.commit()
    db.close()
    return redirect(url_for("project_notes", project_id=project_id))


# ── Tasks ─────────────────────────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/tasks/add", methods=["POST"])
def task_add(project_id):
    data = request.form.to_dict()
    models.add_task(project_id, data)
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/tasks/complete-all", methods=["POST"])
def tasks_complete_all(project_id):
    models.complete_all_tasks(project_id)
    flash("All tasks marked as complete.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/tasks/<int:task_id>/status", methods=["POST"])
def task_status(task_id):
    task = models.get_task(task_id)
    if not task:
        return jsonify({"error": "not found"}), 404
    new_status = "complete" if task["status"] != "complete" else "not_started"
    models.update_task_status(task_id, new_status)
    prog = models.project_progress(task["project_id"])
    return jsonify({"status": new_status, "progress": prog})


@app.route("/tasks/<int:task_id>/edit", methods=["POST"])
def task_edit(task_id):
    task = models.get_task(task_id)
    if not task:
        return jsonify({"error": "not found"}), 404
    data = request.form.to_dict()
    models.update_task(task_id, data)
    return redirect(url_for("project_detail", project_id=task["project_id"]))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def task_delete(task_id):
    task = models.get_task(task_id)
    project_id = task["project_id"] if task else None
    models.delete_task(task_id)
    if project_id:
        return redirect(url_for("project_detail", project_id=project_id))
    return redirect(url_for("project_list"))


@app.route("/projects/<int:project_id>/tasks/bulk-delete", methods=["POST"])
@login_required
def tasks_bulk_delete(project_id):
    ids = request.form.getlist("task_ids")
    for tid in ids:
        models.delete_task(int(tid))
    return redirect(url_for("project_detail", project_id=project_id))


# ── Proposal ──────────────────────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/proposal")
def project_proposal(project_id):
    project = models.get_project(project_id)
    if not project:
        return redirect(url_for("project_list"))
    groups = models.get_tasks_grouped(project_id)
    milestones = models.get_milestones(project_id)
    progress = models.project_progress(project_id)
    return render_template(
        "export/proposal.html",
        project=project,
        groups=groups,
        milestones=milestones,
        progress=progress,
    )


@app.route("/projects/<int:project_id>/proposal/export")
def project_proposal_export(project_id):
    project = models.get_project(project_id)
    if not project:
        return redirect(url_for("project_list"))
    groups = models.get_tasks_grouped(project_id)
    milestones = models.get_milestones(project_id)
    progress = models.project_progress(project_id)
    html = render_template(
        "export/proposal.html",
        project=project,
        groups=groups,
        milestones=milestones,
        progress=progress,
        standalone=True,
    )
    resp = make_response(html)
    filename = f"proposal-{project['name'].lower().replace(' ', '-')}.html"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    resp.headers["Content-Type"] = "text/html"
    return resp


# ── Reporting ─────────────────────────────────────────────────────────────────

def _build_snapshot():
    from datetime import date
    today = date.today()
    db = models.get_db()
    all_projects = models.list_projects("all")
    snapshot = []
    for p in all_projects:
        if p["status"] in ("cancelled", "complete"):
            continue
        pid = p["id"]
        row = db.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='complete' THEN 1 ELSE 0 END) as done FROM tasks WHERE project_id=?",
            (pid,)
        ).fetchone()
        total = row["total"] or 0
        done = row["done"] or 0
        pct = round((done / total) * 100) if total > 0 else 0
        current_milestone = db.execute(
            """SELECT tg.name FROM task_groups tg
               JOIN tasks t ON t.task_group_id = tg.id
               WHERE tg.project_id = ? AND t.status != 'complete'
               GROUP BY tg.id ORDER BY tg.sort_order LIMIT 1""",
            (pid,)
        ).fetchone()
        milestone = current_milestone["name"] if current_milestone else ("Complete" if total > 0 else "No tasks")
        last_task = db.execute(
            "SELECT MAX(due_date) as last_due FROM tasks WHERE project_id=? AND due_date IS NOT NULL",
            (pid,)
        ).fetchone()
        projected_end = last_task["last_due"] if last_task else None
        is_late = _is_late(p, today)
        snapshot.append({
            "id": pid,
            "merchant_name": p["merchant_name"] or p["name"],
            "ie_owner": p["ie_owner"] or "—",
            "template_type": p["template_type"],
            "target_go_live_date": p["target_go_live_date"] or "",
            "projected_end": projected_end or "",
            "milestone": milestone,
            "pct": pct,
            "is_late": is_late,
        })
    db.close()
    return snapshot, today.isoformat()


@app.route("/weekly-snapshot")
@login_required
def weekly_snapshot():
    snapshot, today = _build_snapshot()
    ie_filter = request.args.get("ie", session.get("current_user", ""))
    if ie_filter:
        snapshot = [p for p in snapshot if p["ie_owner"] == ie_filter]
    snapshot.sort(key=lambda x: (not x["is_late"], x["merchant_name"].lower()))
    ie_owners = models.list_ie_owners()
    return render_template("reporting/weekly_snapshot.html", snapshot=snapshot, today=today,
                           ie_filter=ie_filter, ie_owners=ie_owners)


@app.route("/weekly-snapshot/csv")
@login_required
def weekly_snapshot_csv():
    import csv, io
    snapshot, today = _build_snapshot()
    ie_filter = request.args.get("ie", "")
    if ie_filter:
        snapshot = [p for p in snapshot if p["ie_owner"] == ie_filter]
    snapshot.sort(key=lambda x: (not x["is_late"], x["merchant_name"].lower()))

    tpl_labels = {
        "optimized_activation": "Recharge Optimized Activation",
        "optimized_subscription_migration": "Recharge Optimized Subscription Migration",
        "recharge_strategic_migration": "Recharge Strategic Implementation",
        "skio": "Skio",
        "store_optimization": "Store Optimization",
    }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Merchant", "IE Owner", "Template", "Current Milestone", "Projected End Date", "% Complete", "Status"])
    for p in snapshot:
        writer.writerow([
            p["merchant_name"],
            p["ie_owner"],
            tpl_labels.get(p["template_type"], p["template_type"] or ""),
            p["milestone"],
            p["projected_end"],
            f"{p['pct']}%",
            "Late" if p["is_late"] else "On Time",
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = f"attachment; filename=status-board-{today}.csv"
    return response


@app.route("/reporting")
@login_required
def reporting():
    from datetime import date
    today = date.today()
    all_projects = models.list_projects("all")

    active_late = 0
    active_on_time = 0
    done = 0

    pathway_labels = {
        "optimized_activation": "Recharge Optimized Activation",
        "optimized_subscription_migration": "Recharge Optimized Subscription Migration",
        "recharge_strategic_migration": "Recharge Strategic Implementation",
        "skio": "Skio",
        "store_optimization": "Store Optimization",
        "standard": "Recharge Optimized Activation",
        "enterprise": "Recharge Strategic Implementation",
    }

    active_by_pathway = {}
    done_by_pathway = {}

    for p in all_projects:
        if p["status"] == "cancelled":
            continue
        label = pathway_labels.get(p["template_type"] or "", p["template_type"] or "Unknown")
        if p["status"] == "active":
            try:
                target = date.fromisoformat(p["contract_start_date"]) if p["contract_start_date"] else None
                is_late = target is not None and target < today
            except ValueError:
                is_late = False
            if is_late:
                active_late += 1
            else:
                active_on_time += 1
            active_by_pathway[label] = active_by_pathway.get(label, 0) + 1
        elif p["status"] == "complete":
            done += 1
            done_by_pathway[label] = done_by_pathway.get(label, 0) + 1

    # Project count by IE and pathway (active only)
    ie_owners_list = sorted(set(
        p["ie_owner"] for p in all_projects
        if p["status"] == "active" and p["ie_owner"]
    ))
    ie_by_pathway = {pw: {ie: 0 for ie in ie_owners_list} for pw in [
        "Recharge Optimized Activation", "Recharge Optimized Subscription Migration", "Recharge Strategic Implementation", "Skio", "Store Optimization"
    ]}
    ie_counts = {ie: 0 for ie in ie_owners_list}
    for p in all_projects:
        if p["status"] != "active":
            continue
        owner = p["ie_owner"] or "Unassigned"
        label = pathway_labels.get(p["template_type"] or "", "Unknown")
        ie_counts[owner] = ie_counts.get(owner, 0) + 1
        if owner in ie_owners_list and label in ie_by_pathway:
            ie_by_pathway[label][owner] += 1

    # Projects launching in next 14 days by IE and pathway
    from datetime import timedelta
    pathways = ["Recharge Optimized Activation", "Recharge Optimized Subscription Migration", "Recharge Strategic Implementation", "Skio", "Store Optimization"]
    upcoming_ies = sorted(set(
        p["ie_owner"] or "Unassigned" for p in all_projects
        if p["status"] == "active" and p["ie_owner"]
    ))
    upcoming_by_pathway = {pw: {ie: 0 for ie in upcoming_ies} for pw in pathways}
    for p in all_projects:
        if p["status"] != "active":
            continue
        try:
            target = date.fromisoformat(p["contract_start_date"]) if p["contract_start_date"] else None
        except ValueError:
            target = None
        if not target:
            continue
        days = (target - today).days
        if 0 <= days <= 14:
            owner = p["ie_owner"] or "Unassigned"
            label = pathway_labels.get(p["template_type"] or "", "Unknown")
            if owner in upcoming_ies and label in upcoming_by_pathway:
                upcoming_by_pathway[label][owner] += 1

    return render_template(
        "reporting/dashboard.html",
        active_late=active_late,
        active_on_time=active_on_time,
        done=done,
        active_by_pathway=active_by_pathway,
        done_by_pathway=done_by_pathway,
        ie_counts=ie_counts,
        ie_owners_list=ie_owners_list,
        ie_by_pathway=ie_by_pathway,
        upcoming_ies=upcoming_ies,
        upcoming_by_pathway=upcoming_by_pathway,
        pathways=pathways,
    )


# ── Reporting API ─────────────────────────────────────────────────────────

@app.route("/api/reporting/engaged")
@login_required
def api_engaged():
    from datetime import date
    start_str = request.args.get("start", "")
    end_str   = request.args.get("end", "")
    if not start_str or not end_str:
        return jsonify({"error": "start and end required"}), 400

    ie_filter = request.args.get("ie", "").strip()

    from database import get_db
    db = get_db()

    if ie_filter:
        rows = db.execute("""
            SELECT DISTINCT p.id, p.merchant_name, p.name
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            WHERE p.status = 'active' AND p.ie_owner = ?
              AND (
                (DATE(p.updated_at) BETWEEN ? AND ?)
                OR (t.completed_at IS NOT NULL AND DATE(t.completed_at) BETWEEN ? AND ?)
              )
        """, (ie_filter, start_str, end_str, start_str, end_str)).fetchall()
        total_active = db.execute(
            "SELECT COUNT(*) as cnt FROM projects WHERE status = 'active' AND ie_owner = ?",
            (ie_filter,)
        ).fetchone()["cnt"]
    else:
        rows = db.execute("""
            SELECT DISTINCT p.id, p.merchant_name, p.name
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            WHERE p.status = 'active'
              AND (
                (DATE(p.updated_at) BETWEEN ? AND ?)
                OR (t.completed_at IS NOT NULL AND DATE(t.completed_at) BETWEEN ? AND ?)
              )
        """, (start_str, end_str, start_str, end_str)).fetchall()
        total_active = db.execute(
            "SELECT COUNT(*) as cnt FROM projects WHERE status = 'active'"
        ).fetchone()["cnt"]

    engaged_ids = {r["id"] for r in rows}

    # Disengaged = active projects NOT in the engaged set
    all_active = db.execute(
        "SELECT id, merchant_name, name, ie_owner, updated_at FROM projects WHERE status = 'active'" +
        (" AND ie_owner = ?" if ie_filter else ""),
        (ie_filter,) if ie_filter else ()
    ).fetchall()

    db.close()

    disengaged = [
        {
            "name": r["merchant_name"] or r["name"],
            "ie": r["ie_owner"] or "",
            "updated": r["updated_at"][:10] if r["updated_at"] else "—",
        }
        for r in all_active if r["id"] not in engaged_ids
    ]

    engaged = len(engaged_ids)
    pct = round(engaged / total_active * 100) if total_active else 0
    return jsonify({"engaged": engaged, "total": total_active, "pct": pct, "disengaged": disengaged})


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/projects")
def api_projects():
    projects = models.list_projects()
    return jsonify([dict(p) for p in projects])


@app.route("/api/projects/<int:project_id>/progress")
def api_progress(project_id):
    return jsonify(models.project_progress(project_id))


if __name__ == "__main__":
    init_db()
    migrate_db()
    import argparse
    parser = argparse.ArgumentParser()
    env = _read_file("environment.txt", "production")
    default_port = 5051 if env == "sandbox" else 5050
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()
    app.run(debug=True, port=args.port)
