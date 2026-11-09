# -*- coding: utf-8 -*-
"""
JurisAtlas Interactive Setup CLI
Prompts the user to select:
1. Which country/jurisdiction Legal MCP server(s) they want to install (out of 42 jurisdictions)
2. Which AI client(s) they use (Claude Desktop, Cursor, Windsurf, VS Code / Copilot / Cline, Antigravity, Continue.dev)
And automatically configures the selected AI applications.
"""
import json
import os
import pathlib
import platform
import shutil
import sys

JURISDICTIONS = {
    "al": "Albania",
    "at": "Austria",
    "au": "Australia",
    "ba": "Bosnia and Herzegovina",
    "be": "Belgium",
    "bg": "Bulgaria",
    "ch": "Switzerland",
    "cy": "Cyprus",
    "cz": "Czechia",
    "de": "Germany",
    "dk": "Denmark",
    "ee": "Estonia",
    "es": "Spain",
    "eu": "European Union & ECHR",
    "fi": "Finland",
    "fr": "France",
    "gr": "Greece",
    "hr": "Croatia",
    "hu": "Hungary",
    "ie": "Ireland",
    "is": "Iceland",
    "it": "Italy",
    "li": "Liechtenstein",
    "lt": "Lithuania",
    "lu": "Luxembourg",
    "lv": "Latvia",
    "me": "Montenegro",
    "mk": "North Macedonia",
    "mt": "Malta",
    "nl": "Netherlands",
    "no": "Norway",
    "nz": "New Zealand",
    "pl": "Poland",
    "pt": "Portugal",
    "ro": "Romania",
    "rs": "Serbia",
    "se": "Sweden",
    "si": "Slovenia",
    "sk": "Slovakia",
    "uk": "United Kingdom",
    "us": "United States",
    "xk": "Kosovo"
}


def get_client_paths(repo_name: str) -> dict:
    home = pathlib.Path.home()
    is_mac = platform.system() == "Darwin"
    is_win = platform.system() == "Windows"
    appdata = pathlib.Path(os.environ.get("APPDATA", str(home)))

    if is_win:
        claude_cfg = appdata / "Claude" / "claude_desktop_config.json"
        vscode_cfg = appdata / "Code" / "User" / "mcp.json"
        cline_cfg = appdata / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"
    elif is_mac:
        claude_cfg = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        vscode_cfg = home / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
        cline_cfg = home / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"
    else:
        claude_cfg = home / ".config" / "Claude" / "claude_desktop_config.json"
        vscode_cfg = home / ".config" / "Code" / "User" / "mcp.json"
        cline_cfg = home / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"

    return {
        "1": ("Claude Desktop & Claude Code CLI", [claude_cfg, home / ".claude.json"]),
        "2": ("ChatGPT Desktop & OpenAI Codex CLI", [home / ".codex" / "mcp_config.json", appdata / "OpenAI" / "ChatGPT" / "mcp_config.json"]),
        "3": ("Cursor", [home / ".cursor" / "mcp.json"]),
        "4": ("Windsurf", [home / ".codeium" / "windsurf" / "mcp_config.json"]),
        "5": ("VS Code (GitHub Copilot / Cline / Roo Code)", [vscode_cfg, cline_cfg]),
        "6": ("Google Antigravity / Gemini CLI", [home / ".gemini" / "config" / "mcp_config.json", home / ".gemini" / "settings.json"]),
        "7": ("Perplexity / Continue.dev / LM Studio", [home / ".continue" / "mcpServers" / f"{repo_name}.json"]),
    }


