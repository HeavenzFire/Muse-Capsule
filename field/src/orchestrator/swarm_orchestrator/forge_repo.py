"""forge_repo_worker: git-forge operations for GitHub and Gitea.

PRIME-style worker: CAPABILITIES + run(task, signal) -> dict.
Registered with the kernel as "forge_repo" by the orchestrator's
PrimeAdapter; capabilities are routed by swarm_orchestrator/registry.py.

Capabilities:
  forge.repo.status  {dir} -> branch, clean?, remotes, ahead/behind
  forge.repo.sync    {dir, direction="both"|"push"|"pull", remote="origin",
                      mirror_to=["github"], force=false}
                     push goes to `remote` first, then each mirror.
  forge.repo.check   {forge="github"|"gitea"} -> backend + credential health
  forge.issue.create {forge, repo="owner/name", title, body=""}
  forge.issue.list   {forge, repo="owner/name", state="open", limit=30}

Doctrine: Gitea is the source of truth (origin), GitHub is the mirror.

Backends:
  github: `gh` CLI when present (it owns its own auth), else the GitHub
          REST API via urllib.
  gitea:  Gitea REST API via urllib. The base URL is NEVER defaulted —
          it must come from args, env GITEA_URL, or Credential Manager.

Sync/push/pull always use the git CLI with a per-invocation Authorization
header (`git -c http.extraHeader=...`). Tokens never touch .git/config,
never appear in remote URLs, and are never written to disk by this worker.
(Brief command-line exposure of the token to local process listings is
inherent to this approach and documented in the pack README.)

Credentials — NEVER baked in. Resolution order:
  1. task args (transient only): github_token / gitea_token / gitea_url
  2. env: GITHUB_TOKEN / GITEA_TOKEN / GITEA_URL
  3. Windows Credential Manager (credstore): heavenzfire/github,
     heavenzfire/gitea, heavenzfire/gitea-url
Missing credentials -> {"ok": False, "credential_missing": True, ...}
naming EXACTLY what is missing and how to provide it. Never cryptic.

Destructive ops: force push requires a recorded PRIME approval — the same
approvals file the orchestrator's gate union reads (args approvals_path >
env SWARM_APPROVALS > kernel default). Fail closed: no approvals file,
no force push. There is deliberately NO repo-delete capability.
"""
import json
import os
import shutil
import subprocess
import urllib.request
import urllib.error

try:
    from .canonical import make_task_id
    from . import credstore
except ImportError:  # worker dropped standalone next to the package
    from canonical import make_task_id  # noqa: F401
    credstore = None

CAPABILITIES = [
    "forge.repo.sync",
    "forge.repo.status",
    "forge.repo.check",
    "forge.issue.create",
    "forge.issue.list",
]


# ---------------------------------------------------------------- errors
class _CredMissing(Exception):
    """Raised when a credential is missing. Carries a plain-language fix."""


class _ForgeError(Exception):
    pass


# ------------------------------------------------------------ credentials
def _approvals_path(args):
    return (args.get("approvals_path")
            or os.environ.get("SWARM_APPROVALS"))


def _destructive_approved(task):
    """True iff a recorded PRIME approval exists for this exact task.

    Same trust root the gate union enforces (the approvals file).
    Fail closed: unreadable/missing file -> False.
    """
    path = _approvals_path(task.get("args", {}))
    if not path:
        try:
            import kernel as _k
            tid = task.get("approval_id") or make_task_id(task)
            return bool(_k.is_approved(tid))
        except Exception:
            return False
    try:
        tid = task.get("approval_id") or make_task_id(task)
        with open(path, "r", encoding="utf-8") as f:
            return tid in set(json.load(f))
    except Exception:
        return False


def _creds(args, forge):
    """Resolve credentials. Returns dict or raises _CredMissing."""
    if forge == "github":
        token = (args.get("github_token") or os.environ.get("GITHUB_TOKEN"))
        if not token and credstore:
            c = credstore.read_credential(credstore.TARGET_GITHUB)
            if c:
                token = c["secret"]
        if not token:
            raise _CredMissing(
                "GitHub token missing. Provide it as task arg 'github_token', "
                "env GITHUB_TOKEN, or store it with: "
                "cmdkey /generic:heavenzfire/github /user:<you> /pass:<token>")
        return {"token": token, "scheme": "Bearer"}
    if forge == "gitea":
        url = (args.get("gitea_url") or os.environ.get("GITEA_URL"))
        token = (args.get("gitea_token") or os.environ.get("GITEA_TOKEN"))
        if credstore and (not url or not token):
            c = credstore.read_credential(credstore.TARGET_GITEA_URL)
            if c and not url:
                url = c["secret"]
            c = credstore.read_credential(credstore.TARGET_GITEA)
            if c and not token:
                token = c["secret"]
        if not url:
            raise _CredMissing(
                "Gitea URL missing. Provide it as task arg 'gitea_url', env "
                "GITEA_URL, or store it with: "
                "cmdkey /generic:heavenzfire/gitea-url /user:url /pass:<url>")
        if not token:
            raise _CredMissing(
                "Gitea token missing. Provide it as task arg 'gitea_token', "
                "env GITEA_TOKEN, or store it with: "
                "cmdkey /generic:heavenzfire/gitea /user:<you> /pass:<token>")
        return {"token": token, "scheme": "token",
                "url": url.rstrip("/")}
    raise _ForgeError("unknown forge: %r (use 'github' or 'gitea')" % forge)


