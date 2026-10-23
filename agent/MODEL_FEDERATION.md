# Model federation adapters (developer preview)

The agent can select a model provider through a small adapter interface while
keeping its existing tool loop, capsule context, approval checks, and audit log.

## Supported providers in this change

- `ollama` (default): local Ollama `/api/chat` endpoint.
- `deepseek`: DeepSeek's OpenAI-compatible `/chat/completions` endpoint.
- `openai-compatible`: a configurable compatible endpoint for deployments
  whose API and request schema match the OpenAI chat-completions format.

This is provider routing, not neural-weight fusion. Models remain separate
systems; the agent can choose a provider for a task, and later work can add
explicit delegation, cross-model review, and shared task envelopes.

## Configure DeepSeek in PowerShell

Set credentials locally in the terminal or through your machine's secret
manager. Never paste API keys into chat, commit them, or put them in logs.

```powershell
$env:HF_AGENT_PROVIDER = "deepseek"
$env:HF_AGENT_MODEL = "deepseek-chat"
$env:DEEPSEEK_API_KEY = Read-Host "Enter DeepSeek API key"
python .\agent.py --provider-status
python .\agent.py "Summarize the current task and identify uncertainties"
```

The interactive `Read-Host` example keeps the key out of the command text,
but PowerShell environment variables remain available to child processes for
that terminal session. For persistent use, prefer a local secret manager or
machine-scoped secure configuration appropriate to your environment.

For a one-run provider override, use `python .\agent.py --provider deepseek
"your task"`. The model name still comes from `HF_AGENT_MODEL`; set it to a
model enabled for the account.

## Configure an OpenAI-compatible endpoint

```powershell
$env:HF_AGENT_PROVIDER = "openai-compatible"
$env:HF_AGENT_BASE_URL = "https://your-authorized-provider.example/v1"
$env:HF_AGENT_MODEL = "your-model-name"
$env:HF_OPENAI_COMPATIBLE_API_KEY = Read-Host "Enter provider API key"
python .\agent.py --provider-status
```

Only use an endpoint you trust and are authorized to access. Compatibility
varies between providers; this adapter targets `POST /chat/completions` and
the conventional `choices[0].message.content` response shape.

## External providers require a per-run opt-in

Selecting an external (non-loopback) provider sends the capsule — soul,
standing orders, and memory — plus the run's evolving tool transcript to a
third party. Configuring a provider is therefore not standing consent for
every run. Before any request is made, an external run refuses to proceed
unless you opt in for that run, in either of two equivalent ways:

```powershell
python .\agent.py --provider deepseek --allow-external-provider "your task"
# or, for the run's shell only:
$env:HF_ALLOW_EXTERNAL = "1"
```

Local/loopback providers (including Ollama and endpoints on 127.0.0.1 or
localhost) are unaffected and never require the opt-in.

Related transport rules, enforced in `providers.py`:

- Provider base URLs must be `https://`; `http://` is accepted only for
  loopback hosts. This includes DeepSeek's overridable `HF_AGENT_BASE_URL`.
- If a provider endpoint redirects a request to a different origin, the
  `Authorization` header is stripped rather than forwarded to the new host.
- Provider-side retention and training use are governed by that provider's
  terms; this code cannot control what a provider keeps.

## Status semantics

`python .\agent.py --provider-status` reports local configuration only; it
does not contact the provider or prove reachability, account entitlement,
model availability, or billing status. `AUTH_REQUIRED` means the key is not
present locally. `AUTH_CONFIGURED` means only that an endpoint and nonempty
key are configured, not that authentication has succeeded.

No live provider call is made by the tests. Tests use a mocked HTTP response;
live DeepSeek use requires a valid key and may incur provider charges.

## Current limits

- Ollama remains the default, preserving the local-first behavior.
- One selected provider handles an agent run; parallel multi-model arbitration
  and automatic cross-provider failover are not implemented here yet.
- Shared capsule context is supplied to each run, but provider-side memory is
  not synchronized automatically.
- Tool permissions and approval gates remain in the agent runtime. Do not
  treat model output as trusted instructions or widen tool permissions merely
  because another provider is enabled.
