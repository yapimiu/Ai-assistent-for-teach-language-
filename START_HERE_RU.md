# OpenCode 2.1.4 — ROMÂNĂ B1 tutor (macOS)

1. Распакуйте комплект; перенесите `opencode.json` и `.opencode/` в корень `Ai-assistent-for-teach-language-`. **Не заменяйте существующий AGENTS.md**: он принадлежит проекту и описывает исходную Codex-команду.
2. Проверьте версию `opencode --version`; настройте OpenRouter через `opencode auth login` (API-ключ не вставляйте в файлы проекта).
3. Выполните `cd /путь/к/Ai-assistent-for-teach-language-` затем `opencode debug config` (не публикуйте секреты из вывода).
4. Выполните `opencode agent list` и убедитесь в наличии `architect`, `coder`. Запустите `opencode`; агент по умолчанию — architect на `openrouter/moonshotai/kimi-k2.6`; coder — `openrouter/anthropic/claude-haiku-5.5`. В UI можно сменить агента через Shift+Tab.
5. Начните с `/audit`; затем `/implement Добавь небольшой unit-тест без изменения production-кода`. Для проверки — `/verify`.

### Особенности проекта
- Python >=3.12, `uv`, aiogram, FastAPI, SQLAlchemy/Alembic, PostgreSQL, OpenRouter.
- Официальная документация: README.md, AGENTS.md, MASTER_PROMPT.md, ARCHITECTURE.md, PROJECT_MAP.md, ROADMAP.md.
- База с реальными данными и Docker volumes не должны затрагиваться агентами. Не запускайте живой Telegram bot, не ставьте его на сервер: деплой выполняется вручную.
- M1 включает текстового преподавателя Romanian B1. Anki/voice/Google Calendar — следующие вехи.
- Тесты: `uv run pytest -q` безопасны лишь при корректной тестовой конфигурации. Для интеграционных тестов используйте отдельную уничтожаемую базу, не равную рабочей DATABASE_URL.

### Если возникнет ошибка
`opencode auth list` должен показывать OpenRouter. В модели проверьте OpenRouter, а не OpenCode Go. Используйте `opencode debug config` для диагностики настроек, а `opencode agent list` — для проверки агентов.

### Важно
Конфигурация запрещает архитектору прямые правки; кодер может редактировать файлы только в контексте порученной задачи. Разрешения shell и инструкции снижают риск, но не заменяют проверку команд перед подтверждением. Настройки и навыки созданы без изменения исходников.