def main() -> None:
    print("\n==========================================================================")
    print("  JurisAtlas — Interactive Legal MCP Installer (42 Jurisdictions)")
    print("==========================================================================\n")

    items = sorted(JURISDICTIONS.items(), key=lambda x: x[1])
    half = (len(items) + 1) // 2
    for i in range(half):
        left_code, left_name = items[i]
        left_str = f"[{left_code}] {left_name:<26}"
        right_str = ""
        if i + half < len(items):
            right_code, right_name = items[i + half]
            right_str = f"[{right_code}] {right_name}"
        print(f"  {left_str}  {right_str}")

    print("\n--------------------------------------------------------------------------")
    raw_countries = input("1. Enter country code(s) to install (e.g. ba, de, uk, us or country name): ").strip().lower()
    if not raw_countries:
        print("No country selected. Exiting.")
        sys.exit(0)

    selected_codes = []
    tokens = [t.strip() for t in raw_countries.replace(";", ",").split(",") if t.strip()]
    for tok in tokens:
        if tok in JURISDICTIONS:
            selected_codes.append(tok)
        else:
            for code, cname in JURISDICTIONS.items():
                if tok in cname.lower() or f"{code}-legal-mcp" == tok:
                    selected_codes.append(code)

    selected_codes = sorted(set(selected_codes))
    if not selected_codes:
        print(f"Could not match '{raw_countries}' to a supported jurisdiction code.")
        sys.exit(1)

    print("\nSelected Jurisdiction(s):")
    for c in selected_codes:
        print(f"  -> {JURISDICTIONS[c]} ({c}-legal-mcp)")

    print("\n--------------------------------------------------------------------------")
    print("Available AI Applications:")
    print("  [1] Claude Desktop & Claude Code CLI")
    print("  [2] ChatGPT Desktop & OpenAI Codex CLI")
    print("  [3] Cursor")
    print("  [4] Windsurf")
    print("  [5] VS Code (GitHub Copilot / Cline / Roo Code)")
    print("  [6] Google Antigravity / Gemini CLI")
    print("  [7] Perplexity / Continue.dev / LM Studio")
    print("  [A] All of the above")
    raw_clients = input("\n2. Which AI application(s) do you use? (e.g. 1, 2, 3 or A for all) [Default: A]: ").strip().lower()
    if not raw_clients:
        raw_clients = "a"

    uvx_cmd = shutil.which("uvx") or "uvx"

    configured_files = []
    for code in selected_codes:
        repo = f"{code}-legal-mcp"
        client_map = get_client_paths(repo)
        if "a" in raw_clients or "all" in raw_clients:
            chosen_keys = list(client_map.keys())
        else:
            chosen_keys = [k.strip() for k in raw_clients.replace(";", ",").split(",") if k.strip() in client_map]
            if not chosen_keys:
                chosen_keys = list(client_map.keys())

        for key in chosen_keys:
            label, paths = client_map[key]
            for cfg in paths:
                try:
                    cfg.parent.mkdir(parents=True, exist_ok=True)
                    data = json.loads(cfg.read_text(encoding="utf-8")) if (cfg.exists() and cfg.stat().st_size > 0) else {}
                except Exception:
                    data = {}
                if not isinstance(data.get("mcpServers"), dict):
                    data["mcpServers"] = {}
                data["mcpServers"][repo] = {
                    "command": uvx_cmd,
                    "args": [
                        "--from",
                        f"https://github.com/jurisatlas/{repo}/archive/refs/heads/main.zip",
                        repo,
                    ],
                    "env": {"PYTHONIOENCODING": "utf-8"},
                }
                cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
                configured_files.append((label, repo, str(cfg)))

        # Also write OpenAI Codex CLI ~/.codex/config.toml entry if '2' or 'a' selected
        if "2" in chosen_keys:
            try:
                codex_toml = pathlib.Path.home() / ".codex" / "config.toml"
                codex_toml.parent.mkdir(parents=True, exist_ok=True)
                existing_toml = codex_toml.read_text(encoding="utf-8") if codex_toml.exists() else ""
                section_header = f"[mcp_servers.{repo}]"
                if section_header not in existing_toml:
                    block = (
                        f"\n{section_header}\n"
                        f'command = "{uvx_cmd.replace(chr(92), chr(92)*2)}"\n'
                        f'args = ["--from", "https://github.com/jurisatlas/{repo}/archive/refs/heads/main.zip", "{repo}"]\n'
                    )
                    codex_toml.write_text(existing_toml + block, encoding="utf-8")
            except Exception:
                pass

    print("\n==========================================================================")
    print("  Installation Complete!")
    for label, repo, cfg_path in configured_files:
        print(f"  [OK] Connected {repo} -> {label}")
    print("\n  Please restart your selected AI application(s) to load the legal tools.")
    print("==========================================================================\n")


if __name__ == "__main__":
    main()
