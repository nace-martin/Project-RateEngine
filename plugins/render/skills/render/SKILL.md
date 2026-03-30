---
name: render
description: Use when working with Render services, deployments, logs, environment variables, and service configuration.
---

# Render

Use this skill when the task involves applications or infrastructure hosted on Render.

## Baseline workflow

1. Determine whether the task is read-only or changes Render configuration or deployments.
2. Prefer the Render MCP server or Render app connection once `.mcp.json` and `.app.json` have been configured.
3. Gather the affected Render service, environment, and recent deployment context before making changes.
4. For deployment failures, inspect build logs, start commands, env vars, health checks, and region or plan-specific settings.
5. For service changes, record the intended state and the rollback path before applying updates.

## Current scaffold status

- `.mcp.json` contains placeholder connection details and must be completed before this plugin can talk to Render.
- `.app.json` contains a placeholder connector id and must be updated if you want app-based integration.
- Add narrower sub-skills here as the plugin grows, for example deployment triage, service provisioning, or env management.
