"""Forge-repo worker tests: mocked subprocess, credential paths, approvals.

Run: python tests/test_forge_repo.py
Stdlib only. No network, no git, no Windows needed (credstore mocked).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

from swarm_orchestrator import forge_repo
from swarm_orchestrator import registry

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (" -- " + detail if detail and not cond else ""))


def _task(cap, args):
    return {"capability": cap, "args": dict(args)}


# ---------------------------------------------------------------- registry
def test_registry():
    for cap in ["forge.repo.sync", "forge.repo.status", "forge.repo.check",
                "forge.issue.create", "forge.issue.list"]:
        sub, handler = registry.route({"capability": cap, "args": {}})
        check("registry routes %s -> prime/forge_repo" % cap,
              sub == "prime" and handler == "forge_repo")
    check("forge_repo has CAPABILITIES",
          set(forge_repo.CAPABILITIES) >= {
              "forge.repo.sync", "forge.repo.status", "forge.repo.check",
              "forge.issue.create", "forge.issue.list"})


# ---------------------------------------------------------------- check op
def test_check_reports_missing_credentials_plainly():
    env = {"PATH": os.environ.get("PATH", "")}
    with mock.patch.dict(os.environ, env, clear=True):
        with mock.patch("shutil.which", return_value=None):
            r = forge_repo.run(_task("forge.repo.check",
                                     {"forge": "github"}), None)
    check("check: github token missing -> ok False + credential flag",
          r["ok"] is False and "token" in r.get("fix", "").lower())
    check("check: fix names exact remedies",
          "GITHUB_TOKEN" in r.get("fix", "") and "cmdkey" in r.get("fix", ""))


def test_check_gitea_url_never_defaulted():
    env = {"PATH": os.environ.get("PATH", "")}
    with mock.patch.dict(os.environ, env, clear=True):
        r = forge_repo.run(_task("forge.repo.check",
                                 {"forge": "gitea",
                                  "gitea_token": "x"}), None)
    check("check: gitea without URL -> missing, no invented default",
          r["ok"] is False and "GITEA_URL" in r.get("fix", ""))


def test_check_ok_when_creds_present():
    with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "sekret",
                                       "PATH": os.environ.get("PATH", "")},
                          clear=True):
        with mock.patch("shutil.which",
                        side_effect=lambda c: "/usr/bin/" + c
                        if c in ("git",) else None):
            r = forge_repo.run(_task("forge.repo.check",
                                     {"forge": "github"}), None)
    check("check: token present -> ok True, token value never echoed",
          r["ok"] is True and r.get("github_token") == "present"
          and "sekret" not in json.dumps(r))


# ---------------------------------------------------------------- sync
def _completed(rc=0, out="", err=""):
    m = mock.Mock()
    m.returncode = rc
    m.stdout = out
    m.stderr = err
    return m


def test_sync_force_needs_approval():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".git"))
        with mock.patch("subprocess.run",
                        return_value=_completed(0, "main\n", "")):
            r = forge_repo.run(_task("forge.repo.sync",
                                     {"dir": d, "direction": "push",
                                      "force": True,
                                      "github_token": "t"}), None)
    check("sync: force push without approval -> denied + approval flag",
          r["ok"] is False and r.get("approval_required") is True)


def test_sync_force_with_approval_builds_force_with_lease():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".git"))
        ap = os.path.join(d, "approvals.json")
        from swarm_orchestrator.canonical import make_task_id
        t = _task("forge.repo.sync",
                  {"dir": d, "direction": "push", "force": True,
                   "github_token": "sekret", "approvals_path": ap})
        tid = make_task_id(t)
        with open(ap, "w") as f:
            json.dump([tid], f)
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if "branch" in cmd:
                return _completed(0, "main\n", "")
            return _completed(0, "ok\n", "")

        with mock.patch("subprocess.run", side_effect=fake_run):
            r = forge_repo.run(t, None)
    push_cmds = [c for c in calls if "push" in c]
    check("sync: approved force push uses --force-with-lease (never --force)",
          r["ok"] is True
          and any("--force-with-lease" in c for c in push_cmds)
          and not any(c == "--force" for cmd in push_cmds for c in cmd))
    check("sync: token travels as header, never in URL",
          all("sekret" not in " ".join(c[3:]) or "extraHeader" in " ".join(c)
              for c in calls)
          and not any("sekret@" in " ".join(c) for c in calls))


def test_sync_push_goes_origin_then_mirror():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".git"))
        t = _task("forge.repo.sync",
                  {"dir": d, "direction": "push", "remote": "origin",
                   "mirror_to": ["github"], "github_token": "t"})
        remotes = []

        def fake_run(cmd, **kw):
            if "branch" in cmd:
                return _completed(0, "main\n", "")
            if cmd[0] == "git" and "push" in cmd:
                # find the remote arg: after "push"
                i = cmd.index("push")
                remotes.append(cmd[i + 1])
            return _completed(0, "ok\n", "")

        with mock.patch("subprocess.run", side_effect=fake_run):
            r = forge_repo.run(t, None)
    check("sync: push order origin first, then mirror",
          r["ok"] is True and remotes == ["origin", "github"])


def test_sync_not_a_repo():
    with tempfile.TemporaryDirectory() as d:
        r = forge_repo.run(_task("forge.repo.sync",
                                 {"dir": d, "direction": "push"}), None)
    check("sync: non-repo dir -> clear error",
          r["ok"] is False and "not a git repo" in r["error"])


# ---------------------------------------------------------------- issues
def test_issue_create_via_gh_when_present():
    def fake_run(cmd, **kw):
        assert cmd[0] == "gh", "expected gh, got %r" % cmd[:2]
        return _completed(0, "https://github.com/o/n/issues/7\n", "")

    with mock.patch("shutil.which", return_value="/usr/bin/gh"):
        with mock.patch("subprocess.run", side_effect=fake_run):
            r = forge_repo.run(_task("forge.issue.create",
                                     {"forge": "github", "repo": "o/n",
                                      "title": "t", "body": "b"}), None)
    check("issue.create: uses gh when present",
          r["ok"] is True and r["via"] == "gh"
          and r["url"].endswith("/issues/7"))


def test_issue_create_gitea_api_shape():
    seen = {}

    def fake_api(method, url, token, scheme, payload=None, timeout=30):
        seen.update(method=method, url=url, scheme=scheme, payload=payload)
        assert scheme == "token", "gitea uses 'token' scheme"
        return 201, {"number": 3, "html_url": "https://g/t/o/n/issues/3"}

    with mock.patch("shutil.which", return_value=None):
        with mock.patch.object(forge_repo, "_api", side_effect=fake_api):
            r = forge_repo.run(_task("forge.issue.create",
                                     {"forge": "gitea", "repo": "o/n",
                                      "title": "t",
                                      "gitea_url": "https://gitea.lan:3000/",
                                      "gitea_token": "sek"}), None)
    check("issue.create: gitea posts to /api/v1/repos/o/n/issues",
          r["ok"] is True and r["number"] == 3
          and seen["url"] == "https://gitea.lan:3000/api/v1/repos/o/n/issues"
          and seen["payload"] == {"title": "t", "body": ""})


def test_issue_list_github_api_shape():
    seen = {}

    def fake_api(method, url, token, scheme, payload=None, timeout=30):
        seen.update(method=method, url=url, scheme=scheme)
        assert scheme == "Bearer", "github uses Bearer scheme"
        return 200, [{"number": 1, "title": "a", "state": "open",
                      "html_url": "https://github.com/o/n/issues/1"}]

    with mock.patch("shutil.which", return_value=None):
        with mock.patch.object(forge_repo, "_api", side_effect=fake_api):
            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "sek"}):
                r = forge_repo.run(_task("forge.issue.list",
                                         {"forge": "github",
                                          "repo": "o/n"}), None)
    check("issue.list: github api shape + normalized items",
          r["ok"] is True and len(r["issues"]) == 1
          and r["issues"][0]["number"] == 1
          and "per_page=30" in seen["url"])


def test_unknown_forge():
    r = forge_repo.run(_task("forge.repo.check", {"forge": "bitbucket"}),
                       None)
    check("unknown forge -> clear error, not traceback-shaped",
          r["ok"] is False and "bitbucket" in r.get("error", ""))


if __name__ == "__main__":
    test_registry()
    test_check_reports_missing_credentials_plainly()
    test_check_gitea_url_never_defaulted()
    test_check_ok_when_creds_present()
    test_sync_force_needs_approval()
    test_sync_force_with_approval_builds_force_with_lease()
    test_sync_push_goes_origin_then_mirror()
    test_sync_not_a_repo()
    test_issue_create_via_gh_when_present()
    test_issue_create_gitea_api_shape()
    test_issue_list_github_api_shape()
    test_unknown_forge()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
