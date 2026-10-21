"""Read generic credentials from Windows Credential Manager. Stdlib only.

Targets (written by Install-SwarmOrchestrator.ps1 via cmdkey):
  heavenzfire/github      username = GitHub username,  secret = token / PAT
  heavenzfire/gitea       username = Gitea username,   secret = token
  heavenzfire/gitea-url   username = "url",            secret = Gitea base URL

read_credential(target) -> {"username":..., "secret":...} | None.
None on non-Windows, when the target is missing, or on any API failure.
Secrets are never printed, logged, or written to disk by this module.
"""
import ctypes
import os
from ctypes import wintypes

_CRED_TYPE_GENERIC = 1


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_credential(target):
    """Return {"username", "secret"} or None. Never raises."""
    if os.name != "nt":
        return None
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        cred_read = advapi32.CredReadW
        cred_read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                              wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
        cred_read.restype = wintypes.BOOL
        cred_free = advapi32.CredFree
        cred_free.argtypes = [ctypes.c_void_p]
        cred_free.restype = None

        pcred = ctypes.POINTER(_CREDENTIALW)()
        if not cred_read(target, _CRED_TYPE_GENERIC, 0,
                         ctypes.byref(pcred)):
            return None
        try:
            c = pcred.contents
            blob = ctypes.string_at(c.CredentialBlob,
                                    c.CredentialBlobSize)
            try:
                secret = blob.decode("utf-16-le")
            except UnicodeDecodeError:
                secret = blob.decode("utf-8", errors="replace")
            # cmdkey stores UTF-16LE; strip a possible trailing NUL.
            secret = secret.rstrip("\x00")
            username = c.UserName or ""
            return {"username": username, "secret": secret}
        finally:
            cred_free(pcred)
    except Exception:
        return None


# Convenience targets used by the forge worker.
TARGET_GITHUB = "heavenzfire/github"
TARGET_GITEA = "heavenzfire/gitea"
TARGET_GITEA_URL = "heavenzfire/gitea-url"
