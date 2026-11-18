import logging

import httpx

from . import config

log = logging.getLogger("ntfy")


def send(title: str, message: str, tags: list[str] | None = None, priority: int = 3) -> None:
    if not config.NTFY_URL:
        log.warning("ntfy not configured: %s – %s", title, message)
        return
    payload = {
        "topic": config.NTFY_TOPIC,
        "title": title,
        "message": message,
        "tags": tags or [],
        "priority": priority,
    }
    if config.PUBLIC_URL:
        payload["click"] = config.PUBLIC_URL
    headers = {"Authorization": f"Bearer {config.NTFY_TOKEN}"} if config.NTFY_TOKEN else {}
    try:
        httpx.post(config.NTFY_URL, json=payload, headers=headers, timeout=10).raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("ntfy send failed: %s", exc)
