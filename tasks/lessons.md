# Lessons

## 2026-06-19 - Generated docs location

- Correction: Jovi asked that all generated documents live under `E:\project\douyin_to_obsidian\docs\codex`.
- Rule: For this project, create or move Codex-generated Markdown docs into `docs/codex/` by default. Keep reference materials such as `docs/glm_ref/` in their original reference folders.
- Prevention: Before finalizing documentation work, run a quick `Get-ChildItem docs -File` check and move generated docs out of the docs root if needed.
