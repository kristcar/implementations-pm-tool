from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response, session
from functools import wraps
import database
from database import init_db, migrate_db
import models

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-prod"

@app.template_filter("fmtdate")
def fmtdate(value):
    if not value:
        return "—"
    try:
        parts = str(value)[:10].split("-")
        return f"{parts[1]}/{parts[2]}/{parts[0]}"
    except Exception:
        return value

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
            resp = redirect(url_for("project_list"))
            resp.set_cookie("last_user", name, max_age=60*60*24*365)
            return resp
        flash("Please select your name.", "danger")
    ie_owners = models.list_ie_owners()
    last_user = request.cookies.get("last_user", "")
    return render_template("login.html", ie_owners=ie_owners, last_user=last_user)


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
    timing = request.args.get("timing", "all")  # all | on_time | late
    from datetime import date
    today = date.today()
    projects = models.list_projects(status)
    enriched = []
    for p in projects:
        prog = models.project_progress(p["id"])
        overdue = models.overdue_task_count(p["id"])
        try:
            created = date.fromisoformat(p["created_at"][:10]) if p["created_at"] else None
            elapsed = (today - created).days if created else None
        except ValueError:
            elapsed = None
        is_late = _is_late(p, today)
        enriched.append({"project": p, "progress": prog, "overdue": overdue, "elapsed": elapsed, "is_late": is_late})

    if timing == "late":
        enriched = [i for i in enriched if i["is_late"]]
    elif timing == "on_time":
        enriched = [i for i in enriched if not i["is_late"]]

    def sort_key(item):
        s = item["project"]["status"]
        if s == "active" and item["is_late"]:
            return 0
        if s == "active":
            return 1
        if s == "complete":
            return 2
        return 3

    enriched.sort(key=sort_key)
    return render_template("projects/list.html", projects=enriched, active_status=status, active_timing=timing, today=today)


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


