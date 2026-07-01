from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from database import init_db
import models

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-prod"


@app.before_request
def setup():
    pass


# ── Projects ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("project_list"))


@app.route("/projects")
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
        enriched.append({"project": p, "progress": prog, "overdue": overdue, "elapsed": elapsed})

    def sort_key(item):
        s = item["project"]["status"]
        if s == "active" and item["overdue"] > 0:
            return 0  # Late first
        if s == "active":
            return 1  # Active second
        if s == "complete":
            return 2  # Done third
        return 3      # Cancelled last

    enriched.sort(key=sort_key)
    return render_template("projects/list.html", projects=enriched, active_status=status, ie_owners=ie_owners, today=today)


CURRENT_USER = "Kristin Caras"


@app.route("/my-projects")
def my_projects():
    from datetime import date
    status = request.args.get("status", "all")
    all_projects = models.list_projects(status)
    projects = [p for p in all_projects if (p["ie_owner"] or "").strip() == CURRENT_USER.strip()]
    enriched = []
    today = date.today()
    for p in projects:
        prog = models.project_progress(p["id"])
        overdue = models.overdue_task_count(p["id"])
        try:
            target = date.fromisoformat(p["target_go_live_date"]) if p["target_go_live_date"] else None
            days_until = (target - today).days if target else None
        except ValueError:
            days_until = None
        enriched.append({"project": p, "progress": prog, "overdue": overdue, "days_until": days_until})
    all_enriched = []
    for p in [p for p in models.list_projects("all") if (p["ie_owner"] or "").strip() == CURRENT_USER.strip()]:
        prog = models.project_progress(p["id"])
        overdue = models.overdue_task_count(p["id"])
        try:
            target = date.fromisoformat(p["target_go_live_date"]) if p["target_go_live_date"] else None
            days_until = (target - today).days if target else None
        except ValueError:
            days_until = None
        all_enriched.append({"project": p, "progress": prog, "overdue": overdue, "days_until": days_until})

    total = len(all_enriched)
    complete = sum(1 for i in all_enriched if i["project"]["status"] == "complete")
    active_items = [i for i in all_enriched if i["project"]["status"] == "active"]
    late = sum(1 for i in active_items if i["overdue"] > 0 or (i["days_until"] is not None and i["days_until"] < 0))
    on_time = len(active_items) - late
    avg_pct = round(sum(i["progress"]["pct"] for i in all_enriched) / total) if total else 0

    stats = {"total": total, "on_time": on_time, "late": late, "complete": complete, "avg_pct": avg_pct}

    return render_template("projects/my_projects.html", projects=enriched, active_status=status, current_user=CURRENT_USER, stats=stats)


@app.route("/projects/new", methods=["GET", "POST"])
def project_new():
    if request.method == "POST":
        data = request.form.to_dict()
        if not data.get("name"):
            flash("Project name is required.", "danger")
            return render_template("projects/new.html")
        project_id = models.create_project(data)
        flash("Project created successfully.", "success")
        return redirect(url_for("project_detail", project_id=project_id))
    return render_template("projects/new.html")


@app.route("/projects/<int:project_id>")
def project_detail(project_id):
    project = models.get_project(project_id)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("project_list"))
    groups = models.get_tasks_grouped(project_id)
    milestones = models.get_milestones(project_id)
    progress = models.project_progress(project_id)
    timeline_message = _timeline_message(project)
    return render_template(
        "projects/detail.html",
        project=project,
        groups=groups,
        milestones=milestones,
        progress=progress,
        timeline_message=timeline_message,
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
def project_edit(project_id):
    data = request.form.to_dict()
    models.update_project(project_id, data)
    flash("Project updated.", "success")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def project_delete(project_id):
    models.delete_project(project_id)
    flash("Project deleted.", "success")
    return redirect(url_for("project_list"))


# ── Timeline ──────────────────────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/timeline")
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


# ── Tasks ─────────────────────────────────────────────────────────────────────

@app.route("/projects/<int:project_id>/tasks/add", methods=["POST"])
def task_add(project_id):
    data = request.form.to_dict()
    models.add_task(project_id, data)
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
    app.run(debug=True, port=5050)
