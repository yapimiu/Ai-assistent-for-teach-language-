"""Owner keys are included in foreign keys to prevent cross-user relations."""
from datetime import datetime, date, timezone
from sqlalchemy import (BigInteger, Boolean, Date, DateTime, Float, ForeignKey,
                        ForeignKeyConstraint, Integer, JSON, String, Text,
                        UniqueConstraint, CheckConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningProfile(Base):
    __tablename__ = "learning_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)


class ExamTarget(Base):
    __tablename__ = "exam_targets"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization: Mapped[str] = mapped_column(String(120), default="ILR")
    level: Mapped[str] = mapped_column(String(10), default="B1")
    target_date: Mapped[date | None] = mapped_column(Date)


class Owned:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class StudyPlan(Owned, Base):
    __tablename__ = "study_plans"
    __table_args__ = (UniqueConstraint("id", "user_id"),)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    data: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Lesson(Owned, Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("id", "user_id"),)
    mode: Mapped[str] = mapped_column(String(12), default="teaching")
    status: Mapped[str] = mapped_column(String(16), default="active")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Owned, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("id", "user_id"),
        ForeignKeyConstraint(["lesson_id", "user_id"], ["lessons.id", "lessons.user_id"]),
        ForeignKeyConstraint(["plan_id", "user_id"], ["study_plans.id", "study_plans.user_id"]),
        ForeignKeyConstraint(["prerequisite_id", "user_id"], ["tasks.id", "tasks.user_id"]),
        CheckConstraint("estimated_minutes > 0"),
    )
    lesson_id: Mapped[int | None] = mapped_column(Integer)
    plan_id: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="lesson")
    skill: Mapped[str] = mapped_column(String(30))
    topic: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=20)
    prerequisite_id: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    __mapper_args__ = {}


class Attempt(Owned, Base):
    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint("id", "user_id"),
        ForeignKeyConstraint(["task_id", "user_id"], ["tasks.id", "tasks.user_id"]),
        CheckConstraint("confidence >= 0 AND confidence <= 1"),
    )
    task_id: Mapped[int] = mapped_column(Integer)
    answer: Mapped[str] = mapped_column(Text)
    assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    assessment: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Mistake(Owned, Base):
    __tablename__ = "mistakes"
    __table_args__ = (ForeignKeyConstraint(["attempt_id", "user_id"], ["attempts.id", "attempts.user_id"]),)
    attempt_id: Mapped[int] = mapped_column(Integer)
    original: Mapped[str] = mapped_column(Text)
    corrected: Mapped[str] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(String(60))
    topic: Mapped[str] = mapped_column(String(100))
    explanation: Mapped[str] = mapped_column(Text)
    repetitions: Mapped[int] = mapped_column(Integer, default=1)
    successful_reviews: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProgressRecord(Owned, Base):
    __tablename__ = "progress_records"
    skill: Mapped[str] = mapped_column(String(30))
    topic: Mapped[str] = mapped_column(String(100))
    mastered: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["lesson_id", "user_id"], ["lessons.id", "lessons.user_id"]),
        ForeignKeyConstraint(["task_id", "user_id"], ["tasks.id", "tasks.user_id"]),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(String(40), default="onboarding")
    lesson_id: Mapped[int | None] = mapped_column(Integer)
    task_id: Mapped[int | None] = mapped_column(Integer)
    memory: Mapped[str] = mapped_column(Text, default="")


class MessageReceipt(Base):
    __tablename__ = "message_receipts"
    __table_args__ = (UniqueConstraint("user_id", "message_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message_key: Mapped[str] = mapped_column(String(100))
    response: Mapped[str] = mapped_column(Text)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)


class RescheduleHistory(Owned, Base):
    __tablename__ = "reschedule_history"
    __table_args__ = (ForeignKeyConstraint(["task_id", "user_id"], ["tasks.id", "tasks.user_id"]),)
    task_id: Mapped[int] = mapped_column(Integer)
    old_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    new_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelUsage(Owned, Base):
    __tablename__ = "model_usage"
    model: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(["task_id", "user_id"], ["tasks.id", "tasks.user_id"]),
        ForeignKeyConstraint(["depends_on_id", "user_id"], ["tasks.id", "tasks.user_id"]),
        CheckConstraint("task_id != depends_on_id"),
    )
    task_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    depends_on_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
