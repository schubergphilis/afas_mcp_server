# Security policy

## What this project handles

The server holds one AFAS app connector token for its lifetime and forwards tool calls to the
AFAS Profit REST services with it. A vulnerability in this project could therefore expose or
change ERP, HR and payroll data. We take reports seriously and answer quickly.

## Reporting a vulnerability

Please do **not** open a public issue for security problems.

Use GitHub's private vulnerability reporting: open the repository's **Security** tab and choose
**Report a vulnerability**. If that is unavailable, email evandervecht@schubergphilis.com with
"afas_mcp_server security" in the subject.

Include what you found, how to reproduce it, and the version (`afas-mcp-server --version`).
You will get an acknowledgement within three working days and a fix or a clear plan within
thirty days for confirmed issues. We will credit you in the release notes unless you prefer
otherwise.

## Scope

In scope: this repository's code, its default configuration, its documentation where it gives
unsafe advice, and its release artefacts on PyPI.

Out of scope: AFAS Profit itself (report to AFAS Software), the MCP clients that connect to the
server, and deployments that expose the streamable HTTP transport without a reverse proxy, which
the documentation already warns against.

## Supported versions

The latest release on PyPI receives fixes. Older releases are not patched; upgrade instead.

## Automated checks

Dependencies are audited daily against known vulnerabilities (`.github/workflows/security-audit.yaml`),
Dependabot alerts and security updates are enabled, and every release ships a CycloneDX SBOM
inside the wheel.
