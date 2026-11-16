# JurisAtlas Interactive Installer (`jurisatlas/cli`)

Interactive desktop GUI and terminal setup tool that lets you select:
1. **Which country's Legal MCP Server(s)** you want to install — one, multiple, or **all 42 JurisAtlas jurisdictions** (`Select All (42)` in the GUI or `a` / `all` in CLI mode).
2. **Which AI application(s)** you use (**Claude Desktop, Claude Code CLI, ChatGPT Desktop, OpenAI Codex CLI, Cursor, Windsurf, VS Code / GitHub Copilot / Cline / Roo Code, Google Antigravity / Gemini CLI, Perplexity / Continue.dev / LM Studio**).

## Usage

```bash
uvx --refresh --from https://github.com/jurisatlas/cli/archive/refs/heads/main.zip jurisatlas
```

- Launches the **graphical setup window** automatically on desktop macOS, Windows, and Linux.
- Pass `--cli` for interactive terminal mode (or automatic fallback in headless / SSH environments):

```bash
uvx --refresh --from https://github.com/jurisatlas/cli/archive/refs/heads/main.zip jurisatlas --cli
```
