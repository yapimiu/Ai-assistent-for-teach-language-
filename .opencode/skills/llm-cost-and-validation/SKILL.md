---
name: llm-cost-and-validation
description: LLM API reliability; activate when relevant to changes in Romanian B1 tutor.
---

# LLM API reliability

OpenRouter вызывается через защищённый клиент; сообщения модели считаются недоверенными и проверяются Pydantic. Учитывай токены, retries, стоимость и отсутствие usage; избегай полного диалога в каждом запросе и логирования ответов учащихся. Не скрывай невалидные результаты.

После работы отчитайся о файлах, тестах и рисках.
