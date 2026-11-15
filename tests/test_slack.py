"""Slack alerts against a fake Slack API: no network, no threads."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pomodoro import slack
from pomodoro.notify import ToastMessage
from pomodoro.slack import PostedMessage, SlackAlerts, SlackConfig

HOUR = 3600.0


class FakeSlack:
    """Records API calls and answers like Slack does."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.next_ts = 1
        self.fail_with: str | None = None  # Slack error code to return
        self.offline = False

    def __call__(self, method: str, payload: dict[str, str]) -> dict[str, Any]:
        if self.offline:
            raise OSError("no network")
        self.calls.append((method, payload))
        if self.fail_with:
            return {"ok": False, "error": self.fail_with}
        if method == "chat.postMessage":
            ts = f"1700000000.{self.next_ts:06d}"
            self.next_ts += 1
            return {"ok": True, "channel": payload["channel"], "ts": ts}
        return {"ok": True}

    def deleted(self) -> list[str]:
        return [p["ts"] for m, p in self.calls if m == "chat.delete"]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def run_now(work: Callable[[], None]) -> None:
    work()


@pytest.fixture
def api() -> FakeSlack:
    return FakeSlack()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def alerts(tmp_path: Path, api: FakeSlack, clock: FakeClock) -> SlackAlerts:
    config = SlackConfig(token="xoxb-test", channel="C123", delete_after_hours=3)
    return SlackAlerts(config, tmp_path / "posts.json", transport=api, clock=clock, run=run_now)


def test_post_sends_to_channel_and_logs_message(alerts: SlackAlerts, api: FakeSlack) -> None:
    alerts.post("hello")
    assert api.calls == [("chat.postMessage", {"channel": "C123", "text": "hello"})]
    assert slack.load_posts(alerts.log_path) == [PostedMessage("C123", "1700000000.000001", 1_000_000.0)]


def test_only_messages_past_the_limit_are_deleted(alerts: SlackAlerts, api: FakeSlack, clock: FakeClock) -> None:
    alerts.post("old")
    clock.now += 2 * HOUR
    alerts.post("new")
    clock.now += 1 * HOUR  # "old" is now exactly 3h old, "new" 1h
    alerts.delete_expired()
    assert api.deleted() == ["1700000000.000001"]
    assert [p.ts for p in slack.load_posts(alerts.log_path)] == ["1700000000.000002"]


def test_deletes_are_retried_when_offline(alerts: SlackAlerts, api: FakeSlack, clock: FakeClock) -> None:
    alerts.post("hi")
    clock.now += 4 * HOUR
    api.offline = True
    alerts.delete_expired()
    assert len(slack.load_posts(alerts.log_path)) == 1
    assert alerts.errors.empty()  # offline sweeps stay quiet
    api.offline = False
    alerts.delete_expired()
    assert slack.load_posts(alerts.log_path) == []


def test_deletes_are_retried_when_rate_limited(alerts: SlackAlerts, api: FakeSlack, clock: FakeClock) -> None:
    alerts.post("hi")
    clock.now += 4 * HOUR
    api.fail_with = "ratelimited"
    alerts.delete_expired()
    assert len(slack.load_posts(alerts.log_path)) == 1


def test_already_deleted_message_is_forgotten(alerts: SlackAlerts, api: FakeSlack, clock: FakeClock) -> None:
    alerts.post("hi")
    clock.now += 4 * HOUR
    api.fail_with = "message_not_found"
    alerts.delete_expired()
    assert slack.load_posts(alerts.log_path) == []
    assert alerts.errors.empty()


def test_undeletable_message_is_forgotten_and_reported(alerts: SlackAlerts, api: FakeSlack, clock: FakeClock) -> None:
    alerts.post("hi")
    clock.now += 4 * HOUR
    api.fail_with = "cant_delete_message"
    alerts.delete_expired()
    assert slack.load_posts(alerts.log_path) == []
    assert alerts.errors.get_nowait() == "Slack: couldn't delete an alert (cant_delete_message)"


def test_failed_post_is_reported_and_not_logged(alerts: SlackAlerts, api: FakeSlack) -> None:
    api.fail_with = "not_in_channel"
    alerts.post("hi")
    assert alerts.errors.get_nowait() == "Slack: not_in_channel"
    assert slack.load_posts(alerts.log_path) == []


def test_offline_post_is_reported(alerts: SlackAlerts, api: FakeSlack) -> None:
    api.offline = True
    alerts.post("hi")
    assert alerts.errors.get_nowait() == "Slack: can't reach slack.com"


def test_format_alert_bolds_title_and_mentions_user() -> None:
    message = ToastMessage("Break time · 17 min", "Focus session 1 done.")
    assert slack.format_alert(message) == "*Break time · 17 min*\nFocus session 1 done."
    assert slack.format_alert(message, "U42").startswith("<@U42> *Break time")


def write_config(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_config_reads_all_fields(tmp_path: Path) -> None:
    path = write_config(
        tmp_path / "slack.json",
        {"token": " xoxb-1 ", "channel": "C1", "mention_user_id": "U1", "delete_after_hours": 6},
    )
    assert slack.load_config(path) == SlackConfig("xoxb-1", "C1", "U1", 6.0)


def test_load_config_defaults(tmp_path: Path) -> None:
    path = write_config(tmp_path / "slack.json", {"token": "xoxb-1", "channel": "C1", "mention_user_id": ""})
    assert slack.load_config(path) == SlackConfig("xoxb-1", "C1", None, slack.DEFAULT_DELETE_AFTER_HOURS)


@pytest.mark.parametrize(
    "data",
    [
        {"token": "xoxb-1"},
        {"token": "", "channel": "C1"},
        ["not", "an", "object"],
        {"token": "x", "channel": "C1", "delete_after_hours": "soon"},
    ],
)
def test_incomplete_or_bad_config_is_ignored(tmp_path: Path, data: object) -> None:
    assert slack.load_config(write_config(tmp_path / "slack.json", data)) is None


def test_config_saved_with_bom_is_read(tmp_path: Path) -> None:
    path = tmp_path / "slack.json"
    path.write_text(json.dumps({"token": "xoxb-1", "channel": "C1"}), encoding="utf-8-sig")
    assert slack.load_config(path) == SlackConfig("xoxb-1", "C1")


def test_missing_config_means_not_set_up(tmp_path: Path) -> None:
    assert slack.load_config(tmp_path / "slack.json") is None
    assert slack.connect(tmp_path / "slack.json", tmp_path / "posts.json") is None


def test_corrupt_post_log_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "posts.json"
    path.write_text("{oops", encoding="utf-8")
    assert slack.load_posts(path) == []
