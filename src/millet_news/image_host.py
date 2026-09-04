from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from urllib.parse import quote

import requests

from .http import retrying_session


class GitHubImageHost:
    """Uploads a generated image to a public GitHub repository using its Contents API."""

    def __init__(self, token: str | None = None, repository: str | None = None, branch: str | None = None, timeout: int = 30) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.repository = repository or os.getenv("GITHUB_REPOSITORY", "")
        self.branch = branch or os.getenv("GITHUB_BRANCH", "main")
        self.timeout = timeout

    def upload(self, local_path: str | Path, remote_path: str | None = None) -> str:
        path = Path(local_path)
        if not self.token or not self.repository:
            raise RuntimeError("GITHUB_TOKEN and GITHUB_REPOSITORY are required to host an image for Meta")
        remote = remote_path or f"published-assets/{path.name}"
        endpoint = f"https://api.github.com/repos/{self.repository}/contents/{quote(remote)}"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        payload = {
            "message": f"Publish Instagram asset {path.name}",
            "content": base64.b64encode(path.read_bytes()).decode("ascii"),
            "branch": self.branch,
        }
        session = retrying_session()
        response = session.put(endpoint, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        download_url = response.json()["content"]["download_url"]
        for _ in range(5):
            probe = session.head(download_url, timeout=self.timeout)
            if probe.ok:
                return download_url
            time.sleep(2)
        raise RuntimeError("Uploaded image did not become publicly reachable in time")
