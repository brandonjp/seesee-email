# What's Next — Determine Priority & Generate Session Prompt

You are determining the next development task for this project and generating a ready-to-paste prompt for a new Claude Code session.

**Assume all open PRs and branches have been merged** unless the human says otherwise.

---

## 1. Research Current State

Read these files to understand what's been done and what's planned:

- `NEXT.md` — Current priority and recently completed work
- `README.md` — Project overview and setup
- `ROADMAP.md` — Overall project roadmap and phase status
- `CHANGELOG.md` — Recent version history
- Any plan documents referenced in `NEXT.md`

Also check:
- `git log --oneline -15` — Recent commits to understand what just shipped

## 2. Determine the Single Highest-Priority Task

Use these inputs to decide:
- `NEXT.md` (primary source of truth)
- Plan documents referenced there
- `ROADMAP.md` for phase context
- Any incomplete or deferred items
- Your assessment of what the project needs most

The task must be **implementation work** — building, fixing, refactoring, testing. Never recommend "create a PR," "merge to main," or any git workflow step as the next task.

**Scope to a single focused PR** — don't combine unrelated work.

## 3. Model Recommendation

Assess the task and recommend which model should execute it:

**Recommend Sonnet when:**
- The task follows existing patterns in the codebase
- Requirements are clearly defined with little ambiguity
- It's primarily adding a feature with a known shape (new email action, new copy helper, etc.)
- The work is mechanical — migrations, test writing, refactoring to a known pattern
- The task scope is narrow and well-bounded

**Recommend Opus when:**
- The task requires significant architectural decisions
- Multiple valid approaches exist and the tradeoffs are non-obvious
- The task involves debugging a subtle or hard-to-reproduce issue
- New subsystems or patterns need to be designed from scratch
- The task involves complex integrations or data flows
- Requirements are ambiguous and the AI will need to make judgment calls

## 4. Generate the Session Prompt

Generate a **complete, self-contained prompt** for the next development session. This prompt must work with zero additional context — the new session has no memory of this conversation.

### Title Format (Critical)

The **very first line** must follow this exact format:

```
# [repo-name] - [Task Type]: [specific task description]
```

Rules:
- Must start with `# ` (single hash, space)
- Use the **actual repository/folder name**
- Then ` - ` (space, dash, space)
- Then a **task type** — use one of: `Feature`, `Fix`, `Refactor`, `Test`, `Docs`, `Config`, `Setup`, or another short descriptive noun if none fit
- Then `: ` (colon, space)
- Then a specific description of the work to be done

Examples:
- `# seesee-email - Feature: add copyAll button for bulk address copying`
- `# seesee-email - Fix: make admin username comparison case-insensitive`
- `# seesee-email - Refactor: extract clipboard helper into reusable utility`

Never use generic descriptions:
- `# seesee-email - Feature: continue development`
- `# seesee-email - Feature: various improvements`

### Model and Session Guidance

The **second line** must be a clear, standalone model directive — nothing else:

```
> **⮕ SONNET**
```

or

```
> **⮕ OPUS**
```

This is the only thing the human reads before copy-pasting. No extra instructions, no reasoning text on this line.

### Remaining Prompt Content

After the title and model line, the prompt must include:

1. **Today's date**

2. **Task description** — what to build, why, and how it fits into the project

3. **Concrete acceptance criteria** — specific, verifiable outcomes that define "done"

4. **Key project files to read first**, by exact path:
   - `NEXT.md` — Current priority (confirm alignment)
   - `.claude/commands/dev.md` — Development standards and workflow
   - `ROADMAP.md` — Phase context
   - `README.md` — Project overview

5. **Technical context the next session needs:**
   - Key architectural decisions already made
   - Relevant file paths and module locations
   - Patterns and conventions in use
   - Gotchas or constraints discovered in previous sessions

6. **Standard closing instructions:**
   - Read `NEXT.md` first and confirm it aligns with the task
   - Follow all project coding standards and commit conventions found in project docs
   - Work autonomously — only ask questions on genuine blockers where project docs don't provide the answer
   - Do NOT create pull requests, merge branches, or use the `gh` CLI — the human handles all of that
   - When finished, invoke `/session-close` (edit flags at the bottom before sending if needed)

### Output Format

Wrap the **entire prompt** in a code fence using **at least 6 backticks** (e.g., ``````) so inner code blocks don't break formatting. The entire prompt must be copyable in one clean selection.

Note: Do NOT include a flags section in the generated prompt. Flags are edited at the point of use — on `/session-close` and on the review prompt — not pre-set in the task prompt.
