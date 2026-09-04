from __future__ import annotations

import os

import requests

from .http import retrying_session


def notify_failure(message: str, timeout: int = 15) -> None:
    url = os.getenv("FAILURE_WEBHOOK_URL", "")
    if not url:
        return
    response = retrying_session(total=2, retry_post=True).post(url, json={"content": f"Millet Daily failure: {message[:1500]}"}, timeout=timeout)
    response.raise_for_status()
