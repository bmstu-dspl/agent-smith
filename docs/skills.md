# Agent Skills

Agent Smith supports global, text-only [Agent Skills](https://agentskills.io/specification).
Each skill maps to the required parts of a `SKILL.md` file:

- `name`: lowercase letters, numbers, and hyphens; at most 64 characters;
- `description`: what the skill does and when the agent must use it;
- `instructions`: the Markdown workflow loaded after activation.

Enabled skill names and descriptions are included in the agent's discovery prompt.
When a request matches a description, the agent calls the local `load_skill` tool and
receives the full instructions. Disabled and deleted skills cannot be loaded. Changes
are visible on the next agent request; the services do not need to be restarted.

Skills guide the model through prompts. They do not enforce a deterministic state
machine. Workflows that require hard guarantees should also use runtime validation or
a dedicated workflow engine.

## Managing skills

1. Open **Admin → Skills**.
2. Enter the name, a trigger-oriented description, and Markdown instructions.
3. Save the skill. New skills are enabled by default.
4. Use **Disable** to remove a skill from discovery without deleting its content.
5. Use **Delete** only when the skill should be removed permanently.

Changing a skill increments both its version and the catalog revision. An already
loaded older version is removed from the LLM context before the next response.

## Room availability template

Create this skill through the admin panel; it is intentionally not seeded by a database
migration so the universal runtime remains domain-neutral.

**Name**

```text
room-availability
```

**Description**

```text
Используй, когда пользователь просит найти, показать или проверить свободные номера в отеле, уточняет доступность на даты либо меняет параметры такого поиска.
```

**Instructions**

```markdown
# Поиск свободных номеров

1. До поиска собери только параметры, необходимые схеме MCP-инструмента доступности:
   даты заезда и выезда, количество взрослых, а также количество и возраст детей,
   если инструмент этого требует.
2. Не спрашивай ФИО, телефон, email, паспортные или платежные данные: для проверки
   доступности они не нужны.
3. Если даты относительные или неполные, сначала используй `get_current_datetime`,
   затем уточни или нормализуй даты.
4. Пока обязательных параметров недостаточно, используй `ask_user` и не вызывай MCP.
5. После получения всех обязательных параметров один раз вызови именно TravelLine
   MCP-инструмент с каноническим именем `search_available_rooms`. Адаптер Agent Smith
   добавляет к нему namespace вида
   `mcp_<первые 8 символов server_id>__search_available_rooms`, поэтому выбери среди
   доступных инструментов полное имя с этим точным окончанием. Не используй другой
   search-инструмент и не угадывай значение namespace.
6. Считай один элемент ответа тарифным вариантом, а не обязательно отдельной категорией
   номера: одинаковый `room_id` может встречаться несколько раз с разным питанием,
   ценой или условиями отмены. Объедини такие элементы в один понятный вариант номера,
   если их различия можно корректно показать как несколько цен/тарифов.
7. Отранжируй всю полученную выборку по запросу пользователя. Сначала покажи самые подходящие
   варианты с учётом состава гостей, питания, цены, отмены и доступности.
   Не утверждай, что вариант обладает характеристикой, которой нет в данных MCP.
8. В одном сообщении показывай не более 3 вариантов. После ранжирования перед показом
   один раз для текущей тройки вызови TravelLine-инструмент `get_room_details`, передав
   не более 3 `room_id`. Не вызывай его отдельно для каждого номера. Он получает данные
   из Content cache и возвращает официальное название, описание, характеристики и
   `image_urls`. Если детали временно недоступны, всё равно покажи компактные результаты
   `search_available_rooms`, не повторяя поиск доступности.
9. Каждый вариант оформляй строго так:

   **Название или категория номера**
   *Цена или варианты цены*
   Короткая выжимка, почему вариант подходит запросу пользователя; добавь только реально
   полученные характеристики, например питание, размещение, бесплатную отмену и остаток.
   [Забронировать](booking_link)

   Если официального названия/категории нет, не придумывай его: используй нейтральный
   заголовок вроде **Вариант 1 — размещение для двух взрослых**. Если объединяешь тарифы
   одной категории, укажи отдельную цену и соответствующую ссылку «Забронировать» для
   каждого тарифа: разные `rate_plan_id` обычно имеют разные `booking_link`.
10. Если после показанной тройки остались результаты, закончи сообщение фразой о том,
   что есть ещё варианты, и предложи показать их. На просьбу показать ещё продолжай со
   следующей тройки уже полученной и ранжированной выборки. Не вызывай `search_available_rooms` повторно,
   пока эта выборка не исчерпана и пользователь не
   изменил даты, состав гостей или иной параметр, влияющий на доступность.
11. Ссылка должна использовать ровно непустой `booking_link` соответствующего результата
    и видимый текст «Забронировать». Если ссылка отсутствует, не конструируй её: честно
    сообщи, что прямая ссылка недоступна. Не собирай ФИО, телефон, email или платёжные
    данные для перехода к форме.
12. Если `get_room_details` вернул непустой список `image_urls`, перед заголовком варианта
    добавь Rich Markdown-блок `<tg-slideshow>` с изображениями в исходном порядке:

    <tg-slideshow>

    ![](https://example.com/room-1.jpg)
    ![](https://example.com/room-2.jpg)

    </tg-slideshow>

    Используй не более 10 изображений на вариант и не более 50 медиа во всём сообщении.
    Используй только полученные публичные HTTP(S)-ссылки; не скачивай изображения и не
    подставляй другие URL. Если изображений нет, просто начни с заголовка.
13. Если MCP вернул ошибку, объясни её без выдумывания результатов; при невозможности
    продолжить используй `handoff_to_operator`.
```

After creating the skill, verify the tool trace in staging: `load_skill` must precede
the availability MCP call, and no availability call should occur while required search
parameters are still missing.

Partial replies are throttled and streamed with Telegram's native
`sendRichMessageDraft`; the completed reply is persisted with `sendRichMessage` and
`InputRichMessage.markdown`. Chats that reject rich drafts keep the ordinary editable
placeholder and convert it to a Rich Message at the end. If Telegram also rejects that,
the bot falls back to a deliberately small, HTML-escaped subset: `**bold**`, `*italic*`,
and `[label](https://...)`.
