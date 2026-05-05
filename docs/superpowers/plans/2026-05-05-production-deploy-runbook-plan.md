# Production Deploy Runbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable docs page that records the May 2026 production deploy incident, the final known-good deployment configuration, and the exact recovery commands for future outages.

**Architecture:** The documentation lives as a single standalone markdown page in `docs/` so production operations knowledge is visible in the repository and does not depend on chat history or repo memory. The page combines a short postmortem with an operator-focused runbook and only includes information verified during the incident.

**Tech Stack:** Markdown, repository docs, GitHub Actions deployment workflow context

---

### Task 1: Write Production Deploy Runbook

**Files:**
- Create: `docs/ProductionDeployRunbook.md`
- Reference: `/memories/repo/production_deploy_debugging_2026-05-05.md`

- [ ] **Step 1: Draft the runbook structure**

Create sections for environment facts, incident summary, root causes, known-good configuration, recovery steps, and verification commands.

- [ ] **Step 2: Fill in only verified operational details**

Include the confirmed host, SSH user, service name, working RSA PEM key strategy, sudoers rule, and GitHub Actions secret expectations. Exclude speculative content.

- [ ] **Step 3: Add exact recovery commands**

Document the `sudoers.d` setup commands, `gh` run inspection commands, and SSH-based service verification commands used during the incident.

- [ ] **Step 4: Self-review for clarity and scope**

Ensure the page is useful both as a narrative postmortem and as a future operator runbook. Remove duplicated or chat-specific wording.

### Task 2: Validate Documentation Change

**Files:**
- Verify: `docs/ProductionDeployRunbook.md`

- [ ] **Step 1: Run a focused validation check**

Use workspace diagnostics and a `git diff` on the touched markdown to confirm the file was created as intended.

- [ ] **Step 2: Confirm the doc is discoverable and self-contained**

Verify the page title and section names clearly indicate it covers production deployment debugging and recovery.