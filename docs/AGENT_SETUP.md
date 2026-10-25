# Codex project agents

The project defines three native Codex agent roles in `.codex/config.toml` and `.codex/agents/`:

- `coder`: `gpt-6.1-sol`, medium reasoning
- `reviewer`: `gpt-6.1-sol`, high reasoning
- `researcher`: `gpt-6-luna`, high reasoning

The project default for new sessions is `gpt-6-astra` with high reasoning. This setting does not switch an already-running Codex session. The project config enables agents, limits a session to three concurrent child agents, and uses `gpt-6.1-sol` with medium reasoning as the fallback for untyped child agents. It sets `max_depth = 1` for V1 agent threads; current V2 configuration ignores that setting, so follow the project instruction to keep agents from nesting.

Each role file has `name`, `description`, `model`, `model_reasoning_effort`, and non-empty `developer_instructions`. The main config declares each role and points `config_file` at its role file. Keep role names aligned across the filename, file `name`, and `[agents.<role>]` table.

Codex discovers project roles in `.codex/agents/*.toml`. A role file may also be connected explicitly using `[agents.<role>]` with `description` and `config_file`. Model names and reasoning levels should be checked against the installed CLI's `codex debug models` output when updating this configuration.

## Practical verification

During this task, native Codex subagents completed work at the configured role settings: Explorer/researcher (`gpt-6-luna`, high) performed read-only research, Coder (`gpt-6.1-sol`, medium) created the pedagogy component, and Reviewer (`gpt-6.1-sol`, high) independently reviewed it. The root agent independently ran the unittest suite: 6 tests passed. These runs show the requested native agent/model combinations and project workflow were used; they do not prove that the installed CLI loaded role definitions from this checkout.

The installed CLI provides `codex agents` to browse agent sessions and `codex debug prompt-input` to inspect prompt input, but neither exposes a read-only list of project role definitions. The prompt-input check did not include the custom role descriptions. `codex --strict-config -C <repo> doctor` accepted the configuration without a parse error, then exited 1 because CLI credentials and provider connectivity are unavailable. Therefore CLI role-session discovery remains unconfirmed. The repository default model only applies to newly created sessions; it did not switch the already-running parent session.

## Source and verification

Checked 2026-10-25 against the official OpenAI Codex source:

- [Codex config TOML types](https://github.com/openai/codex/blob/main/codex-rs/config/src/config_toml.rs) defines `AgentsToml`, the `max_concurrent_threads_per_session` field (`max_threads` alias), `max_depth`, role declarations, and the `description` / `config_file` fields.
- [Agent role file parser](https://github.com/openai/codex/blob/main/codex-rs/agent-roles/src/agent_role_config.rs) defines top-level `name`, `description`, and `nickname_candidates`, then flattens the normal config fields. It requires a non-empty name (unless supplied by the declared role) and non-blank developer instructions for discovered role files.
- [Agent role loader](https://github.com/openai/codex/blob/main/codex-rs/agent-roles/src/loader.rs) loads declared and discovered roles from the config folder's `agents` directory.

The local CLI reports `codex-cli 0.163.0`; its model catalog was available through `codex debug models`. `codex --strict-config -C <repo> doctor` reported no config parse errors; doctor exited 1 because this environment lacks CLI credentials and cannot reach provider endpoints. The upstream source URLs were fetched successfully. The `developers.openai.com` documentation pages could not be reached from this environment because the HTTPS tunnel returned `403 Forbidden`.
