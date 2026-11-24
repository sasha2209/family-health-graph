"""Running a pilot: background jobs, encrypted backups and restore, readiness, error scrubbing, push links."""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import backup, monitoring
from fhg.api import Settings, create_app
from fhg.push import Notifier, PushMessage
from fhg.scheduler import IST, Job, Scheduler, is_due

ADMIN = {"X-Admin-Key": "admin-secret"}


def at(day, hour, minute=0):
    return datetime(2026, 12, day, hour, minute, tzinfo=IST)


def test_due_times():
    hourly, daily = Job("care", dict, hourly=True), Job("reminders", dict, at=(10, 0))
    assert is_due(hourly, at(1, 9, 5), at(1, 8, 2).isoformat())
    assert not is_due(hourly, at(1, 9, 50), at(1, 9, 1).isoformat())
    assert not is_due(daily, at(1, 9, 59), at(1, 7).isoformat())          # not 10:00 yet
    assert is_due(daily, at(1, 10, 1), at(1, 7).isoformat())
    assert not is_due(daily, at(1, 23), at(1, 10, 1).isoformat())         # once a day
    assert is_due(daily, at(2, 10), at(1, 10, 1).isoformat())


class MemStore:
    def __init__(self):
        self.runs = {}

    def job_run(self, name):
        return self.runs.get(name)

    def record_job_run(self, name, when, status, detail):
        self.runs[name] = {"last_run_at": when, "status": status, "detail": detail}


def test_scheduler_fresh_install_restarts_and_failures():
    calls = []
    now = [at(1, 15)]

    def boom():
        raise RuntimeError("disk full")
    jobs = [Job("care", lambda: calls.append("care") or {}, hourly=True),
            Job("reminders", lambda: calls.append("reminders") or {}, at=(10, 0)),
            Job("backup", boom, at=(2, 30), first_run_now=True)]
    store = MemStore()
    sched = Scheduler(store, jobs, clock=lambda: now[0])
    # Fresh install at 3 pm: hourly job and the backup run; reminders wait for tomorrow 10:00.
    assert sched.tick() == ["care", "backup"] and calls == ["care"]
    assert store.runs["backup"]["status"] == "error" and "disk full" in store.runs["backup"]["detail"]["error"]
    assert store.runs["reminders"]["status"] == "scheduled"
    assert sched.tick() == []                                              # nothing more this hour
    now[0] = at(2, 10, 1)
    assert set(sched.tick()) == {"care", "reminders", "backup"}
    # A restarted process (new scheduler, same database) doesn't repeat today's runs.
    assert Scheduler(store, jobs, clock=lambda: at(2, 10, 30)).tick() == []


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "o.db"), encryption_key=Fernet.generate_key().decode(),
                    admin_key="admin-secret", backup_dir=str(tmp_path / "backups"), backup_keep=2, scheduler=True)


def test_backup_restore_round_trip(settings, tmp_path):
    api = TestClient(create_app(settings))
    h = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    api.post("/v1/ingest/text", headers=h, json={"text": "My mother had breast cancer at 46."})
    assert api.post("/admin/tasks/backup").status_code in (401, 403)
    first = api.post("/admin/tasks/backup", headers=ADMIN).json()
    path = tmp_path / "backups" / first["file"]
    assert path.exists() and b"breast" not in path.read_bytes()            # encrypted as a whole
    counts = backup.check(str(path), settings.encryption_key)
    assert counts["users"] == 1 and counts["profiles"] == 1
    with pytest.raises(Exception):
        backup.check(str(path), Fernet.generate_key().decode())            # wrong key can't read it

    # Restore into a fresh location and read the record back through the app.
    restored = tmp_path / "restored.db"
    backup.restore(str(path), settings.encryption_key, str(restored))
    again = TestClient(create_app(Settings(db_path=str(restored), encryption_key=settings.encryption_key)))
    family = again.get("/v1/profile", headers=h).json()["family"]
    assert family[0]["conditions"][0]["category"] == "breast_cancer"

    # Only the newest `keep` local copies stay.
    for minute in range(3):
        backup.make_backup(api.app.state.store._conn, settings.backup_dir, settings.encryption_key, keep=2,
                           now=datetime(2026, 12, 1, 2, minute, tzinfo=timezone.utc))
    assert len(list((tmp_path / "backups").iterdir())) == 2


