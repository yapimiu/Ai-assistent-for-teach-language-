from datetime import datetime, timezone
from sqlalchemy import select, func
from app.models import Task, Lesson, Attempt, Mistake, ProgressRecord, ModelUsage
from app.schemas import Assessment, TeachingTask
from app.pedagogy import assess_answer
from app.llm import ModelUnavailable

DIAGNOSTIC = [
    ("reading", "reading_details", "Citește: Ana lucrează la bibliotecă de luni până vineri. Sâmbăta merge la piață cu sora ei. Unde lucrează Ana și ce face sâmbăta?", "Ana lucrează la bibliotecă. Sâmbăta merge la piață cu sora ei."),
    ("grammar", "present", "Completează și explică pe scurt: Eu (a merge) ... la curs, iar ei (a învăța) ... limba română.", "Eu merg la curs, iar ei învață limba română."),
    ("vocabulary", "daily_life", "La farmacie ai nevoie de un medicament pentru durere de cap. Scrie două propoziții politicoase pentru farmacist.", "Bună ziua! Aș dori un medicament pentru durere de cap, vă rog."),
    ("writing", "connected_text", "Scrie 80–120 de cuvinte unui prieten despre o zi importantă: ce s-a întâmplat, cum te-ai simțit și ce ai învățat.", "Accept any coherent relevant Romanian narrative; assess grammar, vocabulary, coherence and task completion, allow valid alternatives."),
]
# Requested training profile, pending verification against official ILR publications.
TRAINING_MINUTES = {"reading_and_grammar": 45, "writing": 60, "listening_and_speaking": 30}


class MistakeTracker:
    def record(self, db, user_id, attempt, assessment):
        if assessment.confidence < 0.7 or assessment.is_acceptable is None:
            return
        if assessment.is_acceptable:
            for mistake in db.scalars(select(Mistake).where(Mistake.user_id == user_id,
                    Mistake.topic == attempt.task_topic, Mistake.status == "open")):
                mistake.successful_reviews += 1
                if mistake.successful_reviews >= 2:
                    mistake.status = "resolved"
            return
        for error in assessment.errors:
            mistake = db.scalar(select(Mistake).where(Mistake.user_id == user_id,
                Mistake.topic == error.topic, Mistake.error_type == error.error_type,
                Mistake.status == "open").order_by(Mistake.id).limit(1))
            if mistake:
                mistake.repetitions += 1
                mistake.successful_reviews = 0
                mistake.original = error.original
                mistake.corrected = error.corrected
                mistake.explanation = error.explanation_ru
                mistake.attempt_id = attempt.id
            else:
                db.add(Mistake(user_id=user_id, attempt_id=attempt.id, original=error.original,
                    corrected=error.corrected, error_type=error.error_type, topic=error.topic,
                    explanation=error.explanation_ru))


