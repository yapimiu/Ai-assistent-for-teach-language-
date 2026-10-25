from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models import StudyPlan, Task, RescheduleHistory, ExamTarget, TaskDependency

TOPICS = [
    ("grammar", "present", "Настоящее время", "Составить 4 фразы о распорядке дня", []),
    ("vocabulary", "daily_life", "Лексика повседневной жизни", "Уместно употребить 8 слов в контексте", ["present"]),
    ("reading", "reading_details", "Чтение: основная мысль и детали", "Верно объяснить смысл и 3 детали текста", ["daily_life"]),
    ("grammar", "past", "Прошедшее время", "Описать 4 завершённых события", ["present"]),
    ("writing", "connected_text", "Связный текст", "Написать связный текст с аргументом и примерами", ["past", "reading_details"]),
    ("writing", "exam_review", "Учебная проверка B1", "Самостоятельно выполнить текстовые задания; затем разобрать ошибки", ["connected_text"]),
]


def next_slot(profile, after: datetime):
    """Find next preferred local study slot strictly after the supplied instant."""
    zone = ZoneInfo(profile["timezone"])
    local = after.astimezone(zone)
    hour, minute = map(int, profile["study_time"].split(":"))
    days = profile["study_days"]
    for offset in range(15):
        day = local.date() + timedelta(days=offset)
        candidate = datetime.combine(day, time(hour, minute), zone)
        if day.isoweekday() in days and candidate > local:
            return candidate.astimezone(timezone.utc)
    raise ValueError("Нет доступных дней занятий")


class PlannerService:
    def create(self, db, user_id, profile, evidence, now=None):
        now = now or datetime.now(timezone.utc)
        for old in db.scalars(select(StudyPlan).where(StudyPlan.user_id == user_id, StudyPlan.active.is_(True))):
            old.active = False
            for task in db.scalars(select(Task).where(Task.user_id == user_id, Task.plan_id == old.id,
                                                     Task.status == "pending")):
                task.status = "superseded"
        weaknesses = {skill for skill, good in evidence.items() if not good}
        # Dependencies remain topological; weak topics receive extra budget and remediation.
        weekly = int(profile["weekly_hours"] * 60)
        session_minutes = max(1, min(60, weekly // len(profile["study_days"])))
        plan = StudyPlan(user_id=user_id, data={"target_level": "B1", "self_level": profile["level"],
            "weekly_minutes": weekly, "timezone": profile["timezone"], "weak_skills": sorted(weaknesses),
            "unassessed": ["listening", "speaking"], "criteria": "Two confident independent successful reviews per topic",
            "target_date": profile.get("exam_date"), "warning": ""})
        db.add(plan)
        db.flush()
        due = now
        topic_ids = {}
        for skill, topic, name, objective, deps in TOPICS:
            remedial_id = None
            if skill in weaknesses or profile["level"] in ("A1", "unknown"):
                due = next_slot(profile, due)
                remedial = Task(user_id=user_id, plan_id=plan.id, skill=skill, topic=topic,
                    prompt="Подготовка: " + name, reference="",
                    explanation="Базовое закрепление: " + objective,
                    due_at=due, estimated_minutes=session_minutes,
                    prerequisite_id=topic_ids.get(deps[-1]) if deps else None)
                db.add(remedial)
                db.flush()
                for dependency in deps:
                    db.add(TaskDependency(user_id=user_id, task_id=remedial.id,
                                          depends_on_id=topic_ids[dependency]))
                remedial_id = remedial.id
            due = next_slot(profile, due)
            task = Task(user_id=user_id, plan_id=plan.id, skill=skill, topic=topic,
                prompt=name + ": " + objective, reference="", explanation=objective,
                due_at=due, estimated_minutes=session_minutes,
                prerequisite_id=remedial_id or (topic_ids.get(deps[-1]) if deps else None))
            db.add(task)
            db.flush()
            for dependency in deps:
                db.add(TaskDependency(user_id=user_id, task_id=task.id,
                                      depends_on_id=topic_ids[dependency]))
            if remedial_id:
                db.add(TaskDependency(user_id=user_id, task_id=task.id, depends_on_id=remedial_id))
            topic_ids[topic] = task.id
        target = profile.get("exam_date")
        if target and due.astimezone(ZoneInfo(profile["timezone"])).date().isoformat() > target:
            plan.data = {**plan.data, "warning": "План выходит за желаемую дату: увеличьте время или обсудите сроки. Цель не изменена."}
        return plan

    def reschedule(self, db, user_id, profile, now=None):
        now = now or datetime.now(timezone.utc)
        tasks = list(db.scalars(select(Task).where(Task.user_id == user_id,
            Task.status == "pending", Task.plan_id.is_not(None)).order_by(Task.id)))
        if not any(task.due_at < now for task in tasks):
            return 0
        # Reflow the remaining topological plan, including downstream dependencies.
        # Each preferred slot has one task; every changed deadline gets an audit row.
        moved = 0
        cursor = now
        for task in tasks:
            earliest = next_slot(profile, cursor)
            due = max(task.due_at, earliest)
            if due != task.due_at:
                db.add(RescheduleHistory(user_id=user_id, task_id=task.id,
                    old_due_at=task.due_at, new_due_at=due,
                    reason="Пропуск или зависимость от перенесённого задания; цель сохранена"))
                task.due_at = due
                moved += 1
            cursor = due
        return moved
