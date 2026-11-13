"""Private workspace storage.

Saved work (organization facts, the funder pipeline, drafts, and the answer library) is kept as small
JSON files in a private GitHub repository, so it is free, versioned, and readable outside the app.
The public repository never holds any of it.

GitHubStore talks to the GitHub contents API with a fine-grained token that can only read and write
that one private repository. LocalStore keeps the same files in a folder, for development and tests.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import requests


class StoreError(RuntimeError):
    pass


class LocalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, name: str, default=None):
        path = self.root / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, name: str, data, message: str = "") -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def list(self, folder: str) -> list[str]:
        base = self.root / folder
        return sorted(p.name for p in base.glob("*.json")) if base.exists() else []

    def delete(self, name: str, message: str = "") -> None:
        (self.root / name).unlink(missing_ok=True)


class GitHubStore:
    API = "https://api.github.com"

    def __init__(self, repo: str, token: str, branch: str = "main"):
        self.repo, self.branch = repo, branch
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self._sha: dict[str, str] = {}

    def _url(self, name: str) -> str:
        return f"{self.API}/repos/{self.repo}/contents/{name}"

    def read(self, name: str, default=None):
        r = self.session.get(self._url(name), params={"ref": self.branch}, timeout=30)
        if r.status_code == 404:
            self._sha.pop(name, None)
            return default
        if not r.ok:
            raise StoreError(f"Could not read {name} (HTTP {r.status_code})")
        body = r.json()
        self._sha[name] = body["sha"]
        return json.loads(base64.b64decode(body["content"]).decode("utf-8"))

    def write(self, name: str, data, message: str = "") -> None:
        payload = {
            "message": message or f"Update {name}",
            "content": base64.b64encode(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")).decode(),
            "branch": self.branch,
        }
        for attempt in range(3):
            if name in self._sha:
                payload["sha"] = self._sha[name]
            r = self.session.put(self._url(name), json=payload, timeout=30)
            if r.ok:
                self._sha[name] = r.json()["content"]["sha"]
                return
            if r.status_code in (409, 422) and attempt < 2:  # someone else saved first; refresh and retry
                self.read(name)
                time.sleep(0.5)
                continue
            raise StoreError(f"Could not save {name} (HTTP {r.status_code})")

    def list(self, folder: str) -> list[str]:
        r = self.session.get(self._url(folder), params={"ref": self.branch}, timeout=30)
        if r.status_code == 404:
            return []
        if not r.ok:
            raise StoreError(f"Could not list {folder} (HTTP {r.status_code})")
        return sorted(item["name"] for item in r.json() if item["name"].endswith(".json"))

    def delete(self, name: str, message: str = "") -> None:
        if name not in self._sha and self.read(name) is None:
            return
        r = self.session.delete(self._url(name), json={"message": message or f"Delete {name}",
                                                       "sha": self._sha[name], "branch": self.branch}, timeout=30)
        if not r.ok:
            raise StoreError(f"Could not delete {name} (HTTP {r.status_code})")
        self._sha.pop(name, None)
