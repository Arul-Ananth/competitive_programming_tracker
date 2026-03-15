import hashlib


def normalize_link(link: str) -> str:
    return link.strip().lower()


def build_fallback_key(platform: str, title: str, date: str, username: str) -> str:
    raw = f"{platform.strip().lower()}|{title.strip().lower()}|{date.strip()}|{username.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

