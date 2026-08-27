# Taste
- For substantial projects, wants a careful planning phase first: read requirement/audit docs fully and carefully before writing any code, then produce an implementation plan covering the whole project. Confidence: 0.8
- Save implementation plans as markdown files inside the project's `docs/` directory. Confidence: 0.8
- After producing an implementation plan, spawn a fresh-context subagent (no prior assumptions) to read, validate, and harshly criticize the plan and propose optimizations before starting implementation. Confidence: 0.7
- Prefer giving spawned review subagents strict constraints (read-only, pure analysis, no file writes) and require a structured verdict/findings report mapping each finding to the requirement it affects. Confidence: 0.6
- After finishing implementation, use review agents to verify correctness and fullness (completeness against requirements). Confidence: 0.7
- Success criterion is audit-driven: every question in the audit must be answered correctly — prioritize completeness and correctness over speed. Confidence: 0.7
- Open to reusing/adapting public reference implementations (e.g., GitHub repos like crud-master-py) as the basis for services instead of designing from scratch. Confidence: 0.7
- Implementation plans should embed canonical/binding drafts of the most error-prone artifacts (e.g., docker-compose.yml, entrypoint/init scripts, code contracts) — prose-only design descriptions leave room for improvisation and are considered a gap. Confidence: 0.7
- Plans must contain an explicit gated validation loop (fail → fix → rerun from the earliest affected gate), verifying build outputs against requirements during implementation — not only end-of-build checks. Confidence: 0.8