class TutorService:
    def __init__(self, llm):
        self.llm = llm
        self.mistakes = MistakeTracker()

    def usage(self, db, user_id, usage):
        # Provider charges survive rollback of the learning savepoint. Core flushes
        # this buffer in the outer receipt transaction, including failed followups.
        db.info.setdefault("model_usage", []).append(dict(user_id=user_id, model=usage.model, role=usage.role,
            prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens, cost=usage.cost))

    def diagnostic(self, db, user_id, mode):
        lesson = Lesson(user_id=user_id, mode=mode, summary="diagnostic")
        db.add(lesson)
        db.flush()
        tasks = []
        for skill, topic, prompt, reference in DIAGNOSTIC:
            task = Task(user_id=user_id, lesson_id=lesson.id, kind="diagnostic", skill=skill,
                topic=topic, prompt=prompt, reference=reference,
                explanation="Короткая текстовая диагностика: это только предварительная оценка навыка.",
                due_at=datetime.now(timezone.utc), estimated_minutes=15)
            db.add(task)
            tasks.append(task)
        db.flush()
        return lesson, tasks[0]

    def prepare(self, db, user_id, task, session, profile):
        mistakes = list(db.scalars(select(Mistake).where(Mistake.user_id == user_id,
            Mistake.status == "open").order_by(Mistake.repetitions.desc()).limit(3)))
        result, usage = self.llm.structured("tutor", TeachingTask, {
            "operation": "create_one_task", "skill": task.skill, "topic": task.topic,
            "objective": task.explanation, "estimated_level": profile["level"],
            "mode": profile["mode"], "memory": session.memory[-1500:],
            "previous_prompt": task.prompt[:3000] if task.reference else "",
            "requirement": "Generate a different independent exercise; do not repeat the previous prompt or reveal its answer",
            "past_errors": [{"topic": m.topic, "error": m.error_type,
                             "explanation": m.explanation[:500]} for m in mistakes],
        })
        self.usage(db, user_id, usage)
        if result.skill != task.skill or result.topic != task.topic:
            raise ModelUnavailable("Модель изменила тему задания; повторите позже.")
        if task.reference and result.prompt_ro.strip() == task.prompt.strip():
            raise ModelUnavailable("Модель повторила задание; повторите позже для независимого упражнения.")
        import json
        lesson = db.scalar(select(Lesson).where(Lesson.id == task.lesson_id, Lesson.user_id == user_id))
        try:
            hints = json.loads(lesson.summary) if lesson.summary.startswith("{") else {}
        except ValueError:
            hints = {}
        hints[str(task.id)] = 0
        lesson.summary = json.dumps(hints)
        task.prompt = result.prompt_ro
        task.explanation = result.objective_ru + "\n" + result.explanation_ru
        task.reference = result.reference_answer

    def present(self, db, user_id, task, mode):
        if mode == "exam":
            return f"Задание {task.id} · {task.skill}\n{task.prompt}\nОтветьте на румынском. Разбор после завершения."
        count = db.scalar(select(func.count()).select_from(ProgressRecord).where(
            ProgressRecord.user_id == user_id, ProgressRecord.topic == task.topic,
            ProgressRecord.mastered.is_(True))) or 0
        hints = assess_answer(is_acceptable=None, confidence=0, demonstrated_mastery=min(count / 3, 1)).hint_budget
        explanation = task.explanation if hints else "Попробуйте самостоятельно; цель — " + task.topic
        return f"Задание {task.id} · {task.skill}\n{explanation}\n\n{task.prompt}\nПодсказок доступно: {hints}. /hint"

    def assess(self, db, user_id, task, answer, session, mode):
        assessment, usage = self.llm.structured("assessor", Assessment, {
            "operation": "assess", "task_id": task.id, "skill": task.skill,
            "topic": task.topic, "prompt": task.prompt[:4000], "reference": task.reference[:3000],
            "answer_text": answer, "memory": session.memory[-1500:],
        })
        self.usage(db, user_id, usage)
        assessment.answer_text = answer
        if assessment.task_id != task.id or assessment.skill != task.skill:
            raise ModelUnavailable("Модель вернула оценку другого задания; повторите ответ.")
        decision = assess_answer(is_acceptable=assessment.is_acceptable, confidence=assessment.confidence,
                                 exam_mode=mode == "exam")
        import json
        lesson = db.scalar(select(Lesson).where(Lesson.id == task.lesson_id, Lesson.user_id == user_id))
        try:
            hints = json.loads(lesson.summary) if lesson.summary.startswith("{") else {}
        except ValueError:
            hints = {}
        assisted = hints.get(str(task.id), 0) > 0
        # Assistance follows the prompt across uncertain clarification attempts;
        # only preparing a genuinely new exercise clears it.
        attempt = Attempt(user_id=user_id, task_id=task.id, answer=answer, assisted=assisted,
                          assessment=assessment.model_dump(), confidence=assessment.confidence)
        db.add(attempt)
        db.flush()
        attempt.task_topic = task.topic
        if not (assisted and assessment.is_acceptable):
            self.mistakes.record(db, user_id, attempt, assessment)
        task.attempts += 1
        if assessment.confidence >= 0.7 and assessment.is_acceptable is not None:
            db.add(ProgressRecord(user_id=user_id, skill=task.skill, topic=task.topic,
                                 mastered=decision.demonstrates_mastery and not assisted, confidence=assessment.confidence))
        successful = sum(1 for a in db.scalars(select(Attempt).where(Attempt.user_id == user_id,
            Attempt.task_id == task.id)) if a.confidence >= 0.7 and a.assessment["is_acceptable"] is True and not a.assisted)
        # Diagnostic collects all four samples; uncertain samples remain explicitly unmastered.
        if task.kind == "diagnostic" or (decision.demonstrates_mastery and successful >= 2):
            task.status = "done"
        session.memory = (f"Последняя тема: {task.topic}; навык: {task.skill}; "
                          f"результат: {decision.next_action.value}; уверенность: {assessment.confidence:.2f}. "
                          f"{assessment.explanation_ru[:600]}")[:1500]
        return assessment, decision

    @staticmethod
    def feedback(assessment):
        if assessment.confidence < 0.7 or assessment.is_acceptable is None:
            return "Оценка неоднозначна. Освоение не засчитано. Уточните мысль или попробуйте другой ответ.\n" + assessment.explanation_ru
        errors = "\n".join(f"• {e.original} → {e.corrected}: {e.explanation_ru}" for e in assessment.errors)
        return (assessment.explanation_ru + "\n" + assessment.feedback_ro +
                ("\n" + errors if errors else "") +
                ("\nВозможный вариант: " + assessment.corrected_answer if not assessment.is_acceptable else ""))
