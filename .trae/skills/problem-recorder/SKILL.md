---
name: "problem-recorder"
description: "Records problems/solutions to `problem_summaries/problems_N.md` with incremental IDs. Invoke when user says '记录这个问题' (record problem) or '再增加一个文档' (new doc)."
---

# Problem Recorder

This skill manages a repository of problem summaries, allowing users to easily record issues and solutions during development.

## Triggers & Actions

### 1. Record a Problem
**Trigger:** User says "记录这个问题", "record this problem", "save problem", "log this issue", etc.

**Action:**
1.  **Ensure Directory:** Check if `problem_summaries/` directory exists in the project root. If not, create it.
2.  **Locate Active File:**
    -   List files in `problem_summaries/` matching `problems_*.md`.
    -   Sort them to find the one with the highest index `N` (e.g., `problems_1.md`, `problems_2.md`).
    -   If no file exists, create `problem_summaries/problems_1.md` with a title `# Problem Summaries (Vol. 1)`.
3.  **Determine Next ID:**
    -   Read the active file.
    -   Find the last used Problem ID (search for lines starting with `## Problem `).
    -   New ID = Last ID + 1 (Start at 1 if no problems found).
4.  **Extract Information:**
    -   Analyze the recent conversation history to extract:
        -   **Problem Description:** What went wrong? (Error messages, unexpected behavior)
        -   **Root Cause:** Why did it happen? (Bug, configuration, logic error)
        -   **Solution:** How was it fixed? (Code change, command, workaround)
    -   If info is missing or ambiguous, do your best to summarize or ask the user for clarification (though preference is to record what is known).
5.  **Append to File:**
    -   Append the entry in the following format (ensure there is a newline before):
        ```markdown
        
        ## Problem {ID}
        **Time:** {YYYY-MM-DD HH:MM:SS}
        
        ### Description
        {Description}
        
        ### Cause
        {Cause}
        
        ### Solution
        {Solution}
        
        ---
        ```
6.  **Confirmation:** Tell the user the problem has been recorded as "Problem {ID}" in `{filename}`.

### 2. Rotate Document
**Trigger:** User says "再增加一个文档", "add another document", "new problem file", "rotate log file", etc.

**Action:**
1.  **Locate Active File:** Find the highest index `N` for `problems_N.md` in `problem_summaries/`.
2.  **Create New File:** 
    -   Calculate `N + 1`.
    -   Create `problem_summaries/problems_{N+1}.md`.
    -   Initialize it with `# Problem Summaries (Vol. {N+1})`.
3.  **Confirmation:** Inform the user that new problems will now be recorded in `problems_{N+1}.md`.

## Notes
-   **Path Handling:** Always use absolute paths or paths relative to the project root for `problem_summaries`.
-   **File Naming:** Strictly follow `problems_{N}.md` pattern to ensure correct sorting and rotation.
-   **Formatting:** Maintain clean Markdown formatting.
