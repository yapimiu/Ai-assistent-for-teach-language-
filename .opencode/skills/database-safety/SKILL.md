---
name: database-safety
description: PostgreSQL and Alembic safety; activate when relevant to changes in Romanian B1 tutor.
---

# PostgreSQL and Alembic safety

Не запускай миграции на production или пользовательской БД. Перед интеграционными тестами проверь TEST_DATABASE_URL и запрети пересечение с DATABASE_URL. Не очищай docker volumes; никогда не используй docker compose down -v. Изменение schema требует Alembic миграции и отката/совместимости.

После работы отчитайся о файлах, тестах и рисках.
