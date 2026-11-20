# web_i18n.py — English translations for the web interface.
#
# The web UI is written in Russian in templates/index.html and static/app.js.
# This module maps Russian UI strings to English. Static HTML uses Jinja's
# `wt()` helper; dynamic JavaScript uses `tr()` / `tf()` from static/i18n.js.
#
# Keys are the exact Russian text nodes / attribute values. Templates that
# contain runtime values use {placeholders} and are formatted by `tf()`.

WEB_EN = {
    # ------------------------------------------------------------
    # Head / header
    # ------------------------------------------------------------
    "Skyfall OSINT Helper — локальный анализ открытых источников":
        "Skyfall OSINT Helper — local open-source intelligence analysis",
    "Skyfall — OSINT Helper": "Skyfall — OSINT Helper",
    "Локальный OSINT-анализ": "Local OSINT analysis",
    "Все расследования": "All investigations",
    "Настроить провайдера LLM": "Configure the LLM provider",
    "Активный LLM-провайдер": "Active LLM provider",
    "LLM: проверка…": "LLM: checking…",
    "Проверка связи…": "Checking connection…",
    "📂 Расследования": "📂 Investigations",
    "LLM: нет связи": "LLM: no connection",
    "Бэкенд недоступен": "Backend unavailable",
    "AI отключён в config.py (USE_AI=False)": "AI is disabled in config.py (USE_AI=False)",

    # ------------------------------------------------------------
    # Form
    # ------------------------------------------------------------
    "Что ищем?": "What are we looking for?",
    "Тип данных": "Data type",
    "Тип входных данных": "Input data type",
    "Ник": "Username",
    "Email": "Email",
    "Домен": "Domain",
    "Значение": "Value",
    "Например: octocat": "Example: octocat",
    "Введи ник, который хочешь проверить.": "Enter the username you want to check.",
    "Куда добавить результат": "Where to add the result",
    "＋ Новое расследование": "＋ New investigation",
    "Выбери прошлое расследование — новые звенья добавятся в его граф, а не в отдельный.":
        "Choose a previous investigation — new nodes will be added to its graph instead of a separate one.",
    "Связать новый запрос с звеном": "Link the new request to a node",
    "— без связи —": "— no link —",
    "— в расследовании пока нет звеньев —":
        "— the investigation has no nodes yet —",
    "Новый запрос появится в графе и сразу соединится с выбранным звеном.":
        "The new request will appear in the graph and connect to the selected node.",
    "Пропустить фильтрацию и анализ через LLM": "Skip LLM filtering and analysis",
    "Режим без AI": "No AI mode",
    "Быстрее: только сбор и сырые данные": "Faster: collection and raw data only",
    "🔎 Расследовать": "🔎 Investigate",
    "Идёт расследование…": "Investigation in progress…",

    # ------------------------------------------------------------
    # Progress / error
    # ------------------------------------------------------------
    "Идёт сбор данных и анализ…": "Collecting data and analyzing…",
    "Sherlock и Maigret проверяют тысячи сайтов. AI-этапы могут занять несколько минут; если LLM недоступна или не уложилась в таймаут, Skyfall покажет сырые данные.":
        "Sherlock and Maigret are checking thousands of sites. AI stages can take several minutes; "
        "if the LLM is unavailable or times out, Skyfall will show raw data.",
    "Ошибка": "Error",
    "Ошибка анализа: {error}": "Analysis error: {error}",
    "AI недоступен: {notice}": "AI unavailable: {notice}",

    # ------------------------------------------------------------
    # Investigation bar / meta
    # ------------------------------------------------------------
    "Расследование": "Investigation",
    "Сохранить полную HTML-страницу в saved_pages/":
        "Save the full HTML page to saved_pages/",
    "💾 Сохранить страницу": "💾 Save page",
    "Запрос": "Query",
    "Тип": "Type",
    "Режим": "Mode",
    "Собрано": "Collected",
    "Отчёт": "Report",

    # ------------------------------------------------------------
    # Result sections
    # ------------------------------------------------------------
    "📝 Сводка": "📝 Summary",
    "🧠 Ход мысли модели": "🧠 Model reasoning",
    "🔎 Сущности": "🔎 Entities",
    "🔗 Связи": "🔗 Connections",
    "⚠️ Замечания": "⚠️ Notes",
    "Противоречия": "Contradictions",
    "Неясности": "Uncertainties",
    "🌳 Дерево рассуждений": "🌳 Reasoning tree",
    "🧹 Фильтрация сайтов": "🧹 Site filtering",
    "Оставлено": "Kept",
    "Отброшено": "Dropped",
    "🧠 Ход мысли на этапе фильтрации": "🧠 Filtering reasoning",
    "найдено в: ": "found in: ",
    "Доказательство: ": "Evidence: ",
    "Почему: ": "Why: ",
    "(нет данных)": "(no data)",

    # ------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------
    "🕸 Граф расследования": "🕸 Investigation graph",
    "0 связей": "0 connections",
    "Создать собственное звено": "Create a custom node",
    "＋ Звено": "＋ Node",
    "Соединить два звена": "Link two nodes",
    "🔗 Связь": "🔗 Link",
    "Перераскладочка графа": "Re-layout the graph",
    "⟲ Разложить": "⟲ Layout",
    "Вписать граф в окно": "Fit the graph to the window",
    "Клик по карточке — источник и заметка · тяни карточки мышью · колесо — зум · фон — панорама":
        "Click a card for its source and note · drag cards with the mouse · "
        "wheel to zoom · drag the background to pan",
    "Кликни по первому звену…": "Click the first node…",
    "Отмена": "Cancel",
    "📌 Звенья, источники и заметки": "📌 Nodes, sources, and notes",
    "📦 Сырые данные (raw_data)": "📦 Raw data (raw_data)",
    "Скачать последний лог-файл Skyfall": "Download the latest Skyfall log file",
    "📥 Скачать логи": "📥 Download logs",

    # Graph node types / legend
    "субъект": "subject",
    "ник": "username",
    "домен": "domain",
    "ссылка": "link",
    "своё звено": "custom node",
    "сущность": "entity",
    "связь": "link",
    "найдено": "found",
    "Добавлено вручную": "Added manually",
    "сильная связь": "strong connection",
    "средняя": "medium",
    "слабая": "weak",
    "Граф пуст": "The graph is empty",
    "Нажми «＋ Звено», чтобы добавить первое звено.":
        "Click “＋ Node” to add the first node.",
    "Пока нет ни одного звена.": "No nodes yet.",
    "Связей пока нет.": "No connections yet.",
    "Звенья ({count})": "Nodes ({count})",
    "Связи ({count})": "Connections ({count})",
    "{count} связей": "{count} connections",

    # Node card popup
    "Закрыть": "Close",
    "Источник": "Source",
    "ссылка не указана": "no source link",
    "Заметка": "Note",
    "Что известно об этом звене…": "What is known about this node…",
    "✓ сохранено": "✓ saved",
    "Откуда": "Origin",
    "🔗 Связать": "🔗 Link",
    "✏ Изменить": "✏ Edit",
    "🗑 Удалить": "🗑 Delete",
    "Изменить звено": "Edit node",
    "Новое звено": "New node",

    # Connection popup
    "Связь": "Connection",
    "Подпись связи": "Connection label",
    "Уверенность": "Confidence",
    "высокая": "high",
    "низкая": "low",
    "Заметка к связи": "Connection note",
    "Почему эти звенья связаны…": "Why are these nodes connected…",
    "Доказательство": "Evidence",
    "Почему": "Why",
    "🗑 Удалить связь": "🗑 Delete connection",

    # ------------------------------------------------------------
    # Graph actions / toasts
    # ------------------------------------------------------------
    "Сначала создай расследование или добавь звено.":
        "Create an investigation or add a node first.",
    "Нужно хотя бы два звена, чтобы создать связь.":
        "At least two nodes are required to create a connection.",
    "Связь создана.": "Connection created.",
    "Такая связь уже была.": "This connection already exists.",
    "Звено удалено.": "Node deleted.",
    "Удалить эту связь?": "Delete this connection?",
    "Связь удалена.": "Connection deleted.",
    "Звено обновлено.": "Node updated.",
    "Звено добавлено в граф.": "Node added to the graph.",
    "«{label}» выбран. Кликни по второму звену…":
        "“{label}” selected. Click the second node…",
    "Удалить звено «{label}»? Связи с ним тоже удалятся.":
        "Delete the node “{label}”? Its connections will be removed too.",
    "Не удалось создать связь: {error}": "Could not create the connection: {error}",
    "Не удалось удалить звено: {error}": "Could not delete the node: {error}",
    "Не удалось удалить связь: {error}": "Could not delete the connection: {error}",
    "Не удалось сохранить связь: {error}": "Could not save the connection: {error}",
    "Не удалось сохранить заметку: {error}": "Could not save the note: {error}",
    "Не удалось сохранить звено: {error}": "Could not save the node: {error}",

    # ------------------------------------------------------------
    # Node modal
    # ------------------------------------------------------------
    "Название": "Name",
    "Например: john.doe@mail.com": "Example: john.doe@mail.com",
    "Своё звено": "Custom node",
    "Ссылка / сайт": "Link / website",
    "Сущность": "Entity",
    "Субъект (центр)": "Subject (center)",
    "Номер": "Number",
    "Ссылка на источник": "Source link",
    "Ссылка на профиль, страницу, отчёт — что угодно.":
        "A link to a profile, page, report — anything.",
    "Описание": "Description",
    "Короткая подпись под названием звена":
        "A short caption under the node name",
    "Почему это звено важно, что о нём известно":
        "Why this node matters and what is known about it",
    "Сохранить": "Save",

    # ------------------------------------------------------------
    # Investigations modal
    # ------------------------------------------------------------
    "Мои расследования": "My investigations",
    "Данные хранятся в папке": "Data is stored in the folder",
    "🖫 Сохранённые HTML-страницы": "🖫 Saved HTML pages",
    "Название расследования": "Investigation name",
    "Новое расследование": "New investigation",
    "Создано новое расследование.": "New investigation created.",
    "Пока нет расследований. Начни с поиска.":
        "No investigations yet. Start with a search.",
    "Без названия": "Untitled",
    "Удалить расследование": "Delete investigation",
    "Расследование удалено.": "Investigation deleted.",
    "Загрузка…": "Loading…",
    "Сохранённых страниц пока нет.": "No saved pages yet.",
    "Открыть": "Open",
    "Открыто: {title}": "Opened: {title}",
    "Не удалось открыть расследование: {error}":
        "Could not open the investigation: {error}",
    "Не удалось удалить: {error}": "Could not delete: {error}",
    "Удалить расследование «{title}»?": "Delete the investigation “{title}”?",
    "Не удалось создать расследование: {error}":
        "Could not create the investigation: {error}",
    "{title} — {nodes} зв. / {searches} поиск.":
        "{title} — {nodes} nodes / {searches} searches",
    "{nodes} звеньев · {edges} связей · {searches} поисков":
        "{nodes} nodes · {edges} connections · {searches} searches",
    "{nodes} звеньев · {edges} связей · {searches} поисков · {date}":
        "{nodes} nodes · {edges} connections · {searches} searches · {date}",
    "последний запрос: {value}": "last query: {value}",
    "Ошибка: {error}": "Error: {error}",
    "{size} КБ": "{size} KB",

    # ------------------------------------------------------------
    # LLM settings
    # ------------------------------------------------------------
    "Настройки LLM": "LLM settings",
    "Провайдер": "Provider",
    "Ollama (локально)": "Ollama (local)",
    "Модель": "Model",
    "Модель Ollama": "Ollama model",
    "API-ключ": "API key",
    "Ключ хранится только локально в": "The key is stored locally only in",
    "Base URL": "Base URL",
    "Для OpenRouter укажите ключ OpenRouter и базовый URL":
        "For OpenRouter, enter the OpenRouter key and base URL",
    ". Для OpenAI — ключ OpenAI. Настройки применяются сразу и сохраняются между перезапусками.":
        ". For OpenAI, use an OpenAI key. Settings apply immediately and persist across restarts.",
    "Проверить": "Check",
    "Проверка подключения…": "Checking connection…",
    "Загрузка настроек…": "Loading settings…",
    "Нажмите «Проверить», чтобы протестировать сохранённые настройки.":
        "Click “Check” to test the saved settings.",
    "Сохранение…": "Saving…",
    "Настройки LLM сохранены.": "LLM settings saved.",
    "Ключ не задан. Для облачного провайдера он обязателен.":
        "No API key set. A key is required for a cloud provider.",
    "Сохранён: {key}": "Saved: {key}",
    "Ключ уже сохранён ({key}). Оставьте поле пустым, чтобы не менять.":
        "A key is already saved ({key}). Leave the field empty to keep it.",
    "LLM доступна: {provider} / {model}": "LLM available: {provider} / {model}",
    "LLM недоступна: {provider} / {model}": "LLM unavailable: {provider} / {model}",
    "{provider} недоступна": "{provider} unavailable",
    "✓ {label} · {model} — доступна": "✓ {label} · {model} — available",
    "✗ {label} · {model} — {error}": "✗ {label} · {model} — {error}",
    "недоступна": "unavailable",
    "Не удалось загрузить настройки: {error}":
        "Could not load settings: {error}",
    "Не удалось сохранить: {error}": "Could not save: {error}",
    "Ошибка проверки: {error}": "Check failed: {error}",

    # ------------------------------------------------------------
    # Pages / logs / saved snapshot
    # ------------------------------------------------------------
    "Лог-файл скачан.": "Log file downloaded.",
    "Не удалось скачать логи: {error}": "Could not download logs: {error}",
    "Сначала проведи поиск или создай расследование.":
        "Run a search or create an investigation first.",
    "Skyfall — анализ": "Skyfall — analysis",
    "Skyfall · сохранённая страница анализа": "Skyfall · saved analysis page",
    "открыть страницу": "open page",
    "Сохранено в {path} · ": "Saved to {path} · ",
    "{title}, {date}. ": "{title}, {date}. ",
    "Страница сохранена: {name}": "Page saved: {name}",
    "Не удалось сохранить страницу: {error}": "Could not save the page: {error}",
    "Звеньев: {nodes}, связей: {edges}.": "Nodes: {nodes}, connections: {edges}.",
    "+{count} звеньев": "+{count} nodes",
    "+{count} связей": "+{count} connections",
    "В граф расследования добавлено: {parts}.":
        "Added to the investigation graph: {parts}.",
    "Поиск выполнен, но в граф не добавлен: {error}":
        "The search completed but was not added to the graph: {error}",
    "Не удалось переименовать: {error}": "Could not rename: {error}",
    "Название обновлено.": "Name updated.",
    "Граф разложен заново.": "Graph re-laid out.",

    # ------------------------------------------------------------
    # Mode badges / hints
    # ------------------------------------------------------------
    "Нет данных": "No data",
    "Raw Mode": "Raw Mode",
    "Raw fallback": "Raw fallback",
    "AI": "AI",
    "Введи значение для поиска.": "Enter a value to search for.",
    "Неизвестная ошибка": "Unknown error",
    "Например: user@example.com": "Example: user@example.com",
    "Проверим, где зарегистрирован этот email (Holehe).":
        "Check where this email is registered (Holehe).",
    "Например: example.com": "Example: example.com",
    "Соберём emails и субдомены через theHarvester.":
        "Collect emails and subdomains with the Harvester.",

    # ------------------------------------------------------------
    # Progress copy (JS)
    # ------------------------------------------------------------
    "Идёт поиск по нику…": "Searching by username…",
    "Sherlock и Maigret проверяют тысячи сайтов. AI отключён: будут показаны сырые профили.":
        "Sherlock and Maigret are checking thousands of sites. "
        "AI is off: raw profiles will be shown.",
    "Идёт поиск по email…": "Searching by email…",
    "Holehe проверяет, где зарегистрирован email. Если Holehe не найдёт сайтов, запустится Diablinda. Затем LLM фильтрует и анализирует результаты.":
        "Holehe checks where the email is registered. If Holehe finds no sites, "
        "Diablinda runs as a fallback. The LLM then filters and analyzes the results.",
    "Holehe проверяет, где зарегистрирован email. Если Holehe не найдёт сайтов, запустится Diablinda. AI отключён: будут показаны сырые данные.":
        "Holehe checks where the email is registered. If Holehe finds no sites, "
        "Diablinda runs as a fallback. AI is off: raw data will be shown.",
    "Идёт анализ домена…": "Analyzing the domain…",
    "theHarvester собирает emails, субдомены и хосты, ThreatFox проверяет IOC. Затем LLM фильтрует и анализирует данные.":
        "theHarvester collects emails, subdomains, and hosts; ThreatFox checks IOCs. "
        "The LLM then filters and analyzes the data.",
    "theHarvester собирает emails, субдомены и хосты, ThreatFox проверяет IOC. AI отключён: будут показаны сырые данные.":
        "theHarvester collects emails, subdomains, and hosts; ThreatFox checks IOCs. "
        "AI is off: raw data will be shown.",
}


def translations_for(lang: str) -> dict:
    """Returns the web translation map for the active language."""
    return WEB_EN if str(lang).lower().startswith("en") else {}


def translate(text: str, lang: str) -> str:
    """Translates a single web UI string; Russian is returned as-is."""
    if not text:
        return text
    if not str(lang).lower().startswith("en"):
        return text
    return WEB_EN.get(text, text)