# ------------------------------------------------------------------ git
def _git(args_list, cwd, token=None, scheme="Bearer", timeout=120):
    """Run git. Token (if any) travels as a per-invocation header only."""
    cmd = ["git"]
    if token:
        cmd += ["-c", "http.extraHeader=Authorization: %s %s"
                % (scheme, token)]
    cmd += args_list
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
    except FileNotFoundError:
        raise _ForgeError("git not found on PATH")
    except subprocess.TimeoutExpired:
        raise _ForgeError("git timed out: %s" % " ".join(args_list))
    return r


def _repo_dir(args):
    d = args.get("dir", "")
    ap = os.path.abspath(d)
    if not os.path.isdir(os.path.join(ap, ".git")):
        raise _ForgeError("not a git repo: %s" % ap)
    return ap


def op_status(args):
    d = _repo_dir(args)
    branch = _git(["branch", "--show-current"], d)
    porcelain = _git(["status", "--porcelain"], d)
    remotes = _git(["remote", "-v"], d)
    ahead_behind = ""
    up = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
              d)
    if up.returncode == 0:
        lr = _git(["rev-list", "--left-right", "--count",
                   "@{u}...HEAD"], d)
        if lr.returncode == 0:
            parts = lr.stdout.strip().split()
            if len(parts) == 2:
                ahead_behind = "behind=%s ahead=%s" % (parts[0], parts[1])
    return {"ok": True, "dir": d,
            "branch": branch.stdout.strip(),
            "clean": porcelain.stdout.strip() == "",
            "changed_files": len(porcelain.stdout.strip().splitlines())
            if porcelain.stdout.strip() else 0,
            "remotes": remotes.stdout.strip(),
            "ahead_behind": ahead_behind}


def op_sync(args, task):
    d = _repo_dir(args)
    forge = args.get("forge", "github")
    direction = args.get("direction", "both")
    remote = args.get("remote", "origin")
    mirrors = list(args.get("mirror_to") or [])
    force = bool(args.get("force", False))

    if force and not _destructive_approved(task):
        return {"ok": False, "error": "force push needs a recorded PRIME "
                "approval first (POST /approve on the orchestrator, or the "
                "kernel's approval path)", "approval_required": True,
                "dir": d}

    branch_r = _git(["branch", "--show-current"], d)
    branch = branch_r.stdout.strip()
    if not branch:
        raise _ForgeError("detached HEAD or no branch in %s" % d)

    creds = _creds(args, forge) if direction in ("push", "both") else None
    results = {}
    if direction in ("pull", "both"):
        # Pulls are read-only; no token needed for public repos, and for
        # private ones the remote's own credential flow applies.
        r = _git(["pull", "--ff-only", remote, branch], d,
                 token=creds["token"] if creds else None,
                 scheme=creds["scheme"] if creds else "Bearer")
        results["pull"] = {"ok": r.returncode == 0,
                           "tail": (r.stdout + r.stderr)[-800:]}
    if direction in ("push", "both"):
        push_args = ["push", remote, branch]
        if force:
            push_args = ["push", "--force-with-lease", remote, branch]
        r = _git(push_args, d, token=creds["token"],
                 scheme=creds["scheme"])
        results["push"] = {"ok": r.returncode == 0,
                           "forced": force,
                           "tail": (r.stdout + r.stderr)[-800:]}
        for m in mirrors:
            r = _git(["push", m, branch], d, token=creds["token"],
                     scheme=creds["scheme"])
            results["mirror_" + m] = {
                "ok": r.returncode == 0,
                "tail": (r.stdout + r.stderr)[-800:]}
    ok = all(v["ok"] for v in results.values())
    return {"ok": ok, "dir": d, "branch": branch, "results": results}


