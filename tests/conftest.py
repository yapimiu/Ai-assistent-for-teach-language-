import os
from pathlib import Path
import sys
import pytest
from sqlalchemy import text
from app.db import Base, create_session_factory
from app import models
from app.llm import Usage
from app.schemas import Assessment, TeachingTask


class FakeModel:
    def __init__(self):
        self.acceptable = True
        self.confidence = 0.95
        self.calls = []

    def structured(self, role, schema, context):
        self.calls.append((role, context))
        usage = Usage("mock", role, 20, 30, None)
        if schema is TeachingTask:
            return TeachingTask(skill=context["skill"], topic=context["topic"],
                objective_ru="Цель: связно выразить мысль", explanation_ru="Согласуйте подлежащее и сказуемое.",
                prompt_ro=f"Scrie trei propoziții despre familia ta. Exercițiul {len(self.calls)}.",
                reference_answer="Familia mea locuiește în București."), usage
        errors = [] if self.acceptable is not False else [{"error_type": "agreement", "topic": context["topic"],
            "original": context["answer_text"], "corrected": "Eu merg acasă.",
            "explanation_ru": "Согласуйте форму глагола."}]
        return Assessment(skill=context["skill"], task_id=context["task_id"],
            answer_text=context["answer_text"], is_acceptable=self.acceptable, errors=errors,
            corrected_answer="Eu merg acasă.", explanation_ru="Подробный разбор ответа.", feedback_ro="Continuă!",
            estimated_level="A2", confidence=self.confidence,
            recommended_next_action="advance" if self.acceptable else "practice"), usage


@pytest.fixture
def model():
    return FakeModel()


@pytest.fixture
def sessions():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    factory = create_session_factory(url)
    # Each test has a private schema; never drop data in the public schema.
    import uuid
    schema = "test_" + uuid.uuid4().hex
    engine = factory.kw["bind"]
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    private = create_session_factory(url)
    from sqlalchemy import event
    @event.listens_for(private.kw["bind"], "connect")
    def search_path(dbapi_connection, record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        dbapi_connection.commit()
    Base.metadata.create_all(private.kw["bind"])
    yield private
    private.kw["bind"].dispose()
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()
