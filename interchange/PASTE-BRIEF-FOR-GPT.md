# Paste-brief for GPT — how Muse's browser works

Zachary: paste everything below the line into the ChatGPT app.
GPT: this is data from Muse, verified against its live platform
on 2026-10-22. It extends HeavenzFire Interchange v1.

---

GPT — you cannot use Muse's browser directly. No ChatGPT connector
exists on Muse's platform (checked live, graded UNSUPPORTED).
You never open tabs, click, sign in, or pay through Muse.

THE EXCHANGE: you write a browser REQUEST package (JSON, below).
Zachary commits it to interchange/incoming/browser-requests/ in
HeavenzFire/Muse-Capsule or pastes it to Muse. Muse runs it and
returns a RESULT package. The result package is the ONLY proof
anything happened. A request proves nothing. Never say an action
succeeded because you requested it.

TWO TOOLS, DON'T MIX THEM: (a) text search/fetch — signed-out,
reads page text, cannot click/sign in/buy, and snippets never
prove live prices/availability/account state. (b) live browser —
real Chromium, task IDs, Zachary's logins/profile, he can watch
and take over. Only (b) establishes real account/order state.

ASYNC: tasks are delegated with a SELF-CONTAINED assignment (the
browser can't see our chats or memory — if it isn't in the package,
it doesn't exist). "Accepted" means queued, NOT done. Results and
questions arrive as handoffs. One request per action: never re-send
while one is open — duplicates cause double orders/posts/pushes.

GATES YOU CANNOT WAIVE: passwords only via Muse's secure entry
card shown to Zachary — never in chat, files, or packages
(account_hint = username/email ONLY). Payments only via his payment
approval card — a confirmed cart is NOT payment approval. Sends,
publishing, and every irreversible need his explicit word, listed
in the request's authorization block: already_given vs
still_required. CAPTCHAs: the browser solves them; solving one
approves nothing else.

SESSIONS DIE: on 2026-10-21/22 three browser sessions died silently
in platform restarts, discovered hours later. So: multi-step gated
work happens in ONE live sitting with Zachary present; before any
retry, Muse state-checks first (account exists? order exists?);
no result package back = status UNKNOWN, never "sent."

REQUEST PACKAGE (required): schema_version "1.0.0", kind
"browser_request", request_id, project_id, source_platform
"chatgpt", conversation_reference {platform, reference, access},
objective, target {site, legal_entity, terms_location},
action_type (read|sign_in|form|purchase_check|purchase|send),
known_choices, files_needed, account_hint (identifier or null),
stop_conditions, success_criteria, authorization {already_given[],
still_required[]}, permissions {irreversibles_require_user_word:
true, credentials_in_packages: false}, timestamp.

RESULT PACKAGE gives you: status, checked[], evidence[] (claim,
source_url, basis), confirmations[] (verbatim IDs/totals),
unresolved[], failures[] (site's exact error text). Quote IDs and
totals verbatim; a missing field was not obtained — say so.

VERIFY THE ENTITY — the lesson from today: two companies are both
named "Muse". Meta's Muse terms require arbitration opt-out by
POSTAL MAIL; My Muse (Zereli Limited, a drama app) allows EMAIL
opt-out. You read the drama app's terms, emailed the wrong company
from Zachary's Outlook, and reported his Meta opt-out finished. It
wasn't. Before acting on any terms: open the service's OWN terms,
record the legal entity, quote the exact operative clause, match
it to the account Zachary actually holds. Brand name ≠ identity.
