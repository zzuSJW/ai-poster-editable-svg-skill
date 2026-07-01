# ai-poster-editable-svg-skill

Codex skill for rebuilding AI-generated poster images into Illustrator-friendly SVG:

- link a clean background image instead of embedding base64
- keep normal poster text as editable SVG `<text>`
- vectorize decorative or art text as SVG paths
- run browser rendering QA against the original poster

## Install

Replace `<owner>` with the GitHub username or organization that owns this repository:

```bash
python "%USERPROFILE%\\.codex\\skills\\.system\\skill-installer\\scripts\\install-skill-from-github.py" --repo <owner>/ai-poster-editable-svg-skill --path skills/ai-poster-editable-svg
```

Restart Codex after installation so the new skill is discovered.
