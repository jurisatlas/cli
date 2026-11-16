# -*- coding: utf-8 -*-
"""
JurisAtlas Interactive Setup Installer (GUI & CLI)

Supports both a desktop graphical setup window (macOS, Windows, Linux) and an
interactive terminal CLI fallback (`--cli`), allowing users to select one,
multiple, or all 42 JurisAtlas Legal MCP servers and register them with their
installed AI applications.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
from typing import Callable

JURISDICTIONS: dict[str, str] = {
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
    "xk": "Kosovo",
}

CLIENT_SPECS: list[tuple[str, str, bool]] = [
    ("1", "Claude Desktop & Claude Code CLI", False),
    ("2", "ChatGPT Desktop & OpenAI Codex CLI", False),
    ("3", "Cursor", False),
    ("4", "Windsurf", False),
    ("5", "VS Code (GitHub Copilot / Cline / Roo Code)", False),
    ("6", "Google Antigravity / Gemini CLI", False),
    ("7", "Perplexity / Continue.dev / LM Studio", False),
]

ALL_COUNTRY_TOKENS = {
    "a",
    "all",
    "*",
    "all countries",
    "all jurisdictions",
    "tum",
    "tumu",
    "tümü",
    "hepsi",
}


def get_client_paths(
    repo_name: str,
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    appdata: pathlib.Path | None = None,
) -> dict[str, tuple[str, list[pathlib.Path]]]:
    """Return AI client configuration labels and file paths for the given OS."""
    home_dir = home if home is not None else pathlib.Path.home()
    sys_name = system_name if system_name is not None else platform.system()
    is_mac = sys_name == "Darwin"
    is_win = sys_name == "Windows"
    appdata_dir = appdata if appdata is not None else pathlib.Path(os.environ.get("APPDATA", str(home_dir)))

    if is_win:
        claude_cfg = appdata_dir / "Claude" / "claude_desktop_config.json"
        chatgpt_paths = [
            appdata_dir / "ChatGPT" / "mcp.json",
            appdata_dir / "OpenAI" / "ChatGPT" / "mcp_config.json",
            home_dir / ".codex" / "mcp_config.json",
        ]
        vscode_base = appdata_dir / "Code" / "User"
    elif is_mac:
        app_support = home_dir / "Library" / "Application Support"
        claude_cfg = app_support / "Claude" / "claude_desktop_config.json"
        chatgpt_paths = [
            app_support / "ChatGPT" / "mcp.json",
            home_dir / ".codex" / "mcp_config.json",
        ]
        vscode_base = app_support / "Code" / "User"
    else:
        cfg_dir = home_dir / ".config"
        claude_cfg = cfg_dir / "Claude" / "claude_desktop_config.json"
        chatgpt_paths = [
            cfg_dir / "ChatGPT" / "mcp.json",
            home_dir / ".codex" / "mcp_config.json",
        ]
        vscode_base = cfg_dir / "Code" / "User"

    return {
        "1": (
            "Claude Desktop & Claude Code CLI",
            [claude_cfg, home_dir / ".claude.json"],
        ),
        "2": (
            "ChatGPT Desktop & OpenAI Codex CLI",
            chatgpt_paths,
        ),
        "3": (
            "Cursor",
            [home_dir / ".cursor" / "mcp.json"],
        ),
        "4": (
            "Windsurf",
            [home_dir / ".codeium" / "windsurf" / "mcp_config.json"],
        ),
        "5": (
            "VS Code (GitHub Copilot / Cline / Roo Code)",
            [
                vscode_base / "mcp.json",
                vscode_base / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
                vscode_base / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "mcp_settings.json",
            ],
        ),
        "6": (
            "Google Antigravity / Gemini CLI",
            [
                home_dir / ".gemini" / "config" / "mcp_config.json",
                home_dir / ".gemini" / "antigravity" / "mcp_config.json",
                home_dir / ".gemini" / "settings.json",
            ],
        ),
        "7": (
            "Perplexity / Continue.dev / LM Studio",
            [home_dir / ".continue" / "mcpServers" / f"{repo_name}.json"],
        ),
    }


def resolve_uvx_command(home: pathlib.Path | None = None, system_name: str | None = None) -> str:
    """Resolve an absolute `uvx` executable path so GUI apps work without shell PATH."""
    found = shutil.which("uvx")
    if found:
        return found

    home_dir = home if home is not None else pathlib.Path.home()
    sys_name = system_name if system_name is not None else platform.system()
    if sys_name == "Windows":
        local_app = pathlib.Path(os.environ.get("LOCALAPPDATA", str(home_dir / "AppData" / "Local")))
        candidates = [
            home_dir / ".local" / "bin" / "uvx.exe",
            local_app / "uv" / "uvx.exe",
            home_dir / ".cargo" / "bin" / "uvx.exe",
        ]
    else:
        candidates = [
            home_dir / ".local" / "bin" / "uvx",
            home_dir / ".cargo" / "bin" / "uvx",
            pathlib.Path("/opt/homebrew/bin/uvx"),
            pathlib.Path("/usr/local/bin/uvx"),
        ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "uvx"


def parse_country_selection(raw_countries: str) -> list[str]:
    """Parse user country input into a sorted list of jurisdiction codes."""
    text = raw_countries.strip().lower()
    if not text:
        return []

    tokens = [t.strip() for t in text.replace(";", ",").split(",") if t.strip()]
    if any(tok in ALL_COUNTRY_TOKENS for tok in tokens):
        return sorted(JURISDICTIONS.keys())

    selected_codes: list[str] = []
    for tok in tokens:
        if tok in JURISDICTIONS:
            selected_codes.append(tok)
            continue

        if tok.endswith("-legal-mcp") and tok[:-10] in JURISDICTIONS:
            selected_codes.append(tok[:-10])
            continue

        # Allow space-separated country codes such as "uk de ba"
        parts = tok.split()
        if len(parts) > 1 and all(p in JURISDICTIONS for p in parts):
            selected_codes.extend(parts)
            continue

        exact_name_matches = [code for code, cname in JURISDICTIONS.items() if tok == cname.lower()]
        if exact_name_matches:
            selected_codes.extend(exact_name_matches)
            continue

        if len(tok) >= 2:
            for code, cname in JURISDICTIONS.items():
                if tok in cname.lower():
                    selected_codes.append(code)

    return sorted(set(selected_codes))


def parse_client_selection(raw_clients: str) -> list[str]:
    """Parse user AI application selection into ordered client keys ('1'..'7')."""
    valid_keys = [k for k, _, _ in CLIENT_SPECS]
    text = raw_clients.strip().lower()
    if not text:
        return []

    normalized = text.replace(";", ",")
    if "," not in normalized and " " in normalized:
        tokens = [t.strip() for t in normalized.split() if t.strip()]
    else:
        tokens = [t.strip() for t in normalized.split(",") if t.strip()]

    if any(tok in {"a", "all", "*"} for tok in tokens):
        return valid_keys

    chosen = [tok for tok in tokens if tok in valid_keys]
    # Preserve order without duplicates
    return list(dict.fromkeys(chosen))


def build_uvx_server_entry(repo_name: str, uvx_cmd: str) -> dict[str, object]:
    """Build the MCP server entry dictionary for a JurisAtlas repository."""
    return {
        "command": uvx_cmd,
        "args": [
            "--from",
            f"https://github.com/jurisatlas/{repo_name}/archive/refs/heads/main.zip",
            repo_name,
        ],
        "env": {"PYTHONIOENCODING": "utf-8"},
    }


def upsert_json_mcp_file(
    cfg_path: pathlib.Path,
    entries_by_repo: dict[str, dict[str, object]],
    dry_run: bool = False,
) -> None:
    """Safely insert or update `mcpServers` entries in a JSON configuration file."""
    data: dict[str, object] = {}
    if cfg_path.exists() and cfg_path.stat().st_size > 0:
        try:
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            if not dry_run:
                backup_path = cfg_path.with_name(f"{cfg_path.name}.bak")
                shutil.copy2(cfg_path, backup_path)
            data = {}

    if not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
    mcp_servers = data["mcpServers"]
    assert isinstance(mcp_servers, dict)
    for repo_name, entry in entries_by_repo.items():
        mcp_servers[repo_name] = entry

    if not dry_run:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def upsert_codex_toml(
    codex_toml: pathlib.Path,
    repos: list[str],
    uvx_cmd: str,
    dry_run: bool = False,
) -> None:
    """Safely insert or update `[mcp_servers.<repo>]` sections in `~/.codex/config.toml`."""
    existing = codex_toml.read_text(encoding="utf-8") if codex_toml.exists() else ""
    esc_cmd = uvx_cmd.replace("\\", "\\\\")
    updated = existing

    for repo_name in repos:
        block = (
            f"[mcp_servers.{repo_name}]\n"
            f'command = "{esc_cmd}"\n'
            f'args = ["--from", "https://github.com/jurisatlas/{repo_name}/archive/refs/heads/main.zip", "{repo_name}"]\n'
        )
        pattern = rf"(?ms)^\[mcp_servers\.{re.escape(repo_name)}\].*?(?=^\[|\Z)"
        if re.search(pattern, updated):
            updated = re.sub(pattern, block + "\n", updated)
        else:
            updated = (updated.rstrip() + "\n\n" + block) if updated.strip() else block

    if not dry_run:
        codex_toml.parent.mkdir(parents=True, exist_ok=True)
        codex_toml.write_text(updated, encoding="utf-8")


def install_servers(
    selected_codes: list[str],
    chosen_keys: list[str],
    uvx_cmd: str | None = None,
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    appdata: pathlib.Path | None = None,
    dry_run: bool = False,
    progress_cb: Callable[[int, str], None] | None = None,
) -> list[tuple[str, str, str]]:
    """Configure selected JurisAtlas servers in selected AI client configuration files."""
    if not selected_codes:
        raise ValueError("At least one jurisdiction must be selected.")
    if not chosen_keys:
        raise ValueError("At least one AI application must be selected.")

    home_dir = home if home is not None else pathlib.Path.home()
    resolved_uvx = uvx_cmd or resolve_uvx_command(home=home_dir, system_name=system_name)

    if progress_cb:
        progress_cb(10, f"Preparing configuration for {len(selected_codes)} jurisdiction(s)...")

    # Group MCP entries by config file path so each JSON file is read and written once.
    file_entries: dict[pathlib.Path, dict[str, dict[str, object]]] = {}
    file_labels: dict[pathlib.Path, str] = {}
    recorded_links: list[tuple[str, str, str]] = []
    repos: list[str] = []

    for code in selected_codes:
        repo = f"{code}-legal-mcp"
        repos.append(repo)
        entry = build_uvx_server_entry(repo, resolved_uvx)
        client_map = get_client_paths(repo, home=home_dir, system_name=system_name, appdata=appdata)
        for key in chosen_keys:
            if key not in client_map:
                continue
            label, paths = client_map[key]
            for cfg_path in paths:
                file_entries.setdefault(cfg_path, {})[repo] = entry
                file_labels[cfg_path] = label
                recorded_links.append((label, repo, str(cfg_path)))

    total_targets = len(file_entries) + (1 if "2" in chosen_keys else 0)
    completed = 0

    for cfg_path, entries in file_entries.items():
        upsert_json_mcp_file(cfg_path, entries, dry_run=dry_run)
        completed += 1
        if progress_cb and total_targets > 0:
            pct = 15 + int((completed / total_targets) * 80)
            progress_cb(pct, f"Configured {file_labels[cfg_path]} ({cfg_path.name})")

    if "2" in chosen_keys:
        codex_toml = home_dir / ".codex" / "config.toml"
        upsert_codex_toml(codex_toml, repos, resolved_uvx, dry_run=dry_run)
        completed += 1
        if progress_cb:
            progress_cb(95, "Configured OpenAI Codex CLI (config.toml)")

    if progress_cb:
        progress_cb(100, "Installation Complete!")

    return recorded_links


def _can_launch_gui(force_cli: bool = False, force_gui: bool = False) -> bool:
    """Return True when a desktop GUI session and Tkinter are available."""
    if force_cli or os.environ.get("JURISATLAS_CLI") == "1":
        return False
    if force_gui:
        return True

    sys_name = platform.system()
    if sys_name == "Linux" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    if sys_name == "Darwin" and (os.environ.get("SSH_TTY") or os.environ.get("SSH_CONNECTION")):
        return False

    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    return True


def _bring_mac_window_to_front() -> None:
    """Best-effort focus activation on macOS when launched from Terminal."""
    if platform.system() != "Darwin":
        return
    try:
        pid = os.getpid()
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "System Events" to set frontmost of the first process whose unix id is {pid} to true',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except Exception:
        pass


def run_gui(dry_run: bool = False) -> None:
    """Launch the cross-platform Tkinter graphical setup window."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("JurisAtlas — Interactive Legal MCP Installer (42 Jurisdictions)")
    root.geometry("760x720")
    root.minsize(660, 560)

    is_mac = platform.system() == "Darwin"
    style = ttk.Style()
    if not is_mac:
        if "clam" in style.theme_names():
            style.theme_use("clam")
        root.configure(bg="#f8fafc")

    base_bg = root.cget("bg")
    font_family = "SF Pro Text" if is_mac else "Segoe UI"

    container = ttk.Frame(root, padding=(18, 14, 18, 14))
    container.pack(fill="both", expand=True)

    header_lbl = ttk.Label(
        container,
        text="JurisAtlas: Interactive Legal MCP Setup (42 Jurisdictions)",
        font=(font_family, 15, "bold"),
    )
    header_lbl.pack(anchor="w", pady=(0, 8))

    info_box = tk.Frame(
        container,
        bg="#e0f2fe",
        highlightbackground="#7dd3fc",
        highlightthickness=1,
        padx=12,
        pady=9,
    )
    info_box.pack(fill="x", pady=(0, 12))
    tk.Label(
        info_box,
        text=(
            "Read-Only & Isolated Installation\n"
            "• Does NOT access or modify your personal files or documents.\n"
            "• Choose specific countries or click 'Select All (42)', then select your AI application(s)."
        ),
        bg="#e0f2fe",
        fg="#0f172a",
        justify="left",
        anchor="w",
        font=(font_family, 10),
    ).pack(fill="x")

    # Bottom fixed section packed BEFORE the expandable country list so the
    # AI client selector, progress bar, and Install button are always visible.
    bottom_section = ttk.Frame(container)
    bottom_section.pack(side="bottom", fill="x")

    # Step 2: AI Client Selection
    client_frame = ttk.LabelFrame(bottom_section, text="2. Select the AI Application(s) You Use", padding=(10, 8))
    client_frame.pack(fill="x", pady=(0, 10))

    client_toolbar = ttk.Frame(client_frame)
    client_toolbar.pack(fill="x", pady=(0, 6))

    client_vars: dict[str, tk.BooleanVar] = {
        key: tk.BooleanVar(value=default) for key, _, default in CLIENT_SPECS
    }

    def set_all_clients(state: bool) -> None:
        for var in client_vars.values():
            var.set(state)

    ttk.Button(client_toolbar, text="Select All Clients", command=lambda: set_all_clients(True)).pack(
        side="left", padx=(0, 6)
    )
    ttk.Button(client_toolbar, text="Clear Clients", command=lambda: set_all_clients(False)).pack(side="left")

    clients_grid = ttk.Frame(client_frame)
    clients_grid.pack(fill="x")
    clients_grid.columnconfigure(0, weight=1)
    clients_grid.columnconfigure(1, weight=1)

    for idx, (key, label, _default) in enumerate(CLIENT_SPECS):
        ttk.Checkbutton(
            clients_grid,
            text=label,
            variable=client_vars[key],
        ).grid(row=idx // 2, column=idx % 2, sticky="w", padx=6, pady=3)

    # Progress & Action Section
    status_var = tk.StringVar(value="Select jurisdictions and AI applications above, then click Install.")
    ttk.Label(bottom_section, textvariable=status_var, font=(font_family, 10)).pack(anchor="w", pady=(2, 4))

    progress = ttk.Progressbar(bottom_section, orient="horizontal", mode="determinate", maximum=100, value=0)
    progress.pack(fill="x", pady=(0, 10))

    btn_row = ttk.Frame(bottom_section)
    btn_row.pack(fill="x")

    install_btn = ttk.Button(
        btn_row,
        text="Install to Selected AI Clients",
        default="active",
    )
    install_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
    close_btn = ttk.Button(btn_row, text="Close", command=lambda: root.destroy())
    close_btn.pack(side="right")

    # Step 1: Expandable Country Selection (fills remaining middle space)
    country_frame = ttk.LabelFrame(container, text="1. Select Jurisdictions (Countries)", padding=(10, 8))
    country_frame.pack(side="top", fill="both", expand=True, pady=(0, 10))

    toolbar = ttk.Frame(country_frame)
    toolbar.pack(fill="x", pady=(0, 8))

    sorted_items = sorted(JURISDICTIONS.items(), key=lambda x: x[1])
    country_vars: dict[str, tk.BooleanVar] = {
        code: tk.BooleanVar(value=False) for code, _ in sorted_items
    }
    search_var = tk.StringVar(value="")
    count_var = tk.StringVar(value=f"Selected: 0 / {len(sorted_items)}")

    def update_count() -> None:
        selected_n = sum(1 for v in country_vars.values() if v.get())
        suffix = " (All)" if selected_n == len(sorted_items) else ""
        count_var.set(f"Selected: {selected_n} / {len(sorted_items)}{suffix}")

    def select_all_countries() -> None:
        for var in country_vars.values():
            var.set(True)
        update_count()

    def clear_all_countries() -> None:
        for var in country_vars.values():
            var.set(False)
        update_count()

    ttk.Button(toolbar, text=f"Select All ({len(sorted_items)})", command=select_all_countries).pack(
        side="left", padx=(0, 6)
    )
    ttk.Button(toolbar, text="Clear All", command=clear_all_countries).pack(side="left", padx=(0, 14))
    ttk.Label(toolbar, text="Filter:").pack(side="left", padx=(0, 4))
    search_entry = ttk.Entry(toolbar, textvariable=search_var, width=20)
    search_entry.pack(side="left", padx=(0, 10))
    ttk.Label(toolbar, textvariable=count_var, font=(font_family, 10, "bold")).pack(side="right")

    list_container = ttk.Frame(country_frame)
    list_container.pack(fill="both", expand=True)

    canvas = tk.Canvas(list_container, highlightthickness=0, bd=0, bg=base_bg, height=190)
    scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
    grid_frame = ttk.Frame(canvas)
    canvas_window = canvas.create_window((0, 0), window=grid_frame, anchor="nw")

    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _sync_scrollregion(_event: object = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _sync_canvas_width(event: tk.Event) -> None:  # type: ignore[type-arg]
        canvas.itemconfigure(canvas_window, width=event.width)

    grid_frame.bind("<Configure>", _sync_scrollregion)
    canvas.bind("<Configure>", _sync_canvas_width)

    def _on_mousewheel(event: tk.Event) -> None:  # type: ignore[type-arg]
        if getattr(event, "num", None) == 4:
            canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(1, "units")
        elif getattr(event, "delta", 0):
            step = -1 if event.delta > 0 else 1
            if not is_mac and abs(event.delta) >= 120:
                step = -int(event.delta / 120)
            canvas.yview_scroll(step, "units")

    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        canvas.bind(seq, _on_mousewheel)
        grid_frame.bind(seq, _on_mousewheel)

    country_checks: dict[str, ttk.Checkbutton] = {}
    for col in range(3):
        grid_frame.columnconfigure(col, weight=1, uniform="country_col")

    def render_countries(*_args: object) -> None:
        query = search_var.get().strip().lower()
        for cb in country_checks.values():
            cb.grid_forget()

        filtered = [
            (code, name)
            for code, name in sorted_items
            if not query or query in name.lower() or query in code.lower()
        ]
        for idx, (code, name) in enumerate(filtered):
            cb = country_checks[code]
            cb.grid(row=idx // 3, column=idx % 3, sticky="w", padx=6, pady=3)
        canvas.yview_moveto(0.0)
        _sync_scrollregion()

    for code, name in sorted_items:
        cb = ttk.Checkbutton(
            grid_frame,
            text=f"{name} [{code}]",
            variable=country_vars[code],
            command=update_count,
        )
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cb.bind(seq, _on_mousewheel)
        country_checks[code] = cb

    search_var.trace_add("write", render_countries)
    render_countries()

    def start_install() -> None:
        chosen_codes = [code for code, _ in sorted_items if country_vars[code].get()]
        chosen_clients = [key for key, _, _ in CLIENT_SPECS if client_vars[key].get()]

        if not chosen_codes:
            messagebox.showwarning(
                "No Jurisdiction Selected",
                "Please select at least one country (or click 'Select All (42)').",
                parent=root,
            )
            return
        if not chosen_clients:
            messagebox.showwarning(
                "No AI Client Selected",
                "Please select at least one AI application.",
                parent=root,
            )
            return

        install_btn.configure(state="disabled", text="Installing... Please wait")
        close_btn.configure(state="disabled")
        progress.configure(value=5)
        status_var.set("Starting installation...")

        events: queue.Queue[tuple[str, object]] = queue.Queue()

        def on_progress(pct: int, msg: str) -> None:
            events.put(("progress", (pct, msg)))

        def worker() -> None:
            try:
                links = install_servers(
                    chosen_codes,
                    chosen_clients,
                    dry_run=dry_run,
                    progress_cb=on_progress,
                )
                events.put(("done", links))
            except Exception as exc:
                events.put(("error", str(exc)))

        def poll_events() -> None:
            try:
                while True:
                    kind, payload = events.get_nowait()
                    if kind == "progress":
                        pct, msg = payload  # type: ignore[misc]
                        progress.configure(value=pct)
                        status_var.set(str(msg))
                    elif kind == "done":
                        links = payload  # type: ignore[assignment]
                        unique_files = len({cfg for _, _, cfg in links})
                        country_summary = (
                            "All 42 jurisdictions"
                            if len(chosen_codes) == len(JURISDICTIONS)
                            else f"{len(chosen_codes)} jurisdiction(s)"
                        )
                        install_btn.configure(state="normal", text="Install to Selected AI Clients")
                        close_btn.configure(state="normal")
                        messagebox.showinfo(
                            "JurisAtlas - Setup Complete",
                            f"Configured {country_summary} across {unique_files} AI client config file(s).\n\n"
                            "Please restart your selected AI application(s) to load the legal tools.",
                            parent=root,
                        )
                        root.destroy()
                        return
                    elif kind == "error":
                        err_msg = str(payload)
                        install_btn.configure(state="normal", text="Retry Installation")
                        close_btn.configure(state="normal")
                        status_var.set(f"Error: {err_msg}")
                        messagebox.showerror(
                            "Setup Error",
                            f"An error occurred during setup:\n{err_msg}",
                            parent=root,
                        )
                        return
            except queue.Empty:
                pass
            if root.winfo_exists():
                root.after(50, poll_events)

        threading.Thread(target=worker, daemon=True).start()
        root.after(50, poll_events)

    install_btn.configure(command=start_install)

    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    if is_mac:
        root.lift()
        root.attributes("-topmost", True)
        topmost_id = root.after(200, lambda: root.winfo_exists() and root.attributes("-topmost", False))
        focus_id = root.after(50, _bring_mac_window_to_front)
        root.focus_force()
    else:
        topmost_id = None
        focus_id = None

    orig_destroy = root.destroy

    def clean_destroy() -> None:
        for aid in (topmost_id, focus_id):
            if aid is not None:
                try:
                    root.after_cancel(aid)
                except Exception:
                    pass
        orig_destroy()

    root.destroy = clean_destroy  # type: ignore[method-assign]

    root.mainloop()


def run_cli(
    countries_arg: str | None = None,
    clients_arg: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run the interactive (or argument-driven) terminal installer."""
    print("\n==========================================================================")
    print("  JurisAtlas — Interactive Legal MCP Installer (42 Jurisdictions)")
    print("==========================================================================\n")

    if countries_arg is None:
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
        print("\n  [A]  All 42 jurisdictions (type 'a' or 'all')")

        print("\n--------------------------------------------------------------------------")
        raw_countries = input(
            "1. Enter country code(s) to install (e.g. ba, de, uk, us, country name, or A/all for all 42): "
        ).strip()
        if not raw_countries:
            print("No country selected. Exiting.")
            sys.exit(0)
    else:
        raw_countries = countries_arg

    selected_codes = parse_country_selection(raw_countries)
    if not selected_codes:
        print(f"Could not match '{raw_countries}' to a supported jurisdiction code.")
        sys.exit(1)

    print("\nSelected Jurisdiction(s):")
    if len(selected_codes) == len(JURISDICTIONS):
        print(f"  -> All {len(JURISDICTIONS)} JurisAtlas jurisdictions selected.")
    else:
        for c in selected_codes:
            print(f"  -> {JURISDICTIONS[c]} ({c}-legal-mcp)")

    if clients_arg is None and countries_arg is None:
        print("\n--------------------------------------------------------------------------")
        print("Available AI Applications:")
        for key, label, _ in CLIENT_SPECS:
            print(f"  [{key}] {label}")
        print("  [A] All of the above")
        while True:
            raw_clients = input(
                "\n2. Which AI application(s) do you use? (e.g. 1, 2, 3 or A for all): "
            ).strip()
            chosen_keys = parse_client_selection(raw_clients)
            if chosen_keys:
                break
            print("Please select at least one AI application (1-7 or A for all) before continuing.")
    elif clients_arg is not None:
        chosen_keys = parse_client_selection(clients_arg)
        if not chosen_keys:
            print(f"Could not match '{clients_arg}' to any supported AI application.")
            sys.exit(1)
    else:
        print("Please specify --clients (e.g. --clients 6 or --clients all). No AI application is selected by default.")
        sys.exit(1)

    configured_files = install_servers(selected_codes, chosen_keys, dry_run=dry_run)

    print("\n==========================================================================")
    print("  Installation Complete!" + (" (Dry Run — no files written)" if dry_run else ""))
    if len(selected_codes) == len(JURISDICTIONS):
        seen_labels = list(dict.fromkeys(label for label, _, _ in configured_files))
        for label in seen_labels:
            print(f"  [OK] Connected all {len(selected_codes)} jurisdictions -> {label}")
    else:
        for label, repo, _cfg_path in configured_files:
            print(f"  [OK] Connected {repo} -> {label}")
    print("\n  Please restart your selected AI application(s) to load the legal tools.")
    print("==========================================================================\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jurisatlas",
        description="Interactive installer for JurisAtlas Legal MCP Servers (42 Jurisdictions).",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--cli", action="store_true", help="Use interactive terminal mode instead of GUI")
    mode_group.add_argument("--gui", action="store_true", help="Launch graphical setup window")
    parser.add_argument(
        "--countries",
        help="Comma-separated jurisdiction codes/names or 'all' (runs in CLI mode)",
    )
    parser.add_argument(
        "--clients",
        help="Comma-separated AI client numbers (1-7) or 'all' (used with --countries)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without modifying configuration files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.countries is not None or args.cli:
        run_cli(countries_arg=args.countries, clients_arg=args.clients, dry_run=args.dry_run)
        return

    if _can_launch_gui(force_cli=args.cli, force_gui=args.gui):
        try:
            print("Launching JurisAtlas Setup Window... (Tip: pass --cli for terminal mode)")
            run_gui(dry_run=args.dry_run)
            return
        except Exception as exc:
            if args.gui:
                print(f"Could not start GUI ({exc}).", file=sys.stderr)
                sys.exit(1)
            print(f"GUI unavailable ({exc}); switching to interactive terminal mode.")

    run_cli(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
