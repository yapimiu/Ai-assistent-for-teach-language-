from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.models import *
from app.services.core import LearningCore


def onboard(core, uid=10):
    core.handle(uid, "start", "/start")
    for i in range(9):
        core.handle(uid, f"onboard:{i}", "-")


def say(core, text, uid=10):
    import uuid
    return core.handle(uid, uuid.uuid4().hex, text)[1]


def test_registration_diagnostic_plan_lesson_and_restart(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    assert "reading" in say(core, "/test")
    for i in range(4):
        output = say(core, "Un răspuns acceptabil.")
    assert "план" in output
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 4
        assert db.scalar(select(func.count()).select_from(StudyPlan)) == 1
        assert db.get(ConversationSession, 10).task_id is None
    output = say(core, "/lesson")
    assert "Scrie trei" in output
    with sessions() as db:
        task_id = db.get(ConversationSession, 10).task_id
    restarted = LearningCore(sessions, model)
    assert "Продолжаем" in say(restarted, "/lesson")
    assert "Scrie trei" in say(restarted, "Eu învăț limba română.")
    with sessions() as db:
        assert db.get(Task, task_id).status == "pending"
    assert "Занятие завершено" in say(restarted, "Eu vorbesc cu familia mea.")
    with sessions() as db:
        assert db.get(Task, task_id).status == "done"
        assert db.get(ConversationSession, 10).task_id is None


def test_uncertain_answer_does_not_change_progress_or_mistakes(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/lesson")
    model.acceptable = False
    model.confidence = 0.6
    assert "неоднозначна" in say(core, "Eu merge.")
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1
        assert db.scalar(select(func.count()).select_from(ProgressRecord)) == 0
        assert db.scalar(select(func.count()).select_from(Mistake)) == 0
        assert db.get(Task, db.get(ConversationSession, 10).task_id).status == "pending"


def test_mistake_followup_and_two_reviews_resolve(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/lesson")
    model.acceptable = False
    say(core, "Eu merge.")
    with sessions() as db:
        mistake = db.scalar(select(Mistake))
        assert mistake.status == "open"
    assert model.calls[-1][1]["past_errors"]
    model.acceptable = True
    say(core, "Eu merg.")
    say(core, "Eu vorbesc.")
    with sessions() as db:
        assert db.scalar(select(Mistake)).status == "resolved"


def test_exam_mode_hides_feedback_and_progress_until_finish(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/settings mode=exam")
    assert "подсказ" in say(core, "/lesson").lower() or model.calls
    assert "недоступны" in say(core, "/hint")
    assert "после завершения" in say(core, "/progress")
    assert "после завершения" in say(core, "/mistakes")
    model.acceptable = False
    output = say(core, "Eu merge.")
    assert "Подробный разбор" in output  # One-task exam ends, then review becomes available.
    with sessions() as db:
        task = db.scalar(select(Task).where(Task.lesson_id.is_not(None)).order_by(Task.id))
        # Failed exam attempt does not unlock dependent curriculum tasks.
        pending = list(db.scalars(select(Task).where(Task.status == "pending")))
        assert pending
        assert db.get(ConversationSession, 10).task_id is None


def test_exam_diagnostic_collects_all_answers_before_feedback(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/settings mode=exam")
    say(core, "/test")
    for i in range(3):
        output = say(core, "Un răspuns.")
        assert "Подробный разбор" not in output
        assert "Разбор после завершения" in output
    output = say(core, "Ultimul răspuns.")
    assert "Подробный разбор" in output
    assert "Аудирование" in say(core, "/progress")


def test_duplicate_answer_is_atomic_with_concurrent_delivery(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/test")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: core.handle(10, "same_update", "Un răspuns."), range(4)))
    assert len({r[0] for r in results}) == 1
    assert len({r[1] for r in results}) == 1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1
        assert db.scalar(select(func.count()).select_from(ModelUsage)) == 1
    core.delivered(10, results[0][0])
    assert core.handle(10, "same_update", "Un răspuns.")[2]


def test_user_isolation_and_composite_foreign_key(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core, 10)
    onboard(core, 20)
    say(core, "/test", 10)
    model.acceptable = False
    say(core, "Eu merge.", 10)
    assert "пока нет" in say(core, "/mistakes", 20)
    with sessions() as db:
        other_task = db.scalar(select(Task).where(Task.user_id == 10))
        task_id = other_task.id
        with pytest.raises(ValueError):
            core.owned(db, Task, 20, task_id)
    with pytest.raises(IntegrityError), sessions.begin() as db:
        db.get(ConversationSession, 20).task_id = task_id


def test_onboarding_resume_and_editable_profile(sessions, model):
    core = LearningCore(sessions, model)
    core.handle(10, "s", "/start")
    core.handle(10, "1", "украинский")
    core = LearningCore(sessions, model)
    assert "организация" in say(core, "/start")
    for i in range(8):
        say(core, "-")
    assert "сохранена" in say(core, "/settings weekly_hours=5")
    assert "Некорректное" in say(core, "/settings timezone=Invalid/Zone")
    with sessions() as db:
        assert db.get(LearningProfile, 10).data["native_language"] == "украинский"
        assert db.get(LearningProfile, 10).data["weekly_hours"] == 5


def test_hint_budget_persists_across_restart(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/lesson")
    for _ in range(3):
        assert "Подсказка:" in say(core, "/hint")
    assert "исчерпаны" in say(LearningCore(sessions, model), "/hint")


def test_explicit_hint_disqualifies_independent_mastery(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/lesson")
    say(core, "/hint")
    say(core, "Eu merg.")
    with sessions() as db:
        assert db.scalar(select(Attempt)).assisted
        assert not db.scalar(select(ProgressRecord)).mastered
    say(core, "Eu vorbesc.")
    with sessions() as db:
        assert db.get(ConversationSession, 10).task_id is not None
    say(core, "Eu citesc.")
    with sessions() as db:
        assert db.get(ConversationSession, 10).task_id is None


def test_unknown_settings_key_with_default_marker_does_not_crash(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    assert "Некорректное" in say(core, "/settings unknown=-")


def test_uncertain_clarification_preserves_prior_hint_assistance(sessions, model):
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/lesson")
    say(core, "/hint")
    model.confidence = 0.5
    say(core, "Eu merg.")
    model.confidence = 0.95
    say(core, "Eu merg acasă.")
    with sessions() as db:
        attempts = list(db.scalars(select(Attempt).order_by(Attempt.id)))
        assert all(a.assisted for a in attempts)
        assert not any(db.scalars(select(ProgressRecord.mastered)))
        assert db.get(ConversationSession, 10).task_id


def test_known_model_cost_survives_learning_rollback_after_followup_failure(sessions, model):
    from app.llm import ModelUnavailable, Usage
    from app.schemas import TeachingTask
    core = LearningCore(sessions, model)
    onboard(core)
    say(core, "/lesson")
    original = model.structured
    def fail_followup(role, schema, context):
        if schema is TeachingTask:
            raise ModelUnavailable("Followup temporarily unavailable")
        result, usage = original(role, schema, context)
        return result, Usage(usage.model, usage.role, 20, 30, 0.012)
    model.structured = fail_followup
    assert "temporarily unavailable" in say(core, "Eu merg.")
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 0
        assert db.scalar(select(func.count()).select_from(ProgressRecord)) == 0
        costs = list(db.scalars(select(ModelUsage.cost).order_by(ModelUsage.id)))
        assert costs == [None, 0.012]
