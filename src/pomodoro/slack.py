"""Slack alerts for when you start the timer and walk away.

Alerts are posted by a Slack bot and deleted again after a few hours, so the channel
doesn't fill up. Deleting needs a bot token (incoming webhooks can't delete messages).
Settings live outside the repo in ``%LOCALAPPDATA%\\Pomodoro\\slack.json``; the README
explains how to create the Slack app.

Network calls run on background threads. The UI thread reads failures from
:attr:`SlackAlerts.errors` instead of being called back.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import queue
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pomodoro.config import APP_NAME
from pomodoro.notify import ToastMessage

log = logging.getLogger(__name__)

API_URL = "https://slack.com/api/"
HTTP_TIMEOUT_S = 15
DEFAULT_DELETE_AFTER_HOURS = 3.0
CONNECTION_ERROR = "can't reach slack.com"
RETRY_ERRORS = frozenset({"ratelimited"})  # deletes failing with these (or offline) are retried at the next sweep

Transport = Callable[[str, dict[str, str]], dict[str, Any]]  # (API method, JSON body) -> parsed response
Runner = Callable[[Callable[[], None]], None]


def default_config_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "slack.json"


def default_log_path() -> Path:
    """Where posted messages are remembered until they are deleted."""
    return default_config_path().with_name("slack_posts.json")


@dataclass(frozen=True)
class SlackConfig:
    token: str
    channel: str
    mention_user_id: str | None = None
    delete_after_hours: float = DEFAULT_DELETE_AFTER_HOURS


def load_config(path: Path) -> SlackConfig | None:
    """Reads the Slack settings. Missing, unreadable or incomplete settings give None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))  # -sig: Notepad/PowerShell may add a BOM
        mention = str(data.get("mention_user_id") or "").strip()
        config = SlackConfig(
            token=str(data["token"]).strip(),
            channel=str(data["channel"]).strip(),
            mention_user_id=mention or None,
            delete_after_hours=max(0.0, float(data.get("delete_after_hours", DEFAULT_DELETE_AFTER_HOURS))),
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        log.warning("Ignoring unreadable Slack settings %s", path, exc_info=True)
        return None
    if not config.token or not config.channel:
        log.warning("Slack settings %s need both a token and a channel", path)
        return None
    return config


def format_alert(message: ToastMessage, mention_user_id: str | None = None) -> str:
    """Slack text for a phase change; mentioning the user makes Slack push it to their phone."""
    text = f"*{message.title}*\n{message.body}"
    return f"<@{mention_user_id}> {text}" if mention_user_id else text


@dataclass(frozen=True)
class PostedMessage:
    channel: str
    ts: str  # Slack's message id
    posted_at: float  # time.time() when posted


def load_posts(path: Path) -> list[PostedMessage]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [PostedMessage(str(p["channel"]), str(p["ts"]), float(p["posted_at"])) for p in data]
    except FileNotFoundError:
        return []
    except (OSError, ValueError, TypeError, KeyError):
        log.warning("Ignoring unreadable Slack post log %s", path, exc_info=True)
        return []


def save_posts(path: Path, posts: list[PostedMessage]) -> None:
    """Writes the post log atomically, so a crash mid-write never loses track of messages."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(p) for p in posts], indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        log.warning("Could not save Slack post log to %s", path, exc_info=True)


def http_call(token: str, method: str, payload: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        API_URL + method,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        result: dict[str, Any] = json.loads(response.read())
    return result


def run_in_thread(work: Callable[[], None]) -> None:
    # Not a daemon: closing the app waits for an in-flight post to be logged, so it still gets deleted
    threading.Thread(target=work, name="slack").start()


class SlackAlerts:
    def __init__(
        self,
        config: SlackConfig,
        log_path: Path,
        *,
        transport: Transport | None = None,
        clock: Callable[[], float] = time.time,
        run: Runner = run_in_thread,
    ) -> None:
        self.config = config
        self.log_path = log_path
        self._call = transport or functools.partial(http_call, config.token)
        self._clock = clock
        self._run = run
        self._lock = threading.Lock()  # guards the post log file
        self.errors: queue.SimpleQueue[str] = queue.SimpleQueue()  # short messages for the UI to show

    def post(self, text: str) -> None:
        """Posts ``text`` to the channel in the background and remembers it for deletion."""
        self._run(functools.partial(self._post, text))

    def delete_expired(self) -> None:
        """Deletes, in the background, every posted message older than the configured limit."""
        self._run(self._delete_expired)

    def _post(self, text: str) -> None:
        result, error = self._request("chat.postMessage", {"channel": self.config.channel, "text": text})
        if result is None:
            self.errors.put(f"Slack: {error}")
            return
        posted = PostedMessage(str(result["channel"]), str(result["ts"]), self._clock())
        with self._lock:
            save_posts(self.log_path, [*load_posts(self.log_path), posted])

    def _delete_expired(self) -> None:
        cutoff = self._clock() - self.config.delete_after_hours * 3600
        with self._lock:
            expired = [p for p in load_posts(self.log_path) if p.posted_at <= cutoff]
        finished: set[tuple[str, str]] = set()
        for post in expired:
            result, error = self._request("chat.delete", {"channel": post.channel, "ts": post.ts})
            if result is not None or error == "message_not_found":
                finished.add((post.channel, post.ts))
            elif error not in RETRY_ERRORS and error != CONNECTION_ERROR:
                finished.add((post.channel, post.ts))  # can never be deleted: stop trying
                self.errors.put(f"Slack: couldn't delete an alert ({error})")
        if finished:
            # Re-read: a post may have been logged while the deletes ran
            with self._lock:
                remaining = [p for p in load_posts(self.log_path) if (p.channel, p.ts) not in finished]
                save_posts(self.log_path, remaining)

    def _request(self, method: str, payload: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
        """Calls the API. Returns the response if it succeeded, otherwise None and the error."""
        try:
            result = self._call(method, payload)
        except (OSError, ValueError):
            log.warning("Slack %s failed", method, exc_info=True)
            return None, CONNECTION_ERROR
        if result.get("ok"):
            return result, ""
        error = str(result.get("error") or "unknown error")
        log.warning("Slack %s failed: %s", method, error)
        return None, error


def connect(config_path: Path | None = None, log_path: Path | None = None) -> SlackAlerts | None:
    """Slack alerts from the settings file, or None if Slack isn't set up."""
    config = load_config(config_path or default_config_path())
    return SlackAlerts(config, log_path or default_log_path()) if config else None