@app.route("/projects/<int:project_id>/export-csv")
@login_required
def project_export_csv(project_id):
    import csv, io
    from datetime import date
    project = models.get_project(project_id)
    if not project:
        return redirect(url_for("project_list"))
    db = models.get_db()
    groups = db.execute(
        "SELECT id, name FROM task_groups WHERE project_id=? ORDER BY sort_order",
        (project_id,)
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Milestone", "Task", "Owner", "Due Date", "Status"])
    for g in groups:
        tasks = db.execute(
            "SELECT title, owner, due_date, status FROM tasks WHERE task_group_id=? ORDER BY sort_order",
            (g["id"],)
        ).fetchall()
        if not tasks:
            continue
        for i, t in enumerate(tasks):
            due = t["due_date"] or ""
            if due:
                try:
                    parts = due.split("-")
                    due = f"{parts[1]}/{parts[2]}/{parts[0]}"
                except Exception:
                    pass
            owner = {"ie": "IE", "merchant": "Merchant", "shared": "Shared"}.get(t["owner"], t["owner"] or "")
            status = "Complete" if t["status"] == "complete" else "Open"
            milestone_label = g["name"] if i == 0 else ""
            writer.writerow([milestone_label, t["title"], owner, due, status])
        writer.writerow([])
    db.close()
    merchant = (project["merchant_name"] or project["name"]).replace(" ", "-")
    today = date.today().isoformat()
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = f"attachment; filename={merchant}-project-plan-{today}.csv"
    return response


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

    # Quick Actions data
    from datetime import date as _dt_date
    _today_iso = _dt_date.today().isoformat()

    overdue_merchant_tasks = db.execute(
        """SELECT t.title, t.owner, t.due_date, tg.name as group_name
           FROM tasks t
           LEFT JOIN task_groups tg ON t.task_group_id = tg.id
           WHERE t.project_id=? AND t.status != 'complete'
             AND t.owner IN ('merchant','shared') AND t.due_date < ?
           ORDER BY t.due_date ASC""",
        (project_id, _today_iso)
    ).fetchall()

    last_completed_group = db.execute(
        """SELECT tg.id, tg.name,
                  COUNT(t.id) as total,
                  SUM(CASE WHEN t.status='complete' THEN 1 ELSE 0 END) as done
           FROM task_groups tg
           JOIN tasks t ON t.task_group_id = tg.id
           WHERE tg.project_id=?
           GROUP BY tg.id
           HAVING total > 0 AND done = total
           ORDER BY tg.sort_order DESC
           LIMIT 1""",
        (project_id,)
    ).fetchone()

    current_milestone_row = db.execute(
        """SELECT tg.name FROM task_groups tg
           JOIN tasks t ON t.task_group_id = tg.id
           WHERE tg.project_id=? AND t.status != 'complete'
           GROUP BY tg.id
           ORDER BY tg.sort_order ASC
           LIMIT 1""",
        (project_id,)
    ).fetchone()
    current_milestone_name = current_milestone_row["name"] if current_milestone_row else None

    db.close()

    _progress = models.project_progress(project_id)
    project_pct = _progress["pct"]
    _go_live = project["target_go_live_date"]
    is_late = False
    if _go_live:
        try:
            is_late = _dt_date.today() > _dt_date.fromisoformat(_go_live[:10]) and project_pct < 100
        except Exception:
            pass

    # Fetch support article for each merchant task
    import urllib.request, urllib.parse, json as _json, re as _re
    is_skio = project["template_type"] == "skio"

    _skio_articles = None
    def _load_skio_articles():
        nonlocal _skio_articles
        if _skio_articles is not None:
            return _skio_articles
        try:
            req = urllib.request.Request("https://help.skio.com/llms.txt", headers={"Accept": "text/plain", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                text = r.read().decode("utf-8")
            entries = []
            for line in text.splitlines():
                m = _re.match(r'-\s+\[([^\]]+)\]\(([^)]+)\)', line)
                if m:
                    entries.append({"title": m.group(1), "url": m.group(2).replace(".md", "")})
            _skio_articles = entries
        except Exception:
            _skio_articles = []
        return _skio_articles

    def _skio_article_search(task_title):
        articles = _load_skio_articles()
        if not articles:
            return None
        # Use 5-char prefix stems so "migration" matches "migrations" etc.
        def stems(text):
            return set(w.lower()[:6] for w in _re.split(r'\W+', text) if len(w) > 4)
        task_stems = stems(task_title)
        best, best_score = None, 0
        for a in articles:
            score = len(task_stems & stems(a["title"]))
            if score > best_score:
                best, best_score = a, score
        return best if best_score > 0 else None

    def _fetch_support_article(title):
        if is_skio:
            return _skio_article_search(title)
        try:
            q = urllib.parse.urlencode({"query": title, "per_page": 1})
            url = f"https://support.getrecharge.com/api/v2/help_center/articles/search.json?{q}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data = _json.loads(r.read())
            results = data.get("results", [])
            if results:
                return {"title": results[0]["title"], "url": results[0]["html_url"]}
        except Exception:
            pass
        return None

    _migration_fallback = {"title": "Migrating to Recharge", "url": "https://support.getrecharge.com/hc/en-us/articles/360008830853-Migrating-to-Recharge"}
    merchant_tasks_with_articles = []
    for t in merchant_tasks:
        article = _fetch_support_article(t["title"])
        if not article and any(kw in t["title"].upper() for kw in ("DMS", "MIGR8")):
            article = _migration_fallback
        merchant_tasks_with_articles.append({"task": t, "article": article})

    next_tasks_with_articles = []
    for t in next_tasks:
        article = _fetch_support_article(t["title"])
        if not article and any(kw in t["title"].upper() for kw in ("DMS", "MIGR8")):
            article = _migration_fallback
        next_tasks_with_articles.append({"task": t, "article": article})

    # Flagged notes for Risk Flag
    _risk_keywords = (
        # clear blockers
        "block","stuck","delay","risk","issue","concern","escalat","problem",
        "behind","unresponsive","no response","urgent","critical","overdue",
        "paused","on hold","cancel","churn","unhappy","frustrat",
        # uncertainty / confusion
        "not sure","unclear","confusion","waiting on","waiting for",
        # technical problems
        "bug","error","broken","fix","fail","crash","not working","doesn't work",
        "does not work","theme","widget","liquid","conflict","sandbox",
        # explicit action flags
        "follow up","followup","reach out","sign off","approval needed",
        "decision needed","todo","to-do",
    )
    all_notes_for_risk = db.execute(
        "SELECT message, author, created_at FROM project_notes WHERE project_id=? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall() if False else notes  # reuse already-fetched notes (sorted ASC, reverse below)
    flagged_notes = []
    for n in sorted(notes, key=lambda x: x["created_at"], reverse=True):
        if any(kw in n["message"].lower() for kw in _risk_keywords):
            msg = n["message"].strip().replace("\n", " ")
            if len(msg) > 160:
                msg = msg[:160] + "..."
            flagged_notes.append({"text": msg, "author": n["author"], "date": n["created_at"][:10]})

    # Days since last note
    last_note_date_str = notes[-1]["created_at"][:10] if notes else None

    embedded = request.args.get("embedded") == "1"
    panel = request.args.get("panel", "notes")
    template = "projects/notes_embedded.html" if embedded else "projects/notes.html"
    return render_template(template, project=project, notes=notes,
                           next_tasks=next_tasks, merchant_tasks=merchant_tasks,
                           merchant_tasks_with_articles=merchant_tasks_with_articles,
                           next_tasks_with_articles=next_tasks_with_articles,
                           panel=panel,
                           overdue_merchant_tasks=overdue_merchant_tasks,
                           last_completed_group=last_completed_group,
                           current_milestone_name=current_milestone_name,
                           project_pct=project_pct,
                           is_late=is_late,
                           flagged_notes=flagged_notes,
                           last_note_date_str=last_note_date_str)


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
    embedded = request.args.get("embedded") == "1"
    return redirect(url_for("project_notes", project_id=project_id, embedded="1" if embedded else None))


@app.route("/projects/<int:project_id>/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def project_notes_delete(project_id, note_id):
    db = models.get_db()
    db.execute("DELETE FROM project_notes WHERE id=? AND project_id=?", (note_id, project_id))
    db.commit()
    db.close()
    embedded = request.form.get("embedded") or request.args.get("embedded")
    panel = request.form.get("panel") or request.args.get("panel", "notes")
    return redirect(url_for("project_notes", project_id=project_id,
                            embedded=embedded or None, panel=panel if embedded else None))


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

@app.route("/projects/<int:project_id>/complete-all-and-close", methods=["POST"])
@login_required
def project_complete_all_and_close(project_id):
    models.complete_all_tasks(project_id)
    db = database.get_db()
    db.execute("UPDATE projects SET status='complete', updated_at=CURRENT_TIMESTAMP WHERE id=?", (project_id,))
    db.commit()
    db.close()
    flash("All tasks marked complete and project closed.", "success")
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
        last_note_row = db.execute(
            "SELECT message, created_at FROM project_notes WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
            (pid,)
        ).fetchone()
        last_note = last_note_row["message"] if last_note_row else ""
        last_note_date = last_note_row["created_at"][:10] if last_note_row and last_note_row["created_at"] else ""

        # AI Status Update
        all_notes = db.execute(
            "SELECT message, author FROM project_notes WHERE project_id=? ORDER BY created_at DESC",
            (pid,)
        ).fetchall()
        next_task_row = db.execute(
            """SELECT t.title, t.owner FROM tasks t
               LEFT JOIN task_groups tg ON tg.id = t.task_group_id
               WHERE t.project_id=? AND t.status != 'complete'
               ORDER BY COALESCE(tg.sort_order,0), t.sort_order LIMIT 1""",
            (pid,)
        ).fetchone()
        overdue_ct = db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE project_id=? AND status!='complete' AND owner IN ('merchant','shared') AND due_date < ?",
            (pid, today.isoformat())
        ).fetchone()["cnt"] or 0

        _ai_flag_kw = (
            "block","stuck","wait","delay","risk","issue","concern","escalat","problem",
            "behind","slow","unresponsive","no response","follow up","followup","urgent",
            "critical","missing","overdue","pending","paused","hold","cancel","churn",
            "unhappy","frustrat","not sure","unclear","confusion","question","need","help",
            "bug","error","broken","fix","fail","crash","not working","doesn't work",
            "does not work","theme","code","script","widget","liquid","css","js",
            "javascript","api","integration","conflict","install","migration","import",
            "export","data","test","sandbox","action","todo","to do","to-do","reach out",
            "contact","email","call","meeting","review","approve","approval","sign off",
            "decision","confirm","update","change","request",
        )
        status_str = "behind schedule" if is_late else "on track"
        ai_parts = [f"{p['merchant_name'] or p['name']} is {status_str} at {pct}% complete."]
        if milestone not in ("Complete", "No tasks"):
            ai_parts.append(f"Currently in: {milestone}.")
        if next_task_row:
            owner_lbl = "IE" if next_task_row["owner"] == "ie" else "Merchant"
            ai_parts.append(f"Next up: {next_task_row['title']} ({owner_lbl}).")
        if overdue_ct:
            ai_parts.append(f"⚠️ {overdue_ct} overdue merchant task{'s' if overdue_ct != 1 else ''}.")
        flagged = []
        for n in all_notes:
            if any(kw in n["message"].lower() for kw in _ai_flag_kw):
                msg = n["message"].strip().replace("\n", " ")
                if len(msg) > 150:
                    msg = msg[:150] + "..."
                flagged.append(f'"{msg}" — {n["author"]}')
        if flagged:
            ai_parts.append("Notes: " + " | ".join(flagged[:3]))
        ai_status = " ".join(ai_parts)

        snapshot.append({
            "id": pid,
            "merchant_name": p["merchant_name"] or p["name"],
            "ie_owner": p["ie_owner"] or "—",
            "template_type": p["template_type"],
            "contract_start_date": p["contract_start_date"] or "",
            "target_go_live_date": p["target_go_live_date"] or "",
            "projected_end": projected_end or "",
            "milestone": milestone,
            "pct": pct,
            "is_late": is_late,
            "last_note": last_note,
            "last_note_date": last_note_date,
            "ai_status": ai_status,
            "salesforce_link": p["salesforce_link"] or "",
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
    writer.writerow(["Merchant", "Salesforce Link", "IE Owner", "Template", "SSD", "Current Milestone", "Go-Live Target", "Final Task Due Date", "% Complete", "Status", "Last Note", "Last Note Date", "Runway AI Status Update"])
    for p in snapshot:
        _sf = p.get("salesforce_link") or ""
        _sf_cell = f'=HYPERLINK("{_sf}","Salesforce")' if _sf else ""
        writer.writerow([
            p["merchant_name"],
            _sf_cell,
            p["ie_owner"],
            tpl_labels.get(p["template_type"], p["template_type"] or ""),
            p["contract_start_date"],
            p["milestone"],
            p["target_go_live_date"],
            p["projected_end"],
            f"{p['pct']}%",
            "Late" if p["is_late"] else "On Time",
            p["last_note"],
            p["last_note_date"],
            p.get("ai_status", ""),
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = f"attachment; filename=status-board-{today}.csv"
    return response


@app.route("/weekly-snapshot/ooo-csv")
@login_required
def weekly_snapshot_ooo_csv():
    import csv, io
    snapshot, today = _build_snapshot()
    ie_filter = request.args.get("ie", "")
    return_date = request.args.get("return_date", "")
    _tasks_param = request.args.get("tasks", "5")
    task_limit = None if (return_date or _tasks_param == "all") else max(1, min(200, int(_tasks_param)))
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

    from datetime import date as _dt_date
    _today_iso = _dt_date.today().isoformat()

    db = models.get_db()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Merchant", "Salesforce Link", "IE Owner", "Template", "SSD", "Current Milestone",
        "Go-Live Target", "Final Task Due Date", "% Complete", "Status",
        "Runway AI Status Update",
        "Last Note", "Last Note Date",
        "Immediate Next Task", "Task Owner", "Done?"
    ])
    for p in snapshot:
        if return_date:
            tasks = db.execute(
                """SELECT t.title, t.owner FROM tasks t
                   LEFT JOIN task_groups tg ON tg.id = t.task_group_id
                   WHERE t.project_id = ? AND t.status != 'complete'
                     AND (t.due_date IS NULL OR t.due_date <= ?)
                   ORDER BY COALESCE(tg.sort_order, 0), t.sort_order""",
                (p["id"], return_date)
            ).fetchall()
        else:
            if task_limit is None:
                tasks = db.execute(
                    """SELECT t.title, t.owner FROM tasks t
                       LEFT JOIN task_groups tg ON tg.id = t.task_group_id
                       WHERE t.project_id = ? AND t.status != 'complete'
                       ORDER BY COALESCE(tg.sort_order, 0), t.sort_order""",
                    (p["id"],)
                ).fetchall()
            else:
                tasks = db.execute(
                    """SELECT t.title, t.owner FROM tasks t
                       LEFT JOIN task_groups tg ON tg.id = t.task_group_id
                       WHERE t.project_id = ? AND t.status != 'complete'
                       ORDER BY COALESCE(tg.sort_order, 0), t.sort_order
                       LIMIT ?""",
                    (p["id"], task_limit)
                ).fetchall()

        # Build project summary
        recent_notes = db.execute(
            """SELECT message, author, created_at FROM project_notes
               WHERE project_id = ? ORDER BY created_at DESC""",
            (p["id"],)
        ).fetchall()
        overdue_merchant_count = db.execute(
            """SELECT COUNT(*) as cnt FROM tasks
               WHERE project_id=? AND status != 'complete'
               AND owner IN ('merchant','shared') AND due_date < ?""",
            (p["id"], _today_iso)
        ).fetchone()["cnt"] or 0

        status_str = "behind schedule" if p["is_late"] else "on track"
        summary_parts = [
            f"{p['merchant_name']} is {status_str} at {p['pct']}% complete.",
        ]
        if p["milestone"] and p["milestone"] not in ("Complete", "No tasks"):
            summary_parts.append(f"Currently in: {p['milestone']}.")
        if p["target_go_live_date"]:
            gl_parts = p["target_go_live_date"].split("-")
            gl_fmt = f"{gl_parts[1]}/{gl_parts[2]}/{gl_parts[0]}" if len(gl_parts) == 3 else p["target_go_live_date"]
            summary_parts.append(f"Go-live target: {gl_fmt}.")
        if tasks:
            next_task = tasks[0]
            owner_label = "IE" if next_task["owner"] == "ie" else "Merchant"
            summary_parts.append(f"Next up: {next_task['title']} ({owner_label}).")
        if overdue_merchant_count:
            summary_parts.append(f"⚠️ {overdue_merchant_count} overdue merchant task{'s' if overdue_merchant_count != 1 else ''} - follow up needed.")
        if recent_notes:
            _flag_keywords = (
                # blockers & status
                "block", "stuck", "wait", "delay", "risk", "issue", "concern",
                "escalat", "problem", "behind", "slow", "unresponsive", "no response",
                "follow up", "followup", "urgent", "critical", "missing", "overdue",
                "pending", "paused", "hold", "cancel", "churn", "unhappy", "frustrat",
                "not sure", "unclear", "confusion", "question", "need", "help",
                # technical
                "bug", "error", "broken", "fix", "fail", "crash", "not working",
                "doesn't work", "does not work", "theme", "code", "script", "widget",
                "liquid", "css", "js", "javascript", "api", "integration", "conflict",
                "install", "migration", "import", "export", "data", "test", "sandbox",
                # action items
                "action", "todo", "to do", "to-do", "reach out", "contact", "email",
                "call", "meeting", "review", "approve", "approval", "sign off",
                "decision", "confirm", "update", "change", "request",
            )
            flagged = []
            for n in recent_notes:
                msg_lower = n["message"].lower()
                if any(kw in msg_lower for kw in _flag_keywords):
                    msg = n["message"].strip().replace("\n", " ")
                    if len(msg) > 150:
                        msg = msg[:150] + "..."
                    flagged.append(f'"{msg}" - {n["author"]}')
            if flagged:
                summary_parts.append("Watch out for: " + " | ".join(flagged[:3]))
        summary = " ".join(summary_parts)

        _sf = p.get("salesforce_link") or ""
        _sf_cell = f'=HYPERLINK("{_sf}","Salesforce")' if _sf else ""
        project_cols = [
            p["merchant_name"],
            _sf_cell,
            p["ie_owner"],
            tpl_labels.get(p["template_type"], p["template_type"] or ""),
            p["contract_start_date"],
            p["milestone"],
            p["target_go_live_date"],
            p["projected_end"],
            f"{p['pct']}%",
            "Late" if p["is_late"] else "On Time",
            summary,
            p["last_note"],
            p["last_note_date"],
        ]
        if not tasks:
            writer.writerow(project_cols + ["", "", ""])
        else:
            for i, t in enumerate(tasks):
                owner_label = "IE" if t["owner"] == "ie" else "Merchant"
                row = (project_cols if i == 0 else [""] * len(project_cols))
                writer.writerow(list(row) + [t["title"], owner_label, ""])
        writer.writerow([])
    db.close()

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = f"attachment; filename=ooo-report-{today}.csv"
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
            LEFT JOIN project_notes n ON n.project_id = p.id
            WHERE p.status = 'active' AND p.ie_owner = ?
              AND (
                (DATE(p.updated_at) BETWEEN ? AND ?)
                OR (t.completed_at IS NOT NULL AND DATE(t.completed_at) BETWEEN ? AND ?)
                OR (DATE(n.created_at) BETWEEN ? AND ?)
              )
        """, (ie_filter, start_str, end_str, start_str, end_str, start_str, end_str)).fetchall()
        total_active = db.execute(
            "SELECT COUNT(*) as cnt FROM projects WHERE status = 'active' AND ie_owner = ?",
            (ie_filter,)
        ).fetchone()["cnt"]
    else:
        rows = db.execute("""
            SELECT DISTINCT p.id, p.merchant_name, p.name
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            LEFT JOIN project_notes n ON n.project_id = p.id
            WHERE p.status = 'active'
              AND (
                (DATE(p.updated_at) BETWEEN ? AND ?)
                OR (t.completed_at IS NOT NULL AND DATE(t.completed_at) BETWEEN ? AND ?)
                OR (DATE(n.created_at) BETWEEN ? AND ?)
              )
        """, (start_str, end_str, start_str, end_str, start_str, end_str)).fetchall()
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
            "updated": fmtdate(r["updated_at"][:10]) if r["updated_at"] else "—",
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
