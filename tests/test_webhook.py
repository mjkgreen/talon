import hashlib
import hmac
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from talon.db import Issue
from talon.routers.webhooks import _extract_labels, _verify_hmac
from talon.server import app

client = TestClient(app)


class TestVerifyHmac:
    def test_valid_signature(self):
        body = b"test payload"
        secret = "my-secret"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_hmac(secret, body, sig)

    def test_invalid_signature(self):
        assert not _verify_hmac("secret", b"body", "wrong")

    def test_empty_secret_accepts_all(self):
        assert _verify_hmac("", b"anything", "garbage")

    def test_github_prefix(self):
        body = b"payload"
        secret = "gh-secret"
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_hmac(secret, body, f"sha256={digest}", prefix="sha256=")

    def test_tampered_body_rejected(self):
        secret = "s3cret"
        body = b"original"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert not _verify_hmac(secret, b"tampered", sig)


class TestExtractLabels:
    def test_extracts_names(self):
        items = [{"name": "agent-task"}, {"name": "bug"}]
        assert _extract_labels(items) == ["agent-task", "bug"]

    def test_empty_list(self):
        assert _extract_labels([]) == []

    def test_missing_name_key(self):
        assert _extract_labels([{"id": "123"}]) == [""]


class TestHealthEndpoint:
    def test_returns_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert "timestamp" in r.json()


class TestLinearWebhook:
    def test_wrong_action_skipped(self):
        r = client.post("/webhook/linear", json={"action": "update", "type": "Issue", "data": {}})
        assert r.status_code == 200
        assert "skipped" in r.json()

    def test_wrong_type_skipped(self):
        r = client.post("/webhook/linear", json={"action": "create", "type": "Comment", "data": {}})
        assert r.status_code == 200
        assert "skipped" in r.json()

    def test_label_filter_blocks_untagged(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_LABEL", "agent-task")
        payload = {
            "action": "create",
            "type": "Issue",
            "data": {"title": "Fix bug", "labels": [{"name": "other"}]},
        }
        r = client.post("/webhook/linear", json=payload)
        assert r.status_code == 200
        assert r.json()["skipped"]

    def test_no_label_filter_accepts_all(self, monkeypatch):
        import talon.routers.webhooks as webhooks_mod

        monkeypatch.setattr(webhooks_mod, "WEBHOOK_LABEL", "")
        fake_issue = Issue(
            id=1,
            title="Do the thing",
            description="",
            status="In Progress",
            run_id=None,
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
        monkeypatch.setattr(webhooks_mod.db, "get_first_project_id", AsyncMock(return_value=1))
        monkeypatch.setattr(webhooks_mod.db, "create_issue", AsyncMock(return_value=fake_issue))
        monkeypatch.setattr(webhooks_mod, "broadcast_issue_update", AsyncMock())
        monkeypatch.setattr(webhooks_mod, "_run_loop", AsyncMock())
        payload = {
            "action": "create",
            "type": "Issue",
            "data": {"title": "Do the thing", "labels": []},
        }
        r = client.post("/webhook/linear", json=payload)
        assert r.status_code == 200
        assert r.json().get("triggered")

    def test_bad_signature_rejected(self, monkeypatch):
        monkeypatch.setenv("LINEAR_WEBHOOK_SECRET", "real-secret")
        import importlib

        import talon.routers.webhooks

        importlib.reload(talon.routers.webhooks)
        c = TestClient(app)
        r = c.post("/webhook/linear", json={}, headers={"Linear-Signature": "wrong"})
        assert r.status_code == 401
        importlib.reload(talon.routers.webhooks)


class TestGithubWebhook:
    def test_non_issue_event_skipped(self):
        r = client.post(
            "/webhook/github",
            json={"action": "opened"},
            headers={"X-GitHub-Event": "push"},
        )
        assert r.status_code == 200
        assert "skipped" in r.json()

    def test_closed_action_skipped(self):
        r = client.post(
            "/webhook/github",
            json={"action": "closed", "issue": {"title": "x", "labels": []}},
            headers={"X-GitHub-Event": "issues"},
        )
        assert r.status_code == 200
        assert "skipped" in r.json()

    def test_label_filter_blocks_untagged(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_LABEL", "agent-task")
        payload = {
            "action": "opened",
            "issue": {"title": "Feature", "body": "", "labels": []},
        }
        r = client.post("/webhook/github", json=payload, headers={"X-GitHub-Event": "issues"})
        assert r.status_code == 200
        assert r.json()["skipped"]

    def test_tagged_issue_triggers(self, monkeypatch):
        import talon.routers.webhooks as webhooks_mod

        monkeypatch.setattr(webhooks_mod, "WEBHOOK_LABEL", "agent-task")
        fake_issue = Issue(
            id=2,
            title="Do the thing",
            description="Details",
            status="In Progress",
            run_id=None,
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
        monkeypatch.setattr(webhooks_mod.db, "get_first_project_id", AsyncMock(return_value=1))
        monkeypatch.setattr(webhooks_mod.db, "create_issue", AsyncMock(return_value=fake_issue))
        monkeypatch.setattr(webhooks_mod, "broadcast_issue_update", AsyncMock())
        monkeypatch.setattr(webhooks_mod, "_run_loop", AsyncMock())
        payload = {
            "action": "opened",
            "issue": {
                "title": "Do the thing",
                "body": "Details",
                "labels": [{"name": "agent-task"}],
            },
        }
        r = client.post("/webhook/github", json=payload, headers={"X-GitHub-Event": "issues"})
        assert r.status_code == 200
        assert r.json().get("triggered")
