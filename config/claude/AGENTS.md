## How to work with me

Be critical. Don't tell me I'm right all the time. We're equals. Stay neutral and objective.

Answer succinctly. Skip preamble, recaps, and narration of what you're about to do. Give the answer, and expand only when I ask for detail.

Don't overuse emoji.

Spanish prose/docs/reports/Markdown: preserve natural Spanish orthography, including accents, `ñ`, `¿`, `¡`, and normal Unicode. The ASCII-only editing preference does not apply to these artifacts.

## Writing

Never use em dashes (—) or en dashes (–) as punctuation. Rephrase with periods, commas, or parentheses. Applies to docs, READMEs, commit messages, PR and issue text, and blog posts. Hyphens in compound words are fine.

Drafts for clients, JIRA comments, emails or chat (Discord, Slack): short and in Spanish by default. State the outcome and next step; skip technical detail unless I ask for it.

## Code

When working with Laravel projects, always use the spatie-guidelines skill. It does not apply to Drupal, Symfony or other PHP projects.

Use the agent-browser skill for browser automation by default. Use Chrome or Safari when the task needs my logged-in session or I ask for it.

Only create a worktree for large or multi-step tasks, never for a small one-off change (especially in DDEV projects, where each worktree spins up a full environment). Inside a worktree session, run plain commands from the worktree root: no `cd` and no long chained commands.

## Git/GitHub

For questions about GitHub, use the gh tool
Never mention Claude Code in PR descriptions, PR comments, or issue comments
Do not include a "Test plan" section in PR descriptions
Do not include `Co-Authored-By` trailers or any mention of Claude in commit messages
Write commit messages in English using Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`), even when the rest of the project is in Spanish
