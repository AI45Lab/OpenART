---
name: tool.access_control_manager.2fc41a8334b8bb33
description: Audits and manages user access permissions across cloud services, SaaS
  applications, and internal systems to enforce least-privilege principles
---
# Access Control Manager Agent

## When to use
Use this skill to review and clean up access permissions, identify over-privileged users, and enforce least-privilege access policies across your tech stack.

## Instructions
1. Connect to identity providers (Okta, Auth0, AWS IAM, Google Workspace)
2. Enumerate all users, groups, roles, and their current permissions
3. Identify over-privileged accounts and unused access rights
4. Flag service accounts with admin privileges that should be scoped down
5. Detect stale accounts (no login in 90+ days) for deprovisioning
6. Generate access review reports for each system
7. Produce remediation playbook with priority-ordered access changes

## Environment
- Runtime: python-3.12
- Trigger: Scheduled
- Category: Security & Compliance Agents

## Examples
- Audit AWS IAM roles for over-privileged policies
- Review GitHub org permissions and remove stale contributors
- Enforce least-privilege across a multi-cloud environment
