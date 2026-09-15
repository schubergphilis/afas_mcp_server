# Maintain the repository with an agent

How the automated maintenance is wired, which repository settings it needs, and how to steer or stop it.

## The moving parts

| Piece | Where | What it does |
| --- | --- | --- |
| Maintainer manual | `AGENTS.md` (imported by `CLAUDE.md`) | The rules and checklist the agent follows. Editing it changes the agent's behaviour. |
| Dependabot | `.github/dependabot.yml` | Proposes dependency updates every Monday after a seven-day release cooldown. |
| Auto-merge | `.github/workflows/dependabot-auto-merge.yaml` | Approves and auto-merges GitHub Actions and non-major tooling updates once CI passes; labels the rest `agent-review`. |
| Interactive agent | `.github/workflows/claude.yaml` | Answers `@claude` from people with write access in issues and pull requests. |
| Maintenance agent | `.github/workflows/claude-maintenance.yaml` | Weekly checklist run, and a review of each `agent-review` PR after its CI finishes. |
| CI | `.github/workflows/continuous-integration.yaml` | Lint, Test (tox matrix), Security audit, Build. These are the checks `main` requires. |
| Security audit | `.github/workflows/security-audit.yaml` | Daily `pip-audit` against `.security-overrides`. |

## Before you start

- Admin access to the repository.
- A Claude API key from the [Claude Console](https://platform.claude.com), or a subscription token from `claude setup-token`.
- The [GitHub CLI](https://cli.github.com) logged in as an admin.

## Repository settings

The workflows assume the following. Run the commands from a clone with `OWNER=schubergphilis REPO=afas_mcp_server`.

1. **Install the Claude GitHub App** on the repository: <https://github.com/apps/claude>. It authenticates the agent's commits and comments.

2. **Add the authentication secret** the workflows read:

   ```bash
   gh secret set ANTHROPIC_API_KEY --repo $OWNER/$REPO
   ```

   Use `CLAUDE_CODE_OAUTH_TOKEN` instead, and change the `anthropic_api_key` lines in both Claude workflows, when authenticating with a subscription.

3. **Let workflows approve pull requests**, which the auto-merge workflow needs:

   ```bash
   gh api -X PUT repos/$OWNER/$REPO/actions/permissions/workflow \
     -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
   ```

4. **Enable auto-merge and branch cleanup**:

   ```bash
   gh repo edit $OWNER/$REPO --enable-auto-merge --delete-branch-on-merge
   ```

5. **Protect `main`** so that auto-merge waits for CI. Require the four CI checks, one approving review, linear history, and no force pushes. Without required checks `gh pr merge --auto` merges immediately.

6. **Create the labels** the workflows use: `agent-review`, `needs-info`, `afas-behaviour` (plus the default `bug`, `enhancement`, `question`, `dependencies`).

7. **Enable Dependabot security updates and private vulnerability reporting**:

   ```bash
   gh api -X PUT repos/$OWNER/$REPO/automated-security-fixes
   gh api -X PUT repos/$OWNER/$REPO/private-vulnerability-reporting
   ```

8. **Publishing** (optional until the first release): create the `pypi` environment with a required reviewer, and register the repository as a trusted publisher on PyPI. See [Harden the GitHub repository](https://schubergphilis.github.io/paleofuturistic_python/using/how-to/harden-github-repository.html) in the template docs.

## Steering the agent

- **Change the rules**: edit `AGENTS.md` in a pull request. It is the agent's prompt; keep it short.
- **Ask for something**: comment `@claude ...` on an issue or PR. Only people with write access can trigger it; issue text from others is treated as untrusted input.
- **Run maintenance now**: `gh workflow run claude-maintenance.yaml`.
- **Read what it did**: the weekly summary lands on the issue titled *Maintenance log*; details are in the workflow run logs.
- **Pause it**: `gh workflow disable claude-maintenance.yaml` (and `claude.yaml`). Dependabot and the auto-merge workflow keep running; disable those in their files if needed.
- **Cap the cost**: `--max-turns` in `claude_args` and `timeout-minutes` on the jobs bound each run; the Claude Console shows spend per key.

## What stays with humans

Merging behaviour changes, releasing and publishing, approving the `pypi` deployment, verifying anything against a real AFAS environment, changing the license or adding a dependency with a non-permissive license, handling security disclosures, and rotating the API key.

## See also

- [`AGENTS.md`](https://github.com/schubergphilis/afas_mcp_server/blob/main/AGENTS.md): the manual itself.
- [Dependency groups](../reference/dependency-groups.md): why the fixed `exclude-newer` date is gone and what replaced it.
- [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions): the action the workflows use.
