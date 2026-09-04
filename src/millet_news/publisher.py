from __future__ import annotations

import os
import time

import requests

from .http import retrying_session


class InstagramPublisher:
    def __init__(self, account_id: str | None = None, access_token: str | None = None, graph_version: str | None = None, timeout: int = 30) -> None:
        self.account_id = account_id or os.getenv("INSTAGRAM_ACCOUNT_ID", "")
        self.access_token = access_token or os.getenv("META_ACCESS_TOKEN", "")
        self.graph_version = graph_version or os.getenv("META_GRAPH_VERSION", "v26.0")
        self.timeout = timeout

    def publish(self, image_url: str, caption: str) -> str:
        if not self.account_id or not self.access_token:
            raise RuntimeError("INSTAGRAM_ACCOUNT_ID and META_ACCESS_TOKEN are required")
        session = retrying_session()
        base = f"https://graph.facebook.com/{self.graph_version}/{self.account_id}"
        create = session.post(f"{base}/media", data={"image_url": image_url, "caption": caption, "access_token": self.access_token}, timeout=self.timeout)
        create.raise_for_status()
        creation_id = create.json()["id"]
        for attempt in range(6):
            status = session.get(
                f"https://graph.facebook.com/{self.graph_version}/{creation_id}",
                params={"fields": "status_code,status", "access_token": self.access_token}, timeout=self.timeout,
            )
            status.raise_for_status()
            code = status.json().get("status_code")
            if code == "FINISHED":
                break
            if code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Meta media container failed: {status.json()}")
            time.sleep(min(2 ** attempt, 20))
        else:
            raise TimeoutError("Meta media container did not finish processing")
        publish = session.post(f"{base}/media_publish", data={"creation_id": creation_id, "access_token": self.access_token}, timeout=self.timeout)
        publish.raise_for_status()
        return str(publish.json()["id"])


class MockPublisher:
    def publish(self, image_url: str, caption: str) -> str:
        return "MOCK_INSTAGRAM_POST_ID"


def refresh_instagram_token(access_token: str | None = None, timeout: int = 30) -> dict:
    token = access_token or os.getenv("META_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN is required")
    response = retrying_session().get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