def op_check(args):
    forge = args.get("forge", "github")
    out = {"ok": True, "forge": forge,
           "git": shutil.which("git") is not None,
           "gh_cli": shutil.which("gh") is not None}
    if forge == "github":
        try:
            _creds(args, "github")
            out["github_token"] = "present"
        except _CredMissing as e:
            out["ok"] = False
            out["credential_missing"] = True
            out["github_token"] = "MISSING"
            out["fix"] = str(e)
    elif forge == "gitea":
        try:
            c = _creds(args, "gitea")
            out["gitea_url"] = c["url"]
            out["gitea_token"] = "present"
        except _CredMissing as e:
            out["ok"] = False
            out["credential_missing"] = True
            out["fix"] = str(e)
    else:
        out["ok"] = False
        out["error"] = "unknown forge: %r" % forge
    return out


# ------------------------------------------------------------------ api
def _api(method, url, token, scheme, payload=None, timeout=30):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "%s %s" % (scheme, token))
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            return r.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = ""
        raise _ForgeError("API %s %s -> %s %s" % (method, url, e.code,
                                                 detail))
    except urllib.error.URLError as e:
        raise _ForgeError("API unreachable: %s" % e)


def _split_repo(repo):
    if "/" not in repo:
        raise _ForgeError("repo must be 'owner/name', got %r" % repo)
    return repo.split("/", 1)


def op_issue_create(args):
    forge = args.get("forge", "github")
    repo = args.get("repo", "")
    title = args.get("title", "")
    body = args.get("body", "")
    if not repo or not title:
        raise _ForgeError("issue.create needs 'repo' (owner/name) and 'title'")
    owner, name = _split_repo(repo)

    if forge == "github" and shutil.which("gh"):
        cmd = ["gh", "issue", "create", "--repo", repo,
               "--title", title, "--body", body]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise _ForgeError("gh issue create failed: %s"
                              % r.stderr[-500:])
        return {"ok": True, "forge": "github", "via": "gh",
                "url": r.stdout.strip()}
    creds = _creds(args, forge)
    if forge == "github":
        st, resp = _api("POST",
                        "https://api.github.com/repos/%s/%s/issues"
                        % (owner, name),
                        creds["token"], creds["scheme"],
                        {"title": title, "body": body})
    else:
        st, resp = _api("POST",
                        "%s/api/v1/repos/%s/%s/issues"
                        % (creds["url"], owner, name),
                        creds["token"], creds["scheme"],
                        {"title": title, "body": body})
    return {"ok": st in (200, 201), "forge": forge, "via": "api",
            "number": resp.get("number"),
            "url": resp.get("html_url") or resp.get("url")}


def op_issue_list(args):
    forge = args.get("forge", "github")
    repo = args.get("repo", "")
    state = args.get("state", "open")
    limit = int(args.get("limit", 30))
    if not repo:
        raise _ForgeError("issue.list needs 'repo' (owner/name)")
    owner, name = _split_repo(repo)

    if forge == "github" and shutil.which("gh"):
        cmd = ["gh", "issue", "list", "--repo", repo, "--state", state,
               "--limit", str(limit),
               "--json", "number,title,state,url"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise _ForgeError("gh issue list failed: %s" % r.stderr[-500:])
        try:
            items = json.loads(r.stdout or "[]")
        except ValueError:
            items = []
        return {"ok": True, "forge": "github", "via": "gh",
                "issues": items}
    creds = _creds(args, forge)
    if forge == "github":
        st, resp = _api(
            "GET",
            "https://api.github.com/repos/%s/%s/issues?state=%s&per_page=%d"
            % (owner, name, state, limit),
            creds["token"], creds["scheme"])
    else:
        st, resp = _api(
            "GET",
            "%s/api/v1/repos/%s/%s/issues?state=%s&limit=%d"
            % (creds["url"], owner, name, state, limit),
            creds["token"], creds["scheme"])
    items = [{"number": i.get("number"), "title": i.get("title"),
              "state": i.get("state"),
              "url": i.get("html_url") or i.get("url")}
             for i in (resp if isinstance(resp, list) else [])]
    return {"ok": True, "forge": forge, "via": "api", "issues": items}


# ------------------------------------------------------------------ run
def run(task, signal):
    """PRIME worker entry: run(task, signal) -> dict."""
    args = task.get("args", {})
    op = task.get("capability", "")
    try:
        if op == "forge.repo.status":
            return op_status(args)
        if op == "forge.repo.sync":
            return op_sync(args, task)
        if op == "forge.repo.check":
            return op_check(args)
        if op == "forge.issue.create":
            return op_issue_create(args)
        if op == "forge.issue.list":
            return op_issue_list(args)
        return {"ok": False, "error": "unknown op: %s" % op}
    except _CredMissing as e:
        return {"ok": False, "credential_missing": True, "error": str(e)}
    except _ForgeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - never leak a traceback shape
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
