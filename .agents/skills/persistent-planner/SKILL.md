---
name: persistent-planner
description: Manages project state, updates the implementation plan, and tracks progress. Use this to maintain context across sessions.
---

# Skill: Persistent Planner

**Instructions for Agent:**
When invoked, you are acting as the Project Manager. Your sole responsibility is to ensure the project state is securely tracked in Markdown files on the disk so that context is never lost across sessions.
1. Check for the existence of `TASK_PLAN.md` and `PROGRESS.md` in the root directory. If they do not exist, create them.
2. Update `PROGRESS.md` with a detailed, timestamped log of the exact files changed, dependencies installed, and bugs fixed during the current interaction.
3. Update `TASK_PLAN.md` by checking off completed items and outlining the immediate next steps required for the current phase.
4. Always read both of these files silently before executing complex code generation to re-orient yourself to the project's current state.