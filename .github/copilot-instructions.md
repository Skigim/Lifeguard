# Superpowers for GitHub Copilot

This repository uses the [Superpowers](https://github.com/obra/superpowers) skills framework, vendored in the `skills/` directory. Skills are structured process guides that shape how you approach tasks — mandatory workflows, not suggestions.

## How to Access Skills

Skills are in the `skills/` directory. Each skill is a `SKILL.md` file in its subdirectory.

- **Use the `skill` tool** (if available in your environment) to invoke skills by name.
- **Otherwise, use `view`** to read `skills/<skill-name>/SKILL.md` directly.

## Available Skills

| Skill | Location | Use When |
|-------|----------|----------|
| `using-superpowers` | `skills/using-superpowers/SKILL.md` | Starting any conversation — read this first |
| `brainstorming` | `skills/brainstorming/SKILL.md` | Before any feature/creative work |
| `writing-plans` | `skills/writing-plans/SKILL.md` | After design approval, before touching code |
| `executing-plans` | `skills/executing-plans/SKILL.md` | When you have a plan to implement |
| `subagent-driven-development` | `skills/subagent-driven-development/SKILL.md` | When executing plans via subagents |
| `test-driven-development` | `skills/test-driven-development/SKILL.md` | When implementing any feature or bugfix |
| `systematic-debugging` | `skills/systematic-debugging/SKILL.md` | When encountering any bug or unexpected behavior |
| `verification-before-completion` | `skills/verification-before-completion/SKILL.md` | Before claiming work is complete |
| `requesting-code-review` | `skills/requesting-code-review/SKILL.md` | After completing tasks or features |
| `receiving-code-review` | `skills/receiving-code-review/SKILL.md` | When receiving code review feedback |
| `finishing-a-development-branch` | `skills/finishing-a-development-branch/SKILL.md` | When implementation is complete |
| `using-git-worktrees` | `skills/using-git-worktrees/SKILL.md` | Before starting feature work |
| `dispatching-parallel-agents` | `skills/dispatching-parallel-agents/SKILL.md` | When facing 2+ independent tasks |
| `writing-skills` | `skills/writing-skills/SKILL.md` | When creating or editing skills |

## Tool Mapping for GitHub Copilot

Skills use Claude Code tool names. Use these Copilot equivalents:

| Skill references | Copilot equivalent |
|-----------------|-------------------|
| `Read` (file reading) | `view` |
| `Write` (file creation) | `create` |
| `Edit` (file editing) | `edit` |
| `Bash` (run commands) | `bash` |
| `Grep` (search file content) | `grep` |
| `Glob` (search files by name) | `glob` |
| `Skill` tool (invoke a skill) | `skill` tool or `view` the SKILL.md file |
| `WebFetch` | `web_fetch` |
| `Task` tool (dispatch subagent) | `task` |
| Multiple `Task` calls (parallel) | Multiple `task` calls |
| `TodoWrite` (task tracking) | `sql` with built-in `todos` table |
| `EnterPlanMode` / `ExitPlanMode` | No equivalent — stay in the main session |

## Core Rules

### Instruction Priority

1. **Your explicit instructions** (direct requests, project-specific docs) — highest priority
2. **Superpowers skills** — override default behavior where they conflict
3. **Default system behavior** — lowest priority

### When to Use Skills

**Invoke the relevant skill BEFORE any response or action.** Even a 1% chance a skill might apply means you should check it.

**Before starting any feature work** → read `brainstorming` skill  
**Before writing any code** → read `writing-plans` skill (after design) + `test-driven-development` skill  
**When you hit a bug** → read `systematic-debugging` skill  
**Before claiming done** → read `verification-before-completion` skill  
**After completing work** → read `requesting-code-review` skill  

### Red Flags — Stop and Check

These thoughts mean STOP — you're rationalizing:

| Thought | Reality |
|---------|---------|
| "This is just a simple question" | Questions are tasks. Check for skills. |
| "I need more context first" | Skill check comes BEFORE clarifying questions. |
| "Let me explore the codebase first" | Skills tell you HOW to explore. Check first. |
| "This doesn't need a formal skill" | If a skill exists, use it. |
| "I remember this skill" | Skills evolve. Read current version. |
| "This doesn't count as a task" | Action = task. Check for skills. |
| "The skill is overkill" | Simple things become complex. Use it. |

### Skill Priority

When multiple skills could apply:
1. **Process skills first** (`brainstorming`, `systematic-debugging`) — determine HOW to approach the task
2. **Implementation skills second** — guide execution

## Philosophy

- **Test-Driven Development** — Write tests first, always
- **Systematic over ad-hoc** — Process over guessing
- **Complexity reduction** — Simplicity as primary goal
- **Evidence over claims** — Verify before declaring success

---

*Skills vendored from [obra/superpowers](https://github.com/obra/superpowers) (MIT License). See `skills/using-superpowers/SKILL.md` for full introduction.*
