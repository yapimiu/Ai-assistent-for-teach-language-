---
name: testing-and-delivery
description: Testing and safe delivery; activate when relevant to changes in Romanian B1 tutor.
---

# Testing and safe delivery

Сначала pytest/unit, потом только разрешённые интеграционные тесты на отдельной временной PostgreSQL БД. Проверяй uv run pytest -q, изменения в git diff, потенциальную утечку секретов; не объявляй интеграции испытанными, если тест пропущен. Docker/production/Telegram запуск — самостоятельное действие владельца.

После работы отчитайся о файлах, тестах и рисках.
