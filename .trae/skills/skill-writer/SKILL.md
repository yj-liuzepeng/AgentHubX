---
name: skill-writer
description: Create reusable, tool-agnostic Agent Skills with clear scope, triggers, and safe tool usage. Use when designing or refining any Skill regardless of project domain.
---

# Skill Writer

This Skill helps you design clear, reusable, and tool-agnostic Agent Skills for any project domain.

## When to use this Skill

Use this Skill when:
- Creating a new Skill from scratch
- Converting a specialized Skill into a general Skill
- Reviewing a Skill for clarity, scope, and activation triggers
- Standardizing Skill structure and frontmatter fields

## Core Principles

- Single purpose: one Skill solves one type of problem
- Explicit triggers: make activation conditions easy to detect
- Safe tool usage: prefer least-privilege tool access
- Reusability: avoid project-specific hardcoding unless required

## Instructions

### Step 1: Define scope and triggers

1. Define the user intent this Skill should cover
2. List the exact phrases or scenarios that should trigger it
3. List exclusions that should not trigger it

### Step 2: Choose Skill location

- Project Skill: `.trae/skills/<skill-name>/SKILL.md`
- Personal Skill: `~/.trae/skills/<skill-name>/SKILL.md`

### Step 3: Create a minimal structure

```
<skill-name>/
├── SKILL.md
└── reference.md (optional)
```

### Step 4: Write SKILL.md frontmatter

```yaml
---
name: skill-name
description: Clear, tool-agnostic description of capability and triggers
allowed-tools: Read, Grep, Glob
---
```

### Step 5: Write the Skill content

Use consistent sections:

```markdown
# Skill Name

## Quick Start
## Instructions
## Examples
## Constraints
## Validation Checklist
```

### Step 6: Add examples and edge cases

- At least one positive activation example
- At least one negative example
- One edge case where the Skill should refuse or ask for clarification

### Step 7: Validate the Skill

- Frontmatter name matches directory
- Description is specific and tool-agnostic
- Steps are actionable and ordered
- Examples are realistic and concise

## Example Skill

```markdown
---
name: issue-triage
description: Triage a bug report into reproduction steps, root cause hypotheses, and next actions. Use when user says “bug”, “error”, or “issue”.
allowed-tools: Read, Grep, Glob
---

# Issue Triage

## Quick Start
1. Extract error message and stack trace
2. Identify suspected modules
3. Propose next diagnostic steps

## Examples
- “App crashes on login with 500 error”
- “Payment flow throws NullPointerException”

## Constraints
- Do not modify production data
```

## Validation Checklist

- [ ] Frontmatter is valid YAML
- [ ] Trigger phrases are explicit
- [ ] Tool access is minimal
- [ ] Examples include positive and negative cases
