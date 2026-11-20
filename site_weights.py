# site_weights.py — knowledge base about sites.

STRONG_SITES = {
    "GitHub": "программисты, ники часто уникальны",
    "GitLab": "программисты",
    "Keybase": "криптография, ники верифицируются",
    "HackerNews": "техническая аудитория",
    "Bandcamp": "музыканты",
    "Behance": "дизайнеры",
    "Dribbble": "дизайнеры",
    "Telegram": "ники обычно уникальны",
    "VK": "русскоязычная соцсеть",
}

MEDIUM_SITES = {
    "Twitter": "миллионник, ник может быть занят брендом",
    "Instagram": "миллионник",
    "Reddit": "средний, много ников",
    "Steam": "геймеры, ники повторяются",
    "SoundCloud": "музыканты",
    "TikTok": "миллионник, но bio и fullname — сильные сигналы",
    "Twitch": "стримы, метаданные дают created_at",
    "Patreon": "авторы",
}

WEAK_SITES = {
    "About.me": "лендинг-визитка, может быть заброшена",
    "Gravatar": "аватарки, не связано с профилем",
    "Imgur": "хостинг картинок",
    "Pastebin": "временные вещи",
    "WordPress": "миллионы заброшенных",
    "Blogger": "то же",
    "LiveJournal": "мёртвый журнал",
}


def get_site_weight(site_name: str) -> str:
    site_lower = site_name.lower()
    for name in STRONG_SITES:
        if name.lower() in site_lower:
            return "strong"
    for name in MEDIUM_SITES:
        if name.lower() in site_lower:
            return "medium"
    for name in WEAK_SITES:
        if name.lower() in site_lower:
            return "weak"
    return "unknown"


def build_site_dictionary() -> str:
    lines = ["БАЗА ЗНАНИЙ О САЙТАХ (используй при оценке сигналов):\n"]
    lines.append("СИЛЬНЫЕ СИГНАЛЫ:")
    for site, note in STRONG_SITES.items():
        lines.append(f"  • {site} — {note}")
    lines.append("\nСРЕДНИЕ СИГНАЛЫ:")
    for site, note in MEDIUM_SITES.items():
        lines.append(f"  • {site} — {note}")
    lines.append("\nСЛАБЫЕ СИГНАЛЫ:")
    for site, note in WEAK_SITES.items():
        lines.append(f"  • {site} — {note}")
    return "\n".join(lines)

