from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models import User, Task, StudyPlan, RescheduleHistory, TaskDependency
from app.services.core import DEFAULTS
from app.services.planner import PlannerService, next_slot


def test_slots_respect_timezone_days_and_dst():
    profile = {**DEFAULTS, "timezone": "Europe/Bucharest", "study_days": [7], "study_time": "19:00"}
    now = datetime(2026, 3, 28, 20, tzinfo=timezone.utc)
    slot = next_slot(profile, now)
    assert slot.astimezone(ZoneInfo("Europe/Bucharest")).hour == 19
    assert slot.isoweekday() == 7
    assert slot.hour == 16  # DST starts on March 29.


def test_plan_adapts_weaknesses_and_level_and_respects_budget(sessions):
    planner = PlannerService()
    with sessions.begin() as db:
        db.add_all([User(id=1), User(id=2)])
        db.flush()
        strong = {**DEFAULTS, "level": "B1", "weekly_hours": 0.5, "study_days": [1,2,3,4,5,6,7]}
        p1 = planner.create(db, 1, strong, {s: True for s in ("reading", "grammar", "vocabulary", "writing")})
        p2 = planner.create(db, 2, {**strong, "level": "A1"}, {"grammar": False})
        t1 = list(db.scalars(select(Task).where(Task.plan_id == p1.id)))
        t2 = list(db.scalars(select(Task).where(Task.plan_id == p2.id)))
        assert len(t2) > len(t1)
        assert sum(t.estimated_minutes for t in t1[:7]) <= 30
        dependencies = list(db.scalars(select(TaskDependency).where(TaskDependency.task_id == t1[-1].id)))
        assert dependencies


def test_impossible_target_warns_without_changing_target(sessions):
    with sessions.begin() as db:
        db.add(User(id=1))
        db.flush()
        target = "2026-01-06"
        plan = PlannerService().create(db, 1, {**DEFAULTS, "exam_date": target}, {},
            now=datetime(2026, 1, 5, tzinfo=timezone.utc))
        assert plan.data["target_date"] == target
        assert "выходит" in plan.data["warning"]


def test_reschedule_reflows_downstream_with_audit_and_preserves_target(sessions):
    planner = PlannerService()
    profile = {**DEFAULTS, "level": "B1"}
    now = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
    with sessions.begin() as db:
        db.add(User(id=1))
        db.flush()
        plan = planner.create(db, 1, profile, {s: True for s in ("reading", "grammar", "vocabulary", "writing")}, now)
        tasks = list(db.scalars(select(Task).where(Task.plan_id == plan.id).order_by(Task.id)))
        assert len(tasks) == 6
        moved = planner.reschedule(db, 1, profile, now=tasks[0].due_at + timedelta(days=1))
        assert moved >= 2
        assert tasks[0].due_at < tasks[1].due_at < tasks[2].due_at
        db.flush()
        history = list(db.scalars(select(RescheduleHistory)))
        assert len(history) == moved
        assert all(h.new_due_at > h.old_due_at for h in history)
