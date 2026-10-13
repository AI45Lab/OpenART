# Security Policy

## Supported versions

We provide security fixes for the latest release on the `main` branch.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report vulnerabilities privately via
[GitHub security advisories](https://github.com/AI45Lab/OpenART/security/advisories/new)
("Report a vulnerability" under the Security tab). Include:

- A description of the issue and its potential impact
- Steps to reproduce, including any configs or commands involved
- Affected versions or commits

We aim to acknowledge reports within 7 days. Please avoid public disclosure
until we have had a chance to investigate and publish a fix.

## Scope notes

OpenART is a safety benchmark that includes attacker flows. These flows are
intended **only** for evaluating consenting targets inside this repository's
Docker sandbox. Reports of these flows being pointed at external systems,
third-party services, or non-consenting targets are treated as abuse and are
in scope for reporting.

Leaked credentials (e.g., API keys committed to the repository or visible in
shared artifacts) should also be reported privately so maintainers can rotate
them and scrub history.

## Secret handling

- `.env`, `OpenART/outputs/`, and task workspaces may contain credentials and
  are ignored by Git on purpose. Never commit, print, or copy them.
- If you accidentally push a secret, rotate it immediately and contact the
  maintainers privately — removing it from the tip of a branch is not enough,
  as it remains in Git history.
