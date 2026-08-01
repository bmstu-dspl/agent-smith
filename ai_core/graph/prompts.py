from shared.agent_prompts import CORE_SYSTEM_PROMPT, DEFAULT_PERSONA_PROMPT


# Backward-compatible composed prompt for code importing the historical name.
AGENT_SYSTEM_PROMPT = f"{CORE_SYSTEM_PROMPT}\n\nПерсона:\n{DEFAULT_PERSONA_PROMPT}"


RAG_QUERY_EXTRACTOR_PROMPT = """Ты преобразуешь сообщение пользователя в поисковый запрос для RAG.
  Не отвечай пользователю.
  Не добавляй факты, которых нет в сообщении.
  Убери приветствия, благодарности, эмоции, вводные слова и лишнюю вежливость.
  Сохрани только смысл запроса: тему, ключевые слова, сущности, параметры и ограничения.
  Если сообщение слишком короткое, всё равно выдели лучший возможный поисковый запрос.

  Верни только JSON без markdown и пояснений:
  {
    "topic": "краткая тема",
    "keywords": ["ключевое слово или сущность"],
    "constraints": ["важное ограничение или параметр"]
  }
  """
