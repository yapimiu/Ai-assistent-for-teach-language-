"""Transactional entry point used by every Telegram command and answer."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select, text, func
from sqlalchemy.dialects.postgresql import insert
from app.models import (User, LearningProfile, ExamTarget, ConversationSession, MessageReceipt,
                        StudyPlan, Task, Lesson, Attempt, Mistake, ProgressRecord, TaskDependency, ModelUsage)
from app.services.planner import PlannerService
from app.services.tutor import TutorService
from app.schemas import Assessment
from app.llm import ModelUnavailable
from app.pedagogy import assess_answer

FIELDS = [
    ("native_language", "Родной язык? (по умолчанию русский; отправьте -)"),
    ("organization", "Экзаменационная организация? (ILR; - для значения по умолчанию)"),
    ("citizenship_basis", "Основание получения гражданства? (- если пока не уточнено)"),
    ("level", "Предполагаемый уровень: A1, A2, B1 или unknown? (- = unknown)"),
    ("exam_date", "Желаемая дата экзамена YYYY-MM-DD? (- если не определена)"),
    ("weekly_hours", "Сколько часов в неделю готовы учиться? (0.5–40; - = 3)"),
    ("study_days", "Дни занятий: номера через запятую, 1=пн ... 7=вс? (- = 1,3,5)"),
    ("study_time", "Местное время начала занятий HH:MM? (- = 19:00)"),
    ("timezone", "Часовой пояс IANA, например Europe/Bucharest? (- = Europe/Bucharest)"),
]
DEFAULTS = {"language": "Romanian", "native_language": "русский", "organization": "ILR",
    "citizenship_basis": "уточняется", "level": "unknown", "exam_date": None,
    "weekly_hours": 3.0, "study_days": [1,3,5], "study_time": "19:00",
    "timezone": "Europe/Bucharest", "mode": "teaching"}


def validate_field(key, value):
    if key not in DEFAULTS or key == "language":
        raise ValueError("Неизвестная или неизменяемая настройка")
    if value == "-":
        return DEFAULTS[key]
    if key == "weekly_hours":
        hours = float(value)
        if not 0.5 <= hours <= 40:
            raise ValueError("Часы должны быть от 0.5 до 40")
        return hours
    if key == "study_days":
        days = sorted(set(map(int, value.split(","))))
        if not days or any(day < 1 or day > 7 for day in days):
            raise ValueError("Укажите дни 1–7 через запятую")
        return days
    if key == "study_time":
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    if key == "timezone":
        ZoneInfo(value)
    if key == "exam_date":
        target = date.fromisoformat(value)
        if target <= date.today():
            raise ValueError("Дата экзамена должна быть в будущем")
        return target.isoformat()
    if key == "level" and value not in ("A1", "A2", "B1", "unknown"):
        raise ValueError("Уровень: A1, A2, B1, unknown")
    if key == "mode" and value not in ("teaching", "exam"):
        raise ValueError("Режим: teaching или exam")
    if key not in DEFAULTS or key == "language":
        raise ValueError("Неизвестная или неизменяемая настройка")
    if not value.strip() or len(value) > 120:
        raise ValueError("Значение должно содержать от 1 до 120 символов")
    return value.strip()


class LearningCore:
    def __init__(self, sessions, llm):
        self.sessions = sessions
        self.tutor = TutorService(llm)
        self.planner = PlannerService()

    def handle(self, user_id: int, message_key: str, content: str):
        """Return (receipt_id, response, already_delivered), committing before send.

        PostgreSQL transaction advisory locks serialize a single learner, including
        initial registration. Other learners proceed independently. A receipt also
        stores responses for delivery recovery after Telegram/network failures.
        """
        if not 0 < user_id < 2**63:
            raise ValueError("Invalid Telegram sender")
        if len(message_key) > 100:
            raise ValueError("Invalid message key")
        with self.sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(:uid)"), {"uid": user_id})
            old = db.scalar(select(MessageReceipt).where(MessageReceipt.user_id == user_id,
                                                         MessageReceipt.message_key == message_key))
            if old:
                return old.id, old.response, old.delivered
            user = db.get(User, user_id)
            if user is None:
                db.add(User(id=user_id))
                db.flush()
                db.add_all([LearningProfile(user_id=user_id, data=dict(DEFAULTS)),
                            ExamTarget(user_id=user_id), ConversationSession(user_id=user_id)])
                db.flush()
            profile = db.get(LearningProfile, user_id)
            session = db.get(ConversationSession, user_id)
            db.info["model_usage"] = []
            try:
                with db.begin_nested():
                    response = self.route(db, user_id, profile, session, content.strip())
            except ModelUnavailable as exc:
                response = str(exc)
            except (ValueError, ZoneInfoNotFoundError):
                response = "Некорректное значение. Проверьте формат и повторите. /settings покажет доступные поля."
            for usage in db.info.pop("model_usage", []):
                db.add(ModelUsage(**usage))
            receipt = MessageReceipt(user_id=user_id, message_key=message_key, response=response)
            db.add(receipt)
            db.flush()
            return receipt.id, response, False

    def pending(self, user_id=None, limit=100):
        with self.sessions() as db:
            query = select(MessageReceipt).where(MessageReceipt.delivered.is_(False)).order_by(MessageReceipt.id).limit(limit)
            if user_id is not None:
                query = query.where(MessageReceipt.user_id == user_id)
            return [(r.id, r.user_id, r.response) for r in db.scalars(query)]

    def delivered(self, user_id, receipt_id):
        with self.sessions.begin() as db:
            receipt = db.scalar(select(MessageReceipt).where(MessageReceipt.id == receipt_id,
                                                             MessageReceipt.user_id == user_id))
            if receipt:
                receipt.delivered = True

    def target(self, db, user_id, data):
        target = db.get(ExamTarget, user_id)
        target.organization = data["organization"]
        target.target_date = date.fromisoformat(data["exam_date"]) if data["exam_date"] else None

    def evidence(self, db, user_id):
        result = {}
        for skill in ("reading", "grammar", "vocabulary", "writing"):
            records = list(db.scalars(select(ProgressRecord).where(ProgressRecord.user_id == user_id,
                ProgressRecord.skill == skill).order_by(ProgressRecord.id.desc()).limit(3)))
            result[skill] = bool(records) and all(r.mastered for r in records)
        return result

    def plan_text(self, db, user_id, profile):
        plan = db.scalar(select(StudyPlan).where(StudyPlan.user_id == user_id, StudyPlan.active.is_(True)).order_by(StudyPlan.id.desc()).limit(1))
        if not plan:
            return "План ещё не сформирован. Пройдите /test."
        tasks = list(db.scalars(select(Task).where(Task.user_id == user_id, Task.plan_id == plan.id).order_by(Task.id)))
        zone = ZoneInfo(profile.data["timezone"])
        return ("Индивидуальный учебный план B1 (предварительный)\n" +
            f"Бюджет: {plan.data['weekly_minutes']} мин/нед. Уровень: {plan.data['self_level']}.\n" +
            "\n".join(f"#{t.id} {t.topic}: {t.estimated_minutes} мин, {t.due_at.astimezone(zone):%d.%m %H:%M}, "
                      f"зависимости: {','.join(map(str, db.scalars(select(TaskDependency.depends_on_id).where(TaskDependency.user_id == user_id, TaskDependency.task_id == t.id)))) or 'нет'}, {t.status}; цель: {t.explanation[:120]}" for t in tasks) +
            "\nКритерий темы: два уверенных самостоятельных успешных ответа.\nАудирование и говорение не проверены.\n" + plan.data.get("warning", ""))

    def route(self, db, uid, profile, session, content):
        if not content:
            return "Отправьте текст или выберите команду."
        if len(content) > 6000:
            return "Ответ слишком длинный: максимум 6000 символов."
        parts = content.split(maxsplit=1)
        command = parts[0].split("@")[0] if content.startswith("/") else ""
        arg = parts[1] if len(parts) > 1 else ""
        if command == "/start":
            if profile.onboarded:
                return "С возвращением! /today — задачи, /lesson — продолжить, /settings — профиль."
            session.stage = "onboarding:0" if session.stage == "onboarding" else session.stage
            return "Румынский B1 · цель ILR. Короткая диагностика не подтверждает официальный уровень.\n" + FIELDS[int(session.stage.split(":")[-1])][1]
        if not profile.onboarded:
            if command:
                return "Сначала /start и заполните профиль."
            index = int(session.stage.split(":")[-1]) if ":" in session.stage else 0
            key = FIELDS[index][0]
            profile.data = {**profile.data, key: validate_field(key, content)}
            if index + 1 < len(FIELDS):
                session.stage = f"onboarding:{index+1}"
                return FIELDS[index+1][1]
            profile.onboarded = True
            session.stage = "ready"
            self.target(db, uid, profile.data)
            return "Профиль сохранён. Начните /test: чтение, грамматика, лексика, письмо. Аудирование и речь пока не проверяются."
        if command == "/settings":
            if not arg:
                return "\n".join(f"{k}={v}" for k,v in profile.data.items()) + "\nИзменить: /settings weekly_hours=4\nРежим: /settings mode=exam или teaching"
            key, value = arg.split("=", 1)
            if key == "mode" and session.lesson_id:
                lesson = db.scalar(select(Lesson).where(Lesson.id == session.lesson_id, Lesson.user_id == uid))
                if lesson and lesson.status == "active":
                    return "Режим активного занятия изменить нельзя. Завершите /finish."
            profile.data = {**profile.data, key: validate_field(key, value)}
            self.target(db, uid, profile.data)
            if key != "mode" and db.scalar(select(StudyPlan.id).where(StudyPlan.user_id == uid, StudyPlan.active.is_(True)).limit(1)):
                if session.lesson_id:
                    return "Настройка сохранена. Завершите занятие, затем /replan для обновления расписания."
                self.planner.create(db, uid, profile.data, self.evidence(db, uid))
                return "Настройка сохранена, будущий план обновлён.\n" + self.plan_text(db, uid, profile)
            return "Настройка сохранена."
        if command == "/replan":
            if session.lesson_id:
                return "Сначала завершите активное занятие /finish."
            self.planner.create(db, uid, profile.data, self.evidence(db, uid))
            return self.plan_text(db, uid, profile)
        if command == "/plan":
            return self.plan_text(db, uid, profile)
        if command == "/today":
            moved = self.planner.reschedule(db, uid, profile.data)
            db.flush()
            tasks = list(db.scalars(select(Task).where(Task.user_id == uid, Task.status == "pending").order_by(Task.due_at).limit(5)))
            zone = ZoneInfo(profile.data["timezone"])
            today = datetime.now(zone).date()
            return (f"Перенесено пропущенных задач: {moved}. Целевая дата сохранена.\n" +
                "\n".join(f"{'Сегодня' if t.due_at.astimezone(zone).date() == today else 'Предстоит'}: #{t.id} {t.topic} — {t.due_at.astimezone(zone):%d.%m %H:%M}" for t in tasks) +
                "\n/lesson — начать ближайшее задание.\n" + self.deadline_warning(db, uid))
        if command in ("/mistakes", "/progress") and session.lesson_id:
            active = self.owned(db, Lesson, uid, session.lesson_id)
            if active.mode == "exam":
                return "Разбор и обновлённый прогресс доступны после завершения экзаменационного задания: /finish."
        if command == "/mistakes":
            mistakes = list(db.scalars(select(Mistake).where(Mistake.user_id == uid).order_by(Mistake.id.desc()).limit(20)))
            return "\n".join(f"{m.topic}: {m.original} → {m.corrected}\n{m.explanation} ({m.status}, повторов {m.repetitions})" for m in mistakes) or "Зафиксированных ошибок пока нет."
        if command == "/progress":
            records = list(db.scalars(select(ProgressRecord).where(ProgressRecord.user_id == uid)))
            lines = []
            for skill in ("reading", "grammar", "vocabulary", "writing"):
                rows = [r for r in records if r.skill == skill]
                lines.append(f"{skill}: уверенных успешных ответов {sum(r.mastered for r in rows)}/{len(rows)}")
            return "\n".join(lines) + "\nАудирование: не проверено. Говорение: не проверено.\nЭто учебные наблюдения, не официальный результат экзамена."
        if command == "/hint":
            return self.hint(db, uid, session)
        if command == "/finish":
            return self.finish(db, uid, session, profile)
        if command in ("/test", "/lesson", "/practice"):
            if session.lesson_id and session.task_id:
                lesson = self.owned(db, Lesson, uid, session.lesson_id)
                task = self.owned(db, Task, uid, session.task_id)
                return "Продолжаем сохранённое занятие.\n" + self.tutor.present(db, uid, task, lesson.mode)
            if command == "/test":
                lesson, task = self.tutor.diagnostic(db, uid, profile.data["mode"])
            else:
                lesson, task = self.new_lesson(db, uid, session, profile, practice=command == "/practice")
            session.lesson_id, session.task_id, session.stage = lesson.id, task.id, "answer"
            return self.tutor.present(db, uid, task, lesson.mode)
        if command:
            return "Команды: /start /today /plan /lesson /practice /test /mistakes /progress /settings /finish /hint"
        if not session.task_id:
            return "Начните /test, /lesson или /practice."
        task = self.owned(db, Task, uid, session.task_id)
        lesson = self.owned(db, Lesson, uid, session.lesson_id)
        assessment, decision = self.tutor.assess(db, uid, task, content, session, lesson.mode)
        db.flush()
        if task.status != "done" and lesson.mode != "exam":
            # A fresh prompt for remediation; uncertainty instead asks clarification on same task.
            feedback = self.tutor.feedback(assessment)
            if decision.next_action.value in ("practice", "advance"):
                self.tutor.prepare(db, uid, task, session, profile.data)
            return feedback + "\n\n" + self.tutor.present(db, uid, task, lesson.mode)
        prefix = "Ответ принят. Разбор после завершения.\n" if lesson.mode == "exam" else self.tutor.feedback(assessment) + "\n"
        if lesson.mode == "exam" and task.kind != "diagnostic":
            return prefix + self.finish(db, uid, session, profile, completed=True)
        pending = db.scalar(select(Task).where(Task.user_id == uid, Task.lesson_id == lesson.id,
            Task.status == "pending").order_by(Task.id).limit(1))
        if pending:
            session.task_id = pending.id
            return prefix + self.tutor.present(db, uid, pending, lesson.mode)
        if task.kind == "diagnostic":
            return prefix + self.finish(db, uid, session, profile, completed=True)
        return prefix + self.finish(db, uid, session, profile, completed=True)

    @staticmethod
    def owned(db, cls, uid, object_id):
        obj = db.scalar(select(cls).where(cls.id == object_id, cls.user_id == uid))
        if obj is None:
            raise ValueError("Задание недоступно")
        return obj

    def deadline_warning(self, db, uid):
        target = db.get(ExamTarget, uid)
        latest = db.scalar(select(func.max(Task.due_at)).where(Task.user_id == uid, Task.status == "pending"))
        if target.target_date and latest and latest.date() > target.target_date:
            return "Внимание: незавершённый план выходит за желаемую дату экзамена. /settings или /replan."
        return ""

    def hint(self, db, uid, session):
        if not session.task_id:
            return "Сначала начните занятие."
        lesson = self.owned(db, Lesson, uid, session.lesson_id)
        if lesson.mode == "exam":
            return "В экзаменационном режиме подсказки недоступны. Разбор после завершения."
        task = self.owned(db, Task, uid, session.task_id)
        count = db.scalar(select(func.count()).select_from(ProgressRecord).where(ProgressRecord.user_id == uid,
            ProgressRecord.topic == task.topic, ProgressRecord.mastered.is_(True))) or 0
        budget = assess_answer(is_acceptable=None, confidence=0, demonstrated_mastery=min(count/3, 1)).hint_budget
        # Hint counters are persisted with the lesson summary, keyed by task id.
        import json
        try:
            hints = json.loads(lesson.summary) if lesson.summary.startswith("{") else {}
        except ValueError:
            hints = {}
        used = hints.get(str(task.id), 0)
        if used >= budget:
            return "Подсказки исчерпаны. Попробуйте самостоятельно."
        hints[str(task.id)] = used + 1
        lesson.summary = json.dumps(hints)
        return "Подсказка: " + task.explanation[:1200]

    def new_lesson(self, db, uid, session, profile, practice=False):
        lesson = Lesson(user_id=uid, mode=profile.data["mode"])
        db.add(lesson)
        db.flush()
        if practice:
            mistake = db.scalar(select(Mistake).where(Mistake.user_id == uid, Mistake.status == "open").order_by(Mistake.repetitions.desc()).limit(1))
            topic = mistake.topic if mistake else "present"
            skill = "grammar"
            if mistake:
                source_attempt = self.owned(db, Attempt, uid, mistake.attempt_id)
                skill = self.owned(db, Task, uid, source_attempt.task_id).skill
            task = Task(user_id=uid, lesson_id=lesson.id, kind="practice", skill=skill, topic=topic,
                        prompt="", explanation="Самостоятельно исправить повторяющуюся ошибку: " + (mistake.explanation if mistake else "настоящее время"),
                        due_at=datetime.now(timezone.utc), estimated_minutes=15)
            db.add(task)
        else:
            plan = db.scalar(select(StudyPlan).where(StudyPlan.user_id == uid, StudyPlan.active.is_(True)).order_by(StudyPlan.id.desc()).limit(1))
            if not plan:
                plan = self.planner.create(db, uid, profile.data, self.evidence(db, uid))
            candidates = list(db.scalars(select(Task).where(Task.user_id == uid, Task.plan_id == plan.id,
                                                           Task.status == "pending").order_by(Task.id)))
            def ready(t):
                dependencies = list(db.scalars(select(TaskDependency.depends_on_id).where(
                    TaskDependency.user_id == uid, TaskDependency.task_id == t.id)))
                return all(self.owned(db, Task, uid, dep).status == "done" for dep in dependencies)
            task = next((t for t in candidates if ready(t)), None)
            if not task:
                if candidates:
                    raise ValueError("Сначала завершите предыдущие темы")
                task = Task(user_id=uid, lesson_id=lesson.id, kind="practice", skill="writing", topic="exam_review",
                            prompt="", explanation="Повторить навыки связного текста B1", due_at=datetime.now(timezone.utc), estimated_minutes=20)
                db.add(task)
            task.lesson_id = lesson.id
        db.flush()
        self.tutor.prepare(db, uid, task, session, profile.data)
        return lesson, task

    def finish(self, db, uid, session, profile, completed=False):
        if not session.lesson_id:
            return "Нет активного занятия. /lesson"
        lesson = self.owned(db, Lesson, uid, session.lesson_id)
        tasks = list(db.scalars(select(Task).where(Task.user_id == uid, Task.lesson_id == lesson.id).order_by(Task.id)))
        diagnostic = bool(tasks) and tasks[0].kind == "diagnostic"
        if diagnostic and not all(t.status == "done" for t in tasks):
            return "Диагностика ещё не завершена: ответьте на все четыре задания. /test продолжит."
        feedback = []
        if lesson.mode == "exam":
            for task in tasks:
                for attempt in db.scalars(select(Attempt).where(Attempt.user_id == uid, Attempt.task_id == task.id).order_by(Attempt.id)):
                    feedback.append(f"Задание {task.id}: " + self.tutor.feedback(Assessment.model_validate(attempt.assessment)))
        lesson.status = "completed" if completed else "paused"
        # Unfinished plan work is detached for continuation; attempts remain persisted.
        for task in tasks:
            if task.status == "pending":
                task.lesson_id = None
        session.lesson_id = session.task_id = None
        session.stage = "ready"
        response = "Занятие завершено.\n" + "\n".join(feedback)
        if diagnostic:
            self.planner.create(db, uid, profile.data, self.evidence(db, uid))
            response += "\nДиагностика предварительная; аудирование и речь не проверены.\n" + self.plan_text(db, uid, profile)
        return response + "\n/mistakes — ошибки, /today — следующие задания."