def test_backup_with_a_platform_generated_key(tmp_path):
    """Render's generateValue isn't a Fernet key; backups must work with any key the app itself accepts."""
    key = "rnd_" + "x7Qp2LmZ9vK4tR8sW1yB6nD3cF5gH0jA"
    api = TestClient(create_app(Settings(db_path=str(tmp_path / "g.db"), encryption_key=key, admin_key="admin-secret",
                                         backup_dir=str(tmp_path / "b"))))
    api.post("/v1/users")
    out = api.post("/admin/tasks/backup", headers=ADMIN).json()
    assert backup.check(str(tmp_path / "b" / out["file"]), key)["users"] == 1


def test_backup_with_the_development_key_file(tmp_path):
    api = TestClient(create_app(Settings(db_path=str(tmp_path / "d.db"), key_file=str(tmp_path / "dev.key"),
                                         admin_key="admin-secret", backup_dir=str(tmp_path / "b"))))
    out = api.post("/admin/tasks/backup", headers=ADMIN).json()
    assert backup.check(str(tmp_path / "b" / out["file"]), (tmp_path / "dev.key").read_text().strip())


def test_backup_uploads_when_configured(settings):
    api = TestClient(create_app(settings))
    sent = {}
    out = backup.make_backup(api.app.state.store._conn, settings.backup_dir, settings.encryption_key,
                             upload=lambda name, data: sent.update({name: data}))
    assert out["uploaded"] and list(sent) == [out["file"]]


def test_readiness_and_job_status(settings):
    api = TestClient(create_app(settings))
    assert api.get("/health/ready").json() == {"status": "ok", "problems": []}
    api.app.state.store.record_job_run("care", (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(), "ok", {})
    api.app.state.store.record_job_run("backup", datetime.now(timezone.utc).isoformat(), "error", {"error": "x"})
    r = api.get("/health/ready")
    assert r.status_code == 503 and set(r.json()["problems"]) == {"care job overdue", "backup job failed"}
    names = {j["name"] for j in api.get("/admin/jobs", headers=ADMIN).json()["jobs"]}
    assert names == {"care", "backup"}                                     # the probe's own row is hidden


def test_scheduler_runs_real_jobs(settings):
    api = TestClient(create_app(settings))
    sched = api.app.state.scheduler
    ran = sched.tick()
    assert ran == ["care", "backup"]
    assert api.app.state.store.job_run("backup")["detail"]["file"].startswith("fhg-")


def test_error_reports_carry_no_personal_data():
    event = {"request": {"method": "POST", "url": "https://x/v1/ingest/text?token=abc", "data": {"text": "Mom: cancer"},
                         "headers": {"Authorization": "Bearer t"}, "cookies": {"a": "b"}},
             "user": {"id": "u1", "email": "a@b.c"}, "breadcrumbs": {"values": [{"message": "Mom: cancer"}]},
             "exception": {"values": [{"type": "KeyError", "stacktrace": {"frames": [{"function": "f", "vars": {"text": "Mom: cancer"}}]}}]}}
    out = monitoring.scrub(event)
    assert out["request"] == {"method": "POST", "url": "https://x/v1/ingest/text"}
    assert "user" not in out and "breadcrumbs" not in out
    assert out["exception"]["values"][0]["stacktrace"]["frames"] == [{"function": "f"}]
    assert "cancer" not in str(out)
    assert monitoring.init(None, "test") is False


def test_push_links_open_the_right_screen():
    class Store:
        def notify(self, *a):
            pass

        def push_tokens_for(self, uid):
            return ["ExponentPushToken[abcdefghijkl]"]

        def remove_push_tokens(self, t):
            pass

    class Sender:
        def __init__(self):
            self.msgs: list[PushMessage] = []

        def send(self, msgs):
            self.msgs += msgs
            return []
    sender = Sender()
    n = Notifier(Store(), sender, background=False)
    n.notify("u", "care", "Time for Asha's morning medicines: Telma 40.", url="/care?id=u.m1")
    n.notify("u", "privacy", "Answer to your concern")
    assert [(m.body, m.data["url"]) for m in sender.msgs] == [
        ("An update about someone you care for.", "/care?id=u.m1"),
        ("There's an answer to your privacy question.", "/privacy")]
    assert "Telma" not in str(sender.msgs)                                 # nothing medical on the lock screen
