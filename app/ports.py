"""Future integration contracts only; no Calendar, voice or Anki implementation."""
from datetime import datetime
from typing import Protocol


class CalendarPort(Protocol):
    def schedule(self, user_id: int, title: str, starts_at: datetime, minutes: int) -> str: ...


class SpeechToTextPort(Protocol):
    def transcribe(self, audio: bytes, language: str) -> str: ...


class TextToSpeechPort(Protocol):
    def synthesize(self, text: str, language: str) -> bytes: ...


class AudioAnalysisPort(Protocol):
    def analyze(self, audio: bytes, transcript: str) -> dict: ...
