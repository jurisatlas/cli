# -*- coding: utf-8 -*-
"""
JurisAtlas Interactive Setup Installer (GUI & CLI) — v2.0.0

Connects desktop AI assistants to official public legislation and court portals
across 42+ jurisdictions. Supports:
  - Unified `jurisatlas-mcp` mode (default: 1 lightweight server, 7 tools)
  - Optional legacy per-country standalone mode (`--mode standalone`)
  - Pluggable `EXTRA_MCP_BUNDLES` registry (e.g. Türkiye / `hukuk-mcp`)
  - Regional presets, installed AI app auto-detection, 1-click uninstall,
    non-blocking connection check, and tailored "First 60 Seconds" prompts
  - Atomic JSONC/TOML config writes with timestamped backups
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import pathlib
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
from typing import Any, Callable

_THIS_DIR = str(pathlib.Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from jurisatlas_i18n import (  # noqa: E402
    LANGUAGE_CODES,
    LANGUAGE_DISPLAY_OPTIONS,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    configure_console_utf8,
    detect_system_language,
    normalize_language_code,
    t,
)

VERSION = "2.0.0"

PRESET_I18N_KEYS: dict[str, str] = {
    "EU + UK + CH": "preset_eu_uk_ch",
    "DACH (DE/AT/CH)": "preset_dach",
    "Common Law (UK/US/AU/NZ/IE)": "preset_common_law",
    "Nordics": "preset_nordics",
    "Western Balkans": "preset_western_balkans",
    "Türkiye + EU": "preset_turkiye_eu",
    "All Jurisdictions": "preset_all",
}

UNIFIED_SERVER_NAME = "jurisatlas-mcp"
UNIFIED_PACKAGE_URL = "https://github.com/jurisatlas/jurisatlas-mcp/archive/refs/heads/main.zip"
CLI_PACKAGE_URL = "https://github.com/jurisatlas/cli/archive/refs/heads/main.zip"

REMOTE_CONNECTOR_NOTE = (
    "Note: JurisAtlas installs directly from GitHub and runs 100% locally "
    "with no hosted server. Browser-only ChatGPT Web / Claude Web cannot launch local tools."
)

TRUST_BANNER_TEXT = "Read-Only · Free · Never touches personal files · 1-Click Uninstall"

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

# Pluggable external MCP server bundles.
# Dropping a single entry here automatically wires it into:
#   - GUI country list, presets & search
#   - CLI country parser & listings
#   - Unified & standalone installers
#   - 1-Click Uninstaller
#   - First 60 Seconds starter prompts
EXTRA_MCP_BUNDLES: dict[str, dict[str, Any]] = {
    "tr": {
        "name": "Türkiye",
        "server_name": "tr-legal-mcp",
        "package_url": "https://github.com/jurisatlas/tr-legal-mcp/archive/refs/heads/main.zip",
        "entrypoint": "tr-legal-mcp",
        "aliases": ["tur", "turkey", "türkiye", "turkiye", "türk", "turk", "yargi", "yargı", "uyap"],
        "extra_args": [],
        "env": {"PYTHONIOENCODING": "utf-8"},
        "unified_supported": False,
        "starter_prompts": [
            (
                "Türk Borçlar Kanunu & Yargıtay İçtihat",
                "6098 sayılı Türk Borçlar Kanunu madde 344 kapsamındaki kira tespit davalarına ilişkin güncel Yargıtay Hukuk Genel Kurulu ve 3. Hukuk Dairesi emsal kararlarını bul, esas/karar numaralarıyla özetle.",
            ),
            (
                "AYM Bireysel Başvuru & Danıştay",
                "Anayasa Mahkemesi bireysel başvuru kararlarında makul sürede yargılanma hakkı ihlali ölçütlerini ve güncel Danıştay idari yargı içtihatlarını karşılaştırmalı olarak listele.",
            ),
            (
                "KVKK Mevzuat & Kurul Kararları",
                "6698 sayılı KVKK kapsamında açık rıza ve veri ihlali bildirimine ilişkin güncel KVKK Kurul kararları ile ilgili mevzuat maddelerini getir.",
            ),
        ],
    },
}

EU_27_CODES: tuple[str, ...] = (
    "at",
    "be",
    "bg",
    "cy",
    "cz",
    "de",
    "dk",
    "ee",
    "es",
    "fi",
    "fr",
    "gr",
    "hr",
    "hu",
    "ie",
    "it",
    "lt",
    "lu",
    "lv",
    "mt",
    "nl",
    "pl",
    "pt",
    "ro",
    "se",
    "si",
    "sk",
)

REGIONAL_PRESETS: dict[str, list[str]] = {
    "EU + UK + CH": sorted([*EU_27_CODES, "eu", "uk", "ch"]),
    "DACH (DE/AT/CH)": ["at", "ch", "de"],
    "Common Law (UK/US/AU/NZ/IE)": ["au", "ie", "nz", "uk", "us"],
    "Nordics": ["dk", "fi", "is", "no", "se"],
    "Western Balkans": ["al", "ba", "me", "mk", "rs", "xk"],
    "Türkiye + EU": ["eu", "tr"],
    "All Jurisdictions": sorted([*JURISDICTIONS.keys(), *EXTRA_MCP_BUNDLES.keys()]),
}

PRESET_ALIASES: dict[str, str] = {
    "eu+uk+ch": "EU + UK + CH",
    "eu-uk-ch": "EU + UK + CH",
    "eu uk ch": "EU + UK + CH",
    "dach": "DACH (DE/AT/CH)",
    "common law": "Common Law (UK/US/AU/NZ/IE)",
    "common-law": "Common Law (UK/US/AU/NZ/IE)",
    "commonlaw": "Common Law (UK/US/AU/NZ/IE)",
    "nordics": "Nordics",
    "nordic": "Nordics",
    "western balkans": "Western Balkans",
    "western-balkans": "Western Balkans",
    "balkans": "Western Balkans",
    "tr+eu": "Türkiye + EU",
    "tr-eu": "Türkiye + EU",
    "turkiye+eu": "Türkiye + EU",
    "turkiye-eu": "Türkiye + EU",
    "turkey+eu": "Türkiye + EU",
    "turkey-eu": "Türkiye + EU",
}

CLIENT_SPECS: list[tuple[str, str, bool]] = [
    ("1", "Claude Desktop & Claude Code CLI", False),
    ("2", "OpenAI Codex CLI", False),
    ("3", "Cursor", False),
    ("4", "Windsurf", False),
    ("5", "VS Code (GitHub Copilot / Cline / Roo Code)", False),
    ("6", "Google Antigravity / Gemini CLI", False),
    ("7", "LM Studio", False),
    ("8", "Continue.dev", False),
]

CLIENT_ALIASES: dict[str, str] = {
    "claude": "1",
    "claude-desktop": "1",
    "claude-code": "1",
    "codex": "2",
    "openai-codex": "2",
    "cursor": "3",
    "windsurf": "4",
    "vscode": "5",
    "vs-code": "5",
    "copilot": "5",
    "cline": "5",
    "roo": "5",
    "antigravity": "6",
    "gemini": "6",
    "gemini-cli": "6",
    "lmstudio": "7",
    "lm-studio": "7",
    "continue": "8",
    "continue.dev": "8",
    "continue-dev": "8",
}

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

STANDALONE_WARNING_THRESHOLD = 5

JURISDICTION_SAMPLE_PROMPTS: dict[str, list[tuple[str, str]]] = {
    "nz": [
        (
            "Search New Zealand Legislation & NZSC",
            "Look up the Contract and Commercial Law Act 2017 on legislation.govt.nz and find Supreme Court of New Zealand (NZSC) decisions with official URLs.",
        ),
    ],
    "uk": [
        (
            "Verify a UK Supreme Court Citation",
            "Verify the official UK Supreme Court citation [2024] UKSC 12 using JurisAtlas and summarize the holding with the official portal URL.",
        ),
        (
            "Search UK Legislation",
            "Search UK legislation for the Consumer Rights Act 2015 unfair contract terms provisions and list the relevant sections.",
        ),
        (
            "Check UK Court Hierarchy",
            "Map the 3-tier court hierarchy for the United Kingdom and find recent Court of Appeal decisions on breach of fiduciary duty.",
        ),
    ],
    "eu": [
        (
            "Look Up EU GDPR Provision",
            "Retrieve official EUR-Lex text for CELEX:32016R0679 (GDPR) Article 6 lawful bases for processing and summarize key obligations.",
        ),
        (
            "Search CJEU & ECHR Case Law",
            "Search European Union and ECHR case law for proportionality in data retention and verify each citation against official portals.",
        ),
        (
            "Verify EU Citation",
            "Verify whether CELEX:32016R0679 is an official EU legal record and provide its official EUR-Lex metadata.",
        ),
    ],
    "ch": [
        (
            "Swiss Code of Obligations Lookup",
            "Look up Swiss Code of Obligations (OR) Article 97 on breach of contract and explain the burden of proof under Swiss law.",
        ),
        (
            "Swiss Federal Supreme Court Precedent",
            "Search Swiss Federal Supreme Court (Bundesgericht) decisions citing BGE 149 III 12 and verify the official citation.",
        ),
        (
            "Cantonal vs Federal Courts",
            "List Switzerland's 3-tier court hierarchy and find official decisions on commercial lease termination.",
        ),
    ],
    "de": [
        (
            "German Civil Code (BGB) Lookup",
            "Look up BGB § 280 (Schadensersatz wegen Pflichtverletzung) from official German legislation portals and outline its elements.",
        ),
        (
            "BGH Case Law Search",
            "Search Federal Court of Justice (Bundesgerichtshof) decisions on general terms and conditions (AGB) under BGB § 307.",
        ),
        (
            "Verify German Legal Citation",
            "Verify official German court records for recent BVerfG decisions on informational self-determination.",
        ),
    ],
    "us": [
        (
            "US Federal Statute Lookup",
            "Search U.S. federal legislation for 17 U.S.C. § 107 (fair use) and summarize the four statutory factors.",
        ),
        (
            "US Supreme Court Precedent",
            "Search U.S. Supreme Court decisions on personal jurisdiction in internet commerce and verify the official citations.",
        ),
        (
            "Federal & State Court Tiers",
            "Explain the U.S. court hierarchy available in JurisAtlas and retrieve official appellate opinions on trade secret misappropriation.",
        ),
    ],
    "fr": [
        (
            "French Civil Code Lookup",
            "Search official French legislation (Légifrance) for Code civil Article 1240 on extracontractual liability.",
        ),
        (
            "Cour de cassation Case Law",
            "Search Cour de cassation decisions on contractual good faith (Article 1104) and verify official references.",
        ),
        (
            "French Court Hierarchy",
            "Map the French 3-tier court hierarchy and search Conseil d'État decisions on administrative proportionality.",
        ),
    ],
    "at": [
        (
            "Austrian ABGB Lookup",
            "Search official Austrian legislation (RIS) for ABGB § 1295 on damages and summarize the legal prerequisites.",
        ),
        (
            "OGH Case Law Search",
            "Search Austrian Supreme Court (OGH) decisions on warranty claims (Gewährleistung) and verify official citations.",
        ),
        (
            "Austrian Court Structure",
            "List Austria's 3-tier court hierarchy and search VfGH constitutional decisions on property rights.",
        ),
    ],
}


class ConfigParseError(ValueError):
    """Raised when an existing AI client config file cannot be parsed safely."""

    def __init__(self, path: pathlib.Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(
            f"Refused to overwrite unparseable configuration file '{path}': {detail}. "
            "Your original file was left untouched."
        )


@dataclass(frozen=True)
class ConfigTarget:
    """Describes one concrete configuration file belonging to an AI client."""

    client_key: str
    client_label: str
    path: pathlib.Path
    kind: str  # "json_mcp_servers" | "json_vscode_servers" | "json_continue_dir" | "codex_toml"
    detect_paths: tuple[pathlib.Path, ...] = ()
    is_primary: bool = True

    def is_present(self) -> bool:
        """Return True if this config file or any of its parent app indicators exist."""
        if self.path.exists():
            return True
        return any(p.exists() for p in self.detect_paths)


@dataclass
class InstallResult:
    """Structured summary returned by `install_servers` (also iterable as legacy links)."""

    links: list[tuple[str, str, str]] = field(default_factory=list)
    mode: str = "unified"
    backups_created: list[pathlib.Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    prewarm_status: str | None = None

    @property
    def unique_files(self) -> list[str]:
        return list(dict.fromkeys(cfg for _, _, cfg in self.links))

    def __iter__(self):
        return iter(self.links)

    def __len__(self) -> int:
        return len(self.links)

    def __getitem__(self, item):
        return self.links[item]


@dataclass
class UninstallResult:
    """Structured summary returned by `uninstall_servers`."""

    removed: list[tuple[str, str, str]] = field(default_factory=list)  # (client_label, server_name, cfg_path)
    backups_created: list[pathlib.Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def unique_files(self) -> list[str]:
        return list(dict.fromkeys(cfg for _, _, cfg in self.removed))


@dataclass
class ConnectionCheckResult:
    """Structured result of the non-blocking environment & connection test."""

    ok: bool
    uvx_path: str
    uvx_version: str | None = None
    uv_version: str | None = None
    server_check_ok: bool | None = None
    summary: str = ""
    details: list[str] = field(default_factory=list)


def get_all_jurisdictions() -> dict[str, str]:
    """Return built-in 42 jurisdictions plus any pluggable `EXTRA_MCP_BUNDLES`."""
    combined = dict(JURISDICTIONS)
    for code, spec in EXTRA_MCP_BUNDLES.items():
        combined[code.lower()] = str(spec.get("name", code.upper()))
    return combined


def get_regional_presets() -> dict[str, list[str]]:
    """Return regional presets filtered to active jurisdictions."""
    active_codes = set(get_all_jurisdictions().keys())
    presets: dict[str, list[str]] = {}
    for name, codes in REGIONAL_PRESETS.items():
        if name == "All Jurisdictions":
            presets[name] = sorted(active_codes)
        else:
            filtered = [c for c in codes if c in active_codes]
            if filtered:
                presets[name] = filtered
    return presets


def register_extra_bundle(code: str, spec: dict[str, Any]) -> None:
    """Register an external MCP bundle (e.g., Türkiye / `hukuk-mcp`) cleanly at runtime."""
    normalized = code.strip().lower()
    if not normalized:
        raise ValueError("Bundle code must be non-empty.")
    if "name" not in spec or "server_name" not in spec:
        raise ValueError("Bundle spec must define at least 'name' and 'server_name'.")
    EXTRA_MCP_BUNDLES[normalized] = dict(spec)


def _resolve_os_dirs(
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    appdata: pathlib.Path | None = None,
    localappdata: pathlib.Path | None = None,
) -> tuple[pathlib.Path, str, pathlib.Path, pathlib.Path]:
    home_dir = home if home is not None else pathlib.Path.home()
    sys_name = system_name if system_name is not None else platform.system()
    if appdata is not None:
        appdata_dir = appdata
    elif home is not None and sys_name == "Windows":
        appdata_dir = home_dir / "AppData" / "Roaming"
    else:
        appdata_dir = pathlib.Path(os.environ.get("APPDATA", str(home_dir / "AppData" / "Roaming")))

    if localappdata is not None:
        localappdata_dir = localappdata
    elif home is not None and sys_name == "Windows":
        localappdata_dir = home_dir / "AppData" / "Local"
    else:
        localappdata_dir = pathlib.Path(os.environ.get("LOCALAPPDATA", str(home_dir / "AppData" / "Local")))

    return home_dir, sys_name, appdata_dir, localappdata_dir


def find_claude_msix_configs(localappdata_dir: pathlib.Path) -> list[tuple[pathlib.Path, pathlib.Path]]:
    """
    Detect Windows Microsoft Store (MSIX) Claude Desktop config paths.

    Returns a list of `(config_path, package_dir)` tuples for every matching
    `%LOCALAPPDATA%\\Packages\\Claude_*` installation.
    """
    packages_dir = localappdata_dir / "Packages"
    if not packages_dir.is_dir():
        return []

    found: list[tuple[pathlib.Path, pathlib.Path]] = []
    try:
        entries = sorted(packages_dir.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []

    for pkg_dir in entries:
        if pkg_dir.is_dir() and pkg_dir.name.startswith("Claude_"):
            cfg = pkg_dir / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
            found.append((cfg, pkg_dir))
    return found


def get_client_targets(
    server_name: str = UNIFIED_SERVER_NAME,
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    appdata: pathlib.Path | None = None,
    localappdata: pathlib.Path | None = None,
) -> dict[str, list[ConfigTarget]]:
    """Return structured configuration targets for all supported AI clients."""
    home_dir, sys_name, appdata_dir, localappdata_dir = _resolve_os_dirs(
        home=home,
        system_name=system_name,
        appdata=appdata,
        localappdata=localappdata,
    )
    is_mac = sys_name == "Darwin"
    is_win = sys_name == "Windows"

    claude_targets: list[ConfigTarget] = []
    if is_win:
        msix_matches = find_claude_msix_configs(localappdata_dir)
        for msix_cfg, pkg_dir in msix_matches:
            claude_targets.append(
                ConfigTarget(
                    client_key="1",
                    client_label="Claude Desktop (Microsoft Store)",
                    path=msix_cfg,
                    kind="json_mcp_servers",
                    detect_paths=(pkg_dir, msix_cfg.parent),
                    is_primary=True,
                )
            )
        claude_classic_dir = appdata_dir / "Claude"
        claude_targets.append(
            ConfigTarget(
                client_key="1",
                client_label="Claude Desktop",
                path=claude_classic_dir / "claude_desktop_config.json",
                kind="json_mcp_servers",
                detect_paths=(claude_classic_dir,),
                is_primary=not bool(msix_matches),
            )
        )
        vscode_base = appdata_dir / "Code" / "User"
        lm_detect = (home_dir / ".lmstudio", localappdata_dir / "LM-Studio", home_dir / ".cache" / "lm-studio")
    elif is_mac:
        app_support = home_dir / "Library" / "Application Support"
        claude_classic_dir = app_support / "Claude"
        claude_targets.append(
            ConfigTarget(
                client_key="1",
                client_label="Claude Desktop",
                path=claude_classic_dir / "claude_desktop_config.json",
                kind="json_mcp_servers",
                detect_paths=(claude_classic_dir,),
                is_primary=True,
            )
        )
        vscode_base = app_support / "Code" / "User"
        lm_detect = (home_dir / ".lmstudio", app_support / "LM Studio", home_dir / ".cache" / "lm-studio")
    else:
        cfg_dir = home_dir / ".config"
        claude_classic_dir = cfg_dir / "Claude"
        claude_targets.append(
            ConfigTarget(
                client_key="1",
                client_label="Claude Desktop",
                path=claude_classic_dir / "claude_desktop_config.json",
                kind="json_mcp_servers",
                detect_paths=(claude_classic_dir,),
                is_primary=True,
            )
        )
        vscode_base = cfg_dir / "Code" / "User"
        lm_detect = (home_dir / ".lmstudio", cfg_dir / "LM Studio", home_dir / ".cache" / "lm-studio")

    # Claude Code CLI (`~/.claude.json`) as a detected sub-client of option 1
    claude_targets.append(
        ConfigTarget(
            client_key="1",
            client_label="Claude Code CLI",
            path=home_dir / ".claude.json",
            kind="json_mcp_servers",
            detect_paths=(home_dir / ".claude", home_dir / ".claude.json"),
            is_primary=False,
        )
    )

    cline_dir = vscode_base / "globalStorage" / "saoudrizwan.claude-dev"
    roo_dir = vscode_base / "globalStorage" / "rooveterinaryinc.roo-cline"

    return {
        "1": claude_targets,
        "2": [
            ConfigTarget(
                client_key="2",
                client_label="OpenAI Codex CLI",
                path=home_dir / ".codex" / "config.toml",
                kind="codex_toml",
                detect_paths=(home_dir / ".codex",),
                is_primary=True,
            ),
        ],
        "3": [
            ConfigTarget(
                client_key="3",
                client_label="Cursor",
                path=home_dir / ".cursor" / "mcp.json",
                kind="json_mcp_servers",
                detect_paths=(home_dir / ".cursor",),
                is_primary=True,
            ),
        ],
        "4": [
            ConfigTarget(
                client_key="4",
                client_label="Windsurf",
                path=home_dir / ".codeium" / "windsurf" / "mcp_config.json",
                kind="json_mcp_servers",
                detect_paths=(home_dir / ".codeium" / "windsurf",),
                is_primary=True,
            ),
        ],
        "5": [
            ConfigTarget(
                client_key="5",
                client_label="VS Code (GitHub Copilot)",
                path=vscode_base / "mcp.json",
                kind="json_vscode_servers",
                detect_paths=(vscode_base, vscode_base.parent),
                is_primary=True,
            ),
            ConfigTarget(
                client_key="5",
                client_label="VS Code (Cline)",
                path=cline_dir / "settings" / "cline_mcp_settings.json",
                kind="json_mcp_servers",
                detect_paths=(cline_dir,),
                is_primary=False,
            ),
            ConfigTarget(
                client_key="5",
                client_label="VS Code (Roo Code)",
                path=roo_dir / "settings" / "mcp_settings.json",
                kind="json_mcp_servers",
                detect_paths=(roo_dir,),
                is_primary=False,
            ),
        ],
        "6": [
            ConfigTarget(
                client_key="6",
                client_label="Google Antigravity",
                path=home_dir / ".gemini" / "antigravity" / "mcp_config.json",
                kind="json_mcp_servers",
                detect_paths=(home_dir / ".gemini" / "antigravity",),
                is_primary=True,
            ),
            ConfigTarget(
                client_key="6",
                client_label="Gemini CLI",
                path=home_dir / ".gemini" / "settings.json",
                kind="json_mcp_servers",
                detect_paths=(home_dir / ".gemini" / "settings.json",),
                is_primary=False,
            ),
            ConfigTarget(
                client_key="6",
                client_label="Google Gemini Config",
                path=home_dir / ".gemini" / "config" / "mcp_config.json",
                kind="json_mcp_servers",
                detect_paths=(home_dir / ".gemini" / "config",),
                is_primary=False,
            ),
        ],
        "7": [
            ConfigTarget(
                client_key="7",
                client_label="LM Studio",
                path=home_dir / ".lmstudio" / "mcp.json",
                kind="json_mcp_servers",
                detect_paths=lm_detect,
                is_primary=True,
            ),
        ],
        "8": [
            ConfigTarget(
                client_key="8",
                client_label="Continue.dev",
                path=home_dir / ".continue" / "mcpServers" / f"{server_name}.json",
                kind="json_continue_dir",
                detect_paths=(home_dir / ".continue",),
                is_primary=True,
            ),
        ],
    }


def get_client_paths(
    repo_name: str = UNIFIED_SERVER_NAME,
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    appdata: pathlib.Path | None = None,
    localappdata: pathlib.Path | None = None,
) -> dict[str, tuple[str, list[pathlib.Path]]]:
    """Return AI client configuration labels and file paths for the given OS."""
    label_by_key = {k: lbl for k, lbl, _ in CLIENT_SPECS}
    targets = get_client_targets(
        server_name=repo_name,
        home=home,
        system_name=system_name,
        appdata=appdata,
        localappdata=localappdata,
    )
    return {
        key: (label_by_key[key], [t.path for t in target_list])
        for key, target_list in targets.items()
    }


def detect_installed_clients(
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    appdata: pathlib.Path | None = None,
    localappdata: pathlib.Path | None = None,
    check_system_apps: bool | None = None,
) -> dict[str, bool]:
    """
    Detect which AI applications appear to be installed on this machine.

    When `home` is passed (e.g. during isolated tests), host-level checks like
    `/Applications` or `PATH` are disabled unless `check_system_apps=True`.
    """
    if check_system_apps is None:
        check_system_apps = home is None

    home_dir, sys_name, appdata_dir, localappdata_dir = _resolve_os_dirs(
        home=home,
        system_name=system_name,
        appdata=appdata,
        localappdata=localappdata,
    )
    targets_by_key = get_client_targets(
        home=home_dir,
        system_name=sys_name,
        appdata=appdata_dir,
        localappdata=localappdata_dir,
    )

    detected: dict[str, bool] = {}
    for key, target_list in targets_by_key.items():
        detected[key] = any(t.is_present() for t in target_list)

    if check_system_apps:
        if sys_name == "Darwin":
            mac_apps = {
                "1": [pathlib.Path("/Applications/Claude.app")],
                "3": [pathlib.Path("/Applications/Cursor.app")],
                "4": [pathlib.Path("/Applications/Windsurf.app")],
                "5": [pathlib.Path("/Applications/Visual Studio Code.app")],
                "7": [pathlib.Path("/Applications/LM Studio.app")],
            }
            for key, app_paths in mac_apps.items():
                if not detected[key] and any(p.exists() for p in app_paths):
                    detected[key] = True
        elif sys_name == "Windows":
            win_programs = {
                "1": [localappdata_dir / "AnthropicClaude"],
                "3": [localappdata_dir / "Programs" / "cursor"],
                "4": [localappdata_dir / "Programs" / "Windsurf"],
                "5": [localappdata_dir / "Programs" / "Microsoft VS Code"],
                "7": [localappdata_dir / "LM-Studio"],
            }
            for key, dirs in win_programs.items():
                if not detected[key] and any(p.exists() for p in dirs):
                    detected[key] = True

        cli_bins = {
            "1": ("claude",),
            "2": ("codex",),
            "3": ("cursor",),
            "4": ("windsurf",),
            "5": ("code",),
            "6": ("gemini",),
        }
        for key, cmds in cli_bins.items():
            if not detected[key] and any(shutil.which(cmd) for cmd in cmds):
                detected[key] = True

    return detected


def resolve_uvx_command(
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    localappdata: pathlib.Path | None = None,
) -> str:
    """Resolve an absolute `uvx` executable path so GUI apps work without shell PATH."""
    if home is None:
        found = shutil.which("uvx")
        if found:
            return found

    home_dir, sys_name, _appdata, local_app = _resolve_os_dirs(
        home=home,
        system_name=system_name,
        localappdata=localappdata,
    )
    if sys_name == "Windows":
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

    if home is not None:
        found = shutil.which("uvx")
        if found:
            return found
    return "uvx"


def parse_country_selection(raw_countries: str) -> list[str]:
    """
    Parse user country input into a sorted list of jurisdiction codes.

    Supports exact codes, `<cc>-legal-mcp` repo names, exact country names,
    regional preset names (e.g. `dach`, `nordics`, `common-law`), `all` aliases,
    and prefix/word-boundary name matches of at least 3 characters (never
    matching 2-char unknown codes like `tr` to Austria/Australia).
    """
    text = raw_countries.strip().lower()
    if not text:
        return []

    jurisdictions = get_all_jurisdictions()
    presets = get_regional_presets()
    tokens = [t.strip() for t in text.replace(";", ",").split(",") if t.strip()]

    if any(tok in ALL_COUNTRY_TOKENS for tok in tokens):
        return sorted(jurisdictions.keys())

    selected_codes: list[str] = []
    bundle_aliases: dict[str, str] = {}
    for b_code, b_spec in EXTRA_MCP_BUNDLES.items():
        b_norm = b_code.lower()
        srv = str(b_spec.get("server_name", "")).strip().lower()
        if srv:
            bundle_aliases[srv] = b_norm
        for alias in b_spec.get("aliases", []):
            bundle_aliases[str(alias).strip().lower()] = b_norm

    for tok in tokens:
        if tok in jurisdictions:
            selected_codes.append(tok)
            continue

        if tok in bundle_aliases:
            selected_codes.append(bundle_aliases[tok])
            continue

        if tok in PRESET_ALIASES:
            preset_key = PRESET_ALIASES[tok]
            selected_codes.extend(presets.get(preset_key, []))
            continue

        matched_preset = next((codes for pname, codes in presets.items() if pname.lower() == tok), None)
        if matched_preset is not None:
            selected_codes.extend(matched_preset)
            continue

        if tok.endswith("-legal-mcp") and tok[:-10] in jurisdictions:
            selected_codes.append(tok[:-10])
            continue

        # Allow space-separated country codes such as "uk de ba"
        parts = tok.split()
        if len(parts) > 1 and all(p in jurisdictions for p in parts):
            selected_codes.extend(parts)
            continue

        exact_name_matches = [code for code, cname in jurisdictions.items() if tok == cname.lower()]
        if exact_name_matches:
            selected_codes.extend(exact_name_matches)
            continue

        # Safe prefix / word-boundary matching only for queries >= 3 chars
        if len(tok) >= 3:
            for code, cname in jurisdictions.items():
                lower_name = cname.lower()
                words = re.findall(r"[a-z\u00c0-\u024f]+", lower_name)
                if lower_name.startswith(tok) or any(word.startswith(tok) for word in words):
                    selected_codes.append(code)

    return sorted(set(selected_codes))


def parse_client_selection(
    raw_clients: str,
    detected_keys: list[str] | None = None,
) -> list[str]:
    """Parse user AI application selection into ordered client keys ('1'..'8')."""
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

    chosen: list[str] = []
    for tok in tokens:
        if tok in {"d", "detected", "auto"} and detected_keys:
            chosen.extend(k for k in detected_keys if k in valid_keys)
        elif tok in valid_keys:
            chosen.append(tok)
        elif tok in CLIENT_ALIASES:
            chosen.append(CLIENT_ALIASES[tok])

    return list(dict.fromkeys(chosen))


def build_uvx_server_entry(
    repo_name: str,
    uvx_cmd: str,
    package_url: str | None = None,
    entrypoint: str | None = None,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the MCP server entry dictionary for a JurisAtlas repository."""
    url = package_url or f"https://github.com/jurisatlas/{repo_name}/archive/refs/heads/main.zip"
    entry_cmd = entrypoint or repo_name
    args = ["--from", url, entry_cmd]
    if extra_args:
        args.extend(extra_args)
    env_map = {"PYTHONIOENCODING": "utf-8"}
    if env:
        env_map.update(env)
    return {
        "command": uvx_cmd,
        "args": args,
        "env": env_map,
    }


def build_unified_server_entry(
    selected_codes: list[str],
    uvx_cmd: str,
    all_base_codes: set[str] | None = None,
) -> dict[str, Any]:
    """Build ONE unified `jurisatlas-mcp` server entry configured with `--countries`."""
    base_set = all_base_codes if all_base_codes is not None else set(JURISDICTIONS.keys())
    clean_codes = sorted({c.lower() for c in selected_codes})
    countries_arg = "all" if set(clean_codes) >= base_set and len(clean_codes) == len(base_set) else ",".join(clean_codes)
    return build_uvx_server_entry(
        repo_name=UNIFIED_SERVER_NAME,
        uvx_cmd=uvx_cmd,
        package_url=UNIFIED_PACKAGE_URL,
        entrypoint=UNIFIED_SERVER_NAME,
        extra_args=["--countries", countries_arg],
    )


def build_server_entries_for_selection(
    selected_codes: list[str],
    uvx_cmd: str,
    mode: str = "unified",
) -> dict[str, dict[str, Any]]:
    """
    Build the server name -> entry mapping for the selected jurisdictions and mode.

    - In `unified` mode (default), base JurisAtlas jurisdictions collapse into ONE
      `jurisatlas-mcp` entry with `--countries <codes|all>`.
    - In `standalone` mode, each base jurisdiction becomes `<cc>-legal-mcp`.
    - Any code registered in `EXTRA_MCP_BUNDLES` produces its own configured entry
      (or merges into unified `--countries` if `unified_supported=True`).
    """
    if mode not in {"unified", "standalone"}:
        raise ValueError(f"Unsupported install mode: {mode!r}. Expected 'unified' or 'standalone'.")

    entries: dict[str, dict[str, Any]] = {}
    unified_codes: list[str] = []
    standalone_base_codes: list[str] = []

    for raw_code in sorted(set(c.lower() for c in selected_codes)):
        if raw_code in EXTRA_MCP_BUNDLES:
            bundle = EXTRA_MCP_BUNDLES[raw_code]
            if mode == "unified" and bundle.get("unified_supported"):
                unified_codes.append(raw_code)
            else:
                srv_name = str(bundle["server_name"])
                entries[srv_name] = build_uvx_server_entry(
                    repo_name=srv_name,
                    uvx_cmd=uvx_cmd,
                    package_url=str(bundle.get("package_url", "")) or None,
                    entrypoint=str(bundle.get("entrypoint", srv_name)),
                    extra_args=list(bundle.get("extra_args", [])),
                    env=dict(bundle.get("env", {})),
                )
        elif raw_code in JURISDICTIONS:
            if mode == "unified":
                unified_codes.append(raw_code)
            else:
                standalone_base_codes.append(raw_code)
        else:
            raise ValueError(f"Unknown jurisdiction code: {raw_code!r}")

    if unified_codes:
        unified_all_set = set(JURISDICTIONS.keys()) | {
            code for code, spec in EXTRA_MCP_BUNDLES.items() if spec.get("unified_supported")
        }
        entries[UNIFIED_SERVER_NAME] = build_unified_server_entry(
            unified_codes,
            uvx_cmd=uvx_cmd,
            all_base_codes=unified_all_set,
        )

    for code in standalone_base_codes:
        repo = f"{code}-legal-mcp"
        entries[repo] = build_uvx_server_entry(repo, uvx_cmd)

    return entries


def strip_jsonc(text: str) -> str:
    """
    Strip JSONC comments (`//` and `/* ... */`) and trailing commas outside strings.

    Preserves string literals (including URLs like `https://...` and escaped quotes)
    verbatim.
    """
    if text.startswith("\ufeff"):
        text = text[1:]

    # Pass 1: strip // and /* ... */ comments outside strings
    no_comments: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False

    while i < n:
        ch = text[i]
        if in_string:
            no_comments.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            no_comments.append(ch)
            i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in ("\r", "\n"):
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = i + 2 if i + 1 < n else n
        else:
            no_comments.append(ch)
            i += 1

    cleaned = "".join(no_comments)

    # Pass 2: remove trailing commas before `}` or `]` outside strings
    result: list[str] = []
    i = 0
    n = len(cleaned)
    in_string = False
    escape = False

    while i < n:
        ch = cleaned[i]
        if in_string:
            result.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
        elif ch == ",":
            j = i + 1
            while j < n and cleaned[j] in (" ", "\t", "\r", "\n"):
                j += 1
            if j < n and cleaned[j] in ("}", "]"):
                # Skip trailing comma
                i += 1
                continue
            result.append(ch)
            i += 1
        else:
            result.append(ch)
            i += 1

    return "".join(result)


def parse_jsonc_object(cfg_path: pathlib.Path) -> dict[str, Any]:
    """Read and parse a UTF-8/UTF-8-BOM JSON/JSONC file into a dict; never silently wipe."""
    if not cfg_path.exists() or cfg_path.stat().st_size == 0:
        return {}

    raw_text = cfg_path.read_text(encoding="utf-8-sig")
    if not raw_text.strip():
        return {}

    sanitized = strip_jsonc(raw_text)
    try:
        loaded = json.loads(sanitized)
    except json.JSONDecodeError as exc:
        raise ConfigParseError(cfg_path, f"invalid JSON ({exc})") from exc

    if not isinstance(loaded, dict):
        raise ConfigParseError(cfg_path, f"expected a top-level JSON object, got {type(loaded).__name__}")

    return loaded


def create_timestamped_backup(cfg_path: pathlib.Path) -> pathlib.Path | None:
    """Create a unique `*.bak.YYYYMMDD-HHMMSS` backup copy before modifying `cfg_path`."""
    if not cfg_path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = cfg_path.with_name(f"{cfg_path.name}.bak.{stamp}")
    counter = 1
    while backup_path.exists():
        backup_path = cfg_path.with_name(f"{cfg_path.name}.bak.{stamp}-{counter}")
        counter += 1
    shutil.copy2(cfg_path, backup_path)
    return backup_path


def atomic_write_text(cfg_path: pathlib.Path, content: str, encoding: str = "utf-8") -> None:
    """Write `content` atomically to `cfg_path` via a same-directory tempfile + `os.replace`."""
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=cfg_path.parent,
            prefix=f".{cfg_path.name}.",
            suffix=".tmp",
            delete=False,
            newline="\n",
        ) as handle:
            tmp_path = pathlib.Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, cfg_path)
    except Exception:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def upsert_json_mcp_file(
    cfg_path: pathlib.Path,
    entries_by_repo: dict[str, dict[str, Any]],
    dry_run: bool = False,
    root_key: str = "mcpServers",
    include_type_stdio: bool = False,
) -> pathlib.Path | None:
    """
    Safely insert or update MCP server entries in a JSON/JSONC configuration file.

    - Reads with `utf-8-sig` and tolerates JSONC comments & trailing commas.
    - Raises `ConfigParseError` without modifying the original file if unparseable.
    - Creates a timestamped backup (`*.bak.YYYYMMDD-HHMMSS`) before every write.
    - Writes atomically via tempfile + `os.replace`.
    """
    data = parse_jsonc_object(cfg_path)

    existing_bucket = data.get(root_key)
    if existing_bucket is None:
        servers_map: dict[str, Any] = {}
        data[root_key] = servers_map
    elif isinstance(existing_bucket, dict):
        servers_map = existing_bucket
    else:
        raise ConfigParseError(
            cfg_path,
            f"expected '{root_key}' to be a JSON object, got {type(existing_bucket).__name__}",
        )

    for server_name, entry in entries_by_repo.items():
        formatted = dict(entry)
        if include_type_stdio:
            formatted = {"type": "stdio", **formatted}
        servers_map[server_name] = formatted

    backup_path: pathlib.Path | None = None
    if not dry_run:
        backup_path = create_timestamped_backup(cfg_path)
        atomic_write_text(cfg_path, json.dumps(data, indent=2) + "\n")
    return backup_path


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_codex_toml_block(server_name: str, entry: dict[str, Any]) -> str:
    cmd = _toml_escape(str(entry["command"]))
    args_list = [f'"{_toml_escape(str(a))}"' for a in entry.get("args", [])]
    env_dict = dict(entry.get("env", {}))
    if "PYTHONIOENCODING" not in env_dict:
        env_dict["PYTHONIOENCODING"] = "utf-8"
    env_pairs = ", ".join(f'{k} = "{_toml_escape(str(v))}"' for k, v in env_dict.items())
    return (
        f"[mcp_servers.{server_name}]\n"
        f'command = "{cmd}"\n'
        f'args = [{", ".join(args_list)}]\n'
        f"env = {{ {env_pairs} }}\n"
    )


def upsert_codex_toml(
    codex_toml: pathlib.Path,
    repos_or_entries: list[str] | dict[str, dict[str, Any]],
    uvx_cmd: str | None = None,
    dry_run: bool = False,
) -> pathlib.Path | None:
    """
    Safely insert or update `[mcp_servers.<name>]` sections in `~/.codex/config.toml`.

    Uses a lambda replacement in `re.sub` so Windows backslashes never corrupt on
    subsequent runs, includes `env = { PYTHONIOENCODING = "utf-8" }`, validates
    TOML syntax with `tomllib.loads`, creates a timestamped backup, and writes atomically.
    """
    if isinstance(repos_or_entries, list):
        resolved_uvx = uvx_cmd or "uvx"
        entries: dict[str, dict[str, Any]] = {
            repo_name: build_uvx_server_entry(repo_name, resolved_uvx)
            for repo_name in repos_or_entries
        }
    else:
        entries = repos_or_entries

    existing = ""
    if codex_toml.exists() and codex_toml.stat().st_size > 0:
        existing = codex_toml.read_text(encoding="utf-8-sig")
        if existing.strip():
            try:
                tomllib.loads(existing)
            except tomllib.TOMLDecodeError as exc:
                raise ConfigParseError(codex_toml, f"invalid TOML ({exc})") from exc

    updated = existing
    for server_name, entry in entries.items():
        block = _format_codex_toml_block(server_name, entry)
        pattern = rf"(?ms)^\[mcp_servers\.{re.escape(server_name)}(?:\.[^\]]+)?\].*?(?=^\[|\Z)"
        if re.search(pattern, updated):
            # Replace first match with new block via lambda (backslash-safe!), strip any duplicates
            first_replaced = False

            def _repl(_match: re.Match[str], b: str = block) -> str:
                nonlocal first_replaced
                if not first_replaced:
                    first_replaced = True
                    return b + "\n"
                return ""

            updated = re.sub(pattern, _repl, updated)
        else:
            updated = (updated.rstrip() + "\n\n" + block) if updated.strip() else block

    updated = re.sub(r"\n{3,}", "\n\n", updated).strip() + "\n"
    # Validate generated TOML before touching disk
    try:
        tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigParseError(codex_toml, f"generated invalid TOML ({exc})") from exc

    backup_path: pathlib.Path | None = None
    if not dry_run:
        backup_path = create_timestamped_backup(codex_toml)
        atomic_write_text(codex_toml, updated)
    return backup_path


def _is_jurisatlas_server_key(server_name: str, entry: Any = None) -> bool:
    """Return True if `server_name` (or its entry args) belongs to JurisAtlas."""
    if server_name == UNIFIED_SERVER_NAME:
        return True
    all_codes = set(get_all_jurisdictions().keys())
    if server_name.endswith("-legal-mcp") and server_name[:-10] in all_codes:
        return True
    bundle_server_names = {str(spec["server_name"]) for spec in EXTRA_MCP_BUNDLES.values() if "server_name" in spec}
    if server_name in bundle_server_names:
        return True
    if isinstance(entry, dict):
        args = entry.get("args")
        if isinstance(args, list):
            if any(isinstance(a, str) and "github.com/jurisatlas/" in a.lower() for a in args):
                return True
    return False


def remove_from_json_mcp_file(
    cfg_path: pathlib.Path,
    dry_run: bool = False,
    root_key: str = "mcpServers",
) -> tuple[list[str], pathlib.Path | None]:
    """Remove all JurisAtlas server entries from a JSON/JSONC config while preserving others."""
    if not cfg_path.exists() or cfg_path.stat().st_size == 0:
        return [], None

    data = parse_jsonc_object(cfg_path)
    bucket = data.get(root_key)
    if not isinstance(bucket, dict):
        return [], None

    to_remove = [name for name, entry in bucket.items() if _is_jurisatlas_server_key(name, entry)]
    if not to_remove:
        return [], None

    for name in to_remove:
        del bucket[name]

    backup_path: pathlib.Path | None = None
    if not dry_run:
        backup_path = create_timestamped_backup(cfg_path)
        atomic_write_text(cfg_path, json.dumps(data, indent=2) + "\n")
    return sorted(to_remove), backup_path


def remove_from_codex_toml(
    codex_toml: pathlib.Path,
    dry_run: bool = False,
) -> tuple[list[str], pathlib.Path | None]:
    """Remove all JurisAtlas `[mcp_servers.<name>]` sections from `~/.codex/config.toml`."""
    if not codex_toml.exists() or codex_toml.stat().st_size == 0:
        return [], None

    existing = codex_toml.read_text(encoding="utf-8-sig")
    if not existing.strip():
        return [], None

    try:
        parsed = tomllib.loads(existing)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigParseError(codex_toml, f"invalid TOML ({exc})") from exc

    mcp_servers = parsed.get("mcp_servers")
    if not isinstance(mcp_servers, dict):
        return [], None

    to_remove = [name for name, entry in mcp_servers.items() if _is_jurisatlas_server_key(name, entry)]
    if not to_remove:
        return [], None

    updated = existing
    for server_name in to_remove:
        pattern = rf"(?ms)^\[mcp_servers\.{re.escape(server_name)}(?:\.[^\]]+)?\].*?(?=^\[|\Z)"
        updated = re.sub(pattern, "", updated)

    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    if updated:
        updated += "\n"
        tomllib.loads(updated)

    backup_path: pathlib.Path | None = None
    if not dry_run:
        backup_path = create_timestamped_backup(codex_toml)
        atomic_write_text(codex_toml, updated)
    return sorted(to_remove), backup_path


def _select_active_targets(
    targets: list[ConfigTarget],
    only_existing_subclients: bool = True,
) -> list[ConfigTarget]:
    """
    Choose which config targets inside one client group to modify.

    When `only_existing_subclients=True`:
      - If at least one target in the group is already present on disk, update ONLY
        the present targets (never creating empty folders for uninstalled extensions
        like Cline/Roo or unused sub-clients).
      - If none are present yet (e.g. user selected an app before first launch),
        update only the primary target(s).
    """
    if not only_existing_subclients:
        return list(targets)

    present = [t for t in targets if t.is_present()]
    if present:
        return present
    primaries = [t for t in targets if t.is_primary]
    return primaries if primaries else list(targets[:1])


def install_servers(
    selected_codes: list[str],
    chosen_keys: list[str],
    uvx_cmd: str | None = None,
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    appdata: pathlib.Path | None = None,
    localappdata: pathlib.Path | None = None,
    dry_run: bool = False,
    mode: str = "unified",
    only_existing_subclients: bool = True,
    prewarm: bool = False,
    progress_cb: Callable[[int, str], None] | None = None,
    lang: str = "en",
) -> InstallResult:
    """
    Configure selected JurisAtlas server(s) in selected AI client configuration files.

    Returns an `InstallResult` (also iterable as `(label, server_name, cfg_path)` tuples).
    """
    if not selected_codes:
        raise ValueError("At least one jurisdiction must be selected.")
    if not chosen_keys:
        raise ValueError("At least one AI application must be selected.")

    home_dir, sys_name, appdata_dir, localappdata_dir = _resolve_os_dirs(
        home=home,
        system_name=system_name,
        appdata=appdata,
        localappdata=localappdata,
    )
    resolved_uvx = uvx_cmd or resolve_uvx_command(
        home=home_dir,
        system_name=sys_name,
        localappdata=localappdata_dir,
    )

    result = InstallResult(mode=mode)
    if mode == "standalone" and len(selected_codes) > STANDALONE_WARNING_THRESHOLD:
        result.warnings.append(
            f"Standalone mode with {len(selected_codes)} countries creates {len(selected_codes)} "
            "separate server processes. Unified mode is recommended for >5 countries."
        )

    if progress_cb:
        mode_desc = t(lang, "mode_unified") if mode == "unified" else t(lang, "mode_standalone")
        progress_cb(10, t(lang, "cli_progress_preparing", mode=mode_desc))

    server_entries = build_server_entries_for_selection(selected_codes, resolved_uvx, mode=mode)

    targets_by_key = get_client_targets(
        server_name=UNIFIED_SERVER_NAME,
        home=home_dir,
        system_name=sys_name,
        appdata=appdata_dir,
        localappdata=localappdata_dir,
    )

    # Plan writes grouped by target path so each config file is read/backed up/written once.
    json_plans: dict[pathlib.Path, tuple[ConfigTarget, dict[str, dict[str, Any]]]] = {}
    codex_targets: dict[pathlib.Path, ConfigTarget] = {}

    for key in chosen_keys:
        if key not in targets_by_key:
            continue
        active_targets = _select_active_targets(
            targets_by_key[key],
            only_existing_subclients=only_existing_subclients,
        )
        for target in active_targets:
            if target.kind == "codex_toml":
                codex_targets[target.path] = target
                for srv_name in server_entries:
                    result.links.append((target.client_label, srv_name, str(target.path)))
            elif target.kind == "json_continue_dir":
                continue_dir = target.path.parent
                for srv_name, entry in server_entries.items():
                    srv_path = continue_dir / f"{srv_name}.json"
                    per_srv_target = ConfigTarget(
                        client_key=target.client_key,
                        client_label=target.client_label,
                        path=srv_path,
                        kind="json_mcp_servers",
                        detect_paths=target.detect_paths,
                        is_primary=target.is_primary,
                    )
                    json_plans.setdefault(srv_path, (per_srv_target, {}))[1][srv_name] = entry
                    result.links.append((target.client_label, srv_name, str(srv_path)))
            else:
                existing_plan = json_plans.setdefault(target.path, (target, {}))
                for srv_name, entry in server_entries.items():
                    existing_plan[1][srv_name] = entry
                    result.links.append((target.client_label, srv_name, str(target.path)))

    total_ops = len(json_plans) + len(codex_targets) + (1 if prewarm and not dry_run else 0)
    completed = 0

    for cfg_path, (target, entries) in json_plans.items():
        is_vscode = target.kind == "json_vscode_servers"
        backup = upsert_json_mcp_file(
            cfg_path,
            entries,
            dry_run=dry_run,
            root_key="servers" if is_vscode else "mcpServers",
            include_type_stdio=is_vscode,
        )
        if backup is not None:
            result.backups_created.append(backup)
        completed += 1
        if progress_cb and total_ops > 0:
            pct = 15 + int((completed / total_ops) * 80)
            prefix = f"{t(lang, 'dry_run_tag')} " if dry_run else ""
            progress_cb(pct, f"{prefix}{t(lang, 'cli_progress_configured', label=target.client_label, filename=cfg_path.name)}")

    for codex_path, target in codex_targets.items():
        backup = upsert_codex_toml(codex_path, server_entries, dry_run=dry_run)
        if backup is not None:
            result.backups_created.append(backup)
        completed += 1
        if progress_cb and total_ops > 0:
            pct = 15 + int((completed / total_ops) * 80)
            prefix = f"{t(lang, 'dry_run_tag')} " if dry_run else ""
            progress_cb(pct, f"{prefix}{t(lang, 'cli_progress_configured', label=target.client_label, filename=codex_path.name)}")

    if prewarm and not dry_run:
        if progress_cb:
            progress_cb(95, t(lang, "cli_progress_prewarm"))
        check = test_connection(
            uvx_cmd=resolved_uvx,
            home=home_dir,
            system_name=sys_name,
            mode=mode,
            check_server=True,
            timeout=25,
        )
        result.prewarm_status = check.summary

    if progress_cb:
        done_msg = t(lang, "status_ready_dry") if dry_run else t(lang, "done_heading")
        progress_cb(100, done_msg)

    return result


def uninstall_servers(
    chosen_keys: list[str] | None = None,
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    appdata: pathlib.Path | None = None,
    localappdata: pathlib.Path | None = None,
    dry_run: bool = False,
    progress_cb: Callable[[int, str], None] | None = None,
) -> UninstallResult:
    """
    Cleanly remove all JurisAtlas MCP server entries from AI client config files.

    Never touches non-JurisAtlas MCP servers or other settings. Creates a
    timestamped backup before every modified file.
    """
    home_dir, sys_name, appdata_dir, localappdata_dir = _resolve_os_dirs(
        home=home,
        system_name=system_name,
        appdata=appdata,
        localappdata=localappdata,
    )
    targets_by_key = get_client_targets(
        home=home_dir,
        system_name=sys_name,
        appdata=appdata_dir,
        localappdata=localappdata_dir,
    )
    keys_to_scan = chosen_keys if chosen_keys is not None else list(targets_by_key.keys())

    all_targets: list[ConfigTarget] = []
    seen_paths: set[pathlib.Path] = set()
    for key in keys_to_scan:
        for target in targets_by_key.get(key, []):
            if target.kind == "json_continue_dir":
                continue_dir = target.path.parent
                if continue_dir.is_dir():
                    for cfg_file in sorted(continue_dir.glob("*.json")):
                        if cfg_file not in seen_paths:
                            seen_paths.add(cfg_file)
                            all_targets.append(
                                ConfigTarget(
                                    client_key=target.client_key,
                                    client_label=target.client_label,
                                    path=cfg_file,
                                    kind="json_continue_file",
                                    detect_paths=target.detect_paths,
                                    is_primary=target.is_primary,
                                )
                            )
            elif target.path not in seen_paths:
                seen_paths.add(target.path)
                all_targets.append(target)

    result = UninstallResult()
    total = max(len(all_targets), 1)
    for idx, target in enumerate(all_targets, start=1):
        try:
            if target.kind == "codex_toml":
                removed_names, backup = remove_from_codex_toml(target.path, dry_run=dry_run)
            elif target.kind == "json_vscode_servers":
                removed_names, backup = remove_from_json_mcp_file(
                    target.path, dry_run=dry_run, root_key="servers"
                )
                # Also clean up any legacy v1.x "mcpServers" JurisAtlas entries in Code/User/mcp.json
                legacy_removed, legacy_backup = remove_from_json_mcp_file(
                    target.path, dry_run=dry_run, root_key="mcpServers"
                )
                removed_names = sorted(set(removed_names) | set(legacy_removed))
                if backup is None:
                    backup = legacy_backup
            elif target.kind == "json_continue_file":
                removed_names, backup = _remove_continue_file(target.path, dry_run=dry_run)
            else:
                removed_names, backup = remove_from_json_mcp_file(
                    target.path, dry_run=dry_run, root_key="mcpServers"
                )

            for name in removed_names:
                result.removed.append((target.client_label, name, str(target.path)))
            if backup is not None:
                result.backups_created.append(backup)
        except ConfigParseError as exc:
            result.errors.append(str(exc))

        if progress_cb:
            pct = int((idx / total) * 100)
            progress_cb(pct, f"Checked {target.client_label} ({target.path.name})")

    return result


def _remove_continue_file(
    cfg_path: pathlib.Path,
    dry_run: bool = False,
) -> tuple[list[str], pathlib.Path | None]:
    """Remove JurisAtlas entries from a Continue.dev mcpServers JSON file."""
    if not cfg_path.exists() or cfg_path.stat().st_size == 0:
        return [], None

    data = parse_jsonc_object(cfg_path)
    bucket = data.get("mcpServers")
    if not isinstance(bucket, dict):
        return [], None

    to_remove = [name for name, entry in bucket.items() if _is_jurisatlas_server_key(name, entry)]
    if not to_remove:
        return [], None

    for name in to_remove:
        del bucket[name]

    backup_path: pathlib.Path | None = None
    if not dry_run:
        backup_path = create_timestamped_backup(cfg_path)
        if not bucket and len(data) == 1:
            cfg_path.unlink()
        else:
            atomic_write_text(cfg_path, json.dumps(data, indent=2) + "\n")
    return sorted(to_remove), backup_path


def test_connection(
    uvx_cmd: str | None = None,
    home: pathlib.Path | None = None,
    system_name: str | None = None,
    mode: str = "unified",
    check_server: bool = False,
    timeout: int = 15,
) -> ConnectionCheckResult:
    """
    Verify `uv`/`uvx` toolchain availability and optionally test server startup.

    Safe to run from a background thread (no GUI calls inside).
    """
    resolved_uvx = uvx_cmd or resolve_uvx_command(home=home, system_name=system_name)
    details: list[str] = []
    uvx_version: str | None = None
    uv_version: str | None = None

    try:
        proc = subprocess.run(
            [resolved_uvx, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode == 0:
            uvx_version = (proc.stdout or proc.stderr).strip()
            details.append(f"uvx ready: {uvx_version} ({resolved_uvx})")
        else:
            err = (proc.stderr or proc.stdout).strip() or f"exit code {proc.returncode}"
            details.append(f"uvx returned an error: {err}")
            return ConnectionCheckResult(
                ok=False,
                uvx_path=resolved_uvx,
                summary=f"uvx check failed ({err})",
                details=details,
            )
    except FileNotFoundError:
        details.append(f"uvx executable not found at '{resolved_uvx}'. Install uv from https://astral.sh/uv")
        return ConnectionCheckResult(
            ok=False,
            uvx_path=resolved_uvx,
            summary="uvx is not installed or not on PATH.",
            details=details,
        )
    except subprocess.TimeoutExpired:
        details.append(f"uvx --version timed out after {timeout}s.")
        return ConnectionCheckResult(
            ok=False,
            uvx_path=resolved_uvx,
            summary="uvx version check timed out.",
            details=details,
        )
    except OSError as exc:
        details.append(f"Could not execute uvx: {exc}")
        return ConnectionCheckResult(
            ok=False,
            uvx_path=resolved_uvx,
            summary=f"Could not run uvx: {exc}",
            details=details,
        )

    # Check companion `uv` binary if present
    uv_bin = shutil.which("uv")
    if uv_bin:
        try:
            uv_proc = subprocess.run(
                [uv_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=min(timeout, 10),
                check=False,
            )
            if uv_proc.returncode == 0:
                uv_version = (uv_proc.stdout or uv_proc.stderr).strip()
                details.append(f"uv ready: {uv_version}")
        except Exception:
            pass

    server_ok: bool | None = None
    if check_server:
        pkg_url = (
            UNIFIED_PACKAGE_URL
            if mode == "unified"
            else "https://github.com/jurisatlas/uk-legal-mcp/archive/refs/heads/main.zip"
        )
        entrypoint = UNIFIED_SERVER_NAME if mode == "unified" else "uk-legal-mcp"
        try:
            srv_proc = subprocess.run(
                [resolved_uvx, "--from", pkg_url, entrypoint, "--help"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if srv_proc.returncode == 0:
                server_ok = True
                details.append(f"Server startup probe succeeded ({entrypoint}).")
            else:
                server_ok = False
                err_tail = ((srv_proc.stderr or srv_proc.stdout).strip().splitlines() or ["no output"])[-1]
                details.append(
                    f"Server probe did not complete yet ({err_tail}). "
                    "Your local uvx runtime is healthy; once the package is reachable online, your AI client will launch it automatically."
                )
        except subprocess.TimeoutExpired:
            server_ok = False
            details.append(
                f"Server pre-warm timed out after {timeout}s (network or initial package download may still be slow)."
            )
        except OSError as exc:
            server_ok = False
            details.append(f"Server probe failed: {exc}")

    summary = (
        f"Ready! {uvx_version} is working."
        if server_ok is not False
        else f"Toolchain ready ({uvx_version}); remote server pre-warm skipped/unavailable."
    )
    return ConnectionCheckResult(
        ok=True,
        uvx_path=resolved_uvx,
        uvx_version=uvx_version,
        uv_version=uv_version,
        server_check_ok=server_ok,
        summary=summary,
        details=details,
    )


def get_starter_prompts(selected_codes: list[str]) -> list[tuple[str, str]]:
    """Return 3 balanced copy-paste legal prompts for the user's selected jurisdictions."""
    jurisdictions = get_all_jurisdictions()
    clean_codes = [c.lower() for c in selected_codes if c.lower() in jurisdictions]
    prompts: list[tuple[str, str]] = []
    seen_titles: set[str] = set()

    # For "all" or large multi-country selections (>5), show universal US / EU / NZ examples
    if len(clean_codes) > 5:
        universal_order = [c for c in ("us", "eu", "nz") if c in clean_codes]
        for code in universal_order:
            for title, text in JURISDICTION_SAMPLE_PROMPTS.get(code, []):
                if title not in seen_titles and len(prompts) < 3:
                    prompts.append((title, text))
                    seen_titles.add(title)
                    break
    else:
        # Spread fairly across chosen countries (at most 1 per country unless only 1 country chosen)
        for code in clean_codes:
            if code in EXTRA_MCP_BUNDLES:
                for item in EXTRA_MCP_BUNDLES[code].get("starter_prompts", []):
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        title, text = str(item[0]), str(item[1])
                        if title not in seen_titles and len(prompts) < 3:
                            prompts.append((title, text))
                            seen_titles.add(title)
                            if len(clean_codes) > 1:
                                break
            if code in JURISDICTION_SAMPLE_PROMPTS:
                for title, text in JURISDICTION_SAMPLE_PROMPTS[code]:
                    if title not in seen_titles and len(prompts) < 3:
                        prompts.append((title, text))
                        seen_titles.add(title)
                        break

    # If user picked a single known country, fill remaining slots with that country's other prompts
    if len(prompts) < 3 and len(clean_codes) == 1 and clean_codes[0] in JURISDICTION_SAMPLE_PROMPTS:
        for title, text in JURISDICTION_SAMPLE_PROMPTS[clean_codes[0]]:
            if title not in seen_titles and len(prompts) < 3:
                prompts.append((title, text))
                seen_titles.add(title)

    # Dynamic fallback tailored to the actual chosen country name(s)
    primary_name = jurisdictions[clean_codes[0]] if clean_codes else "European Union & ECHR"
    secondary_name = jurisdictions[clean_codes[1]] if len(clean_codes) > 1 else primary_name

    fallbacks = [
        (
            f"Search Official {primary_name} Legislation",
            f"Using JurisAtlas, search official {primary_name} legislation for statutory rules on contract breach and list the exact article citations and official URLs.",
        ),
        (
            f"Find Tiered Court Precedents ({secondary_name})",
            f"Using JurisAtlas, map the 3-tier court hierarchy of {secondary_name} and find recent Supreme Court decisions on civil liability.",
        ),
        (
            "Verify Legal Citations Before Filing",
            f"Check these citations against official {primary_name} legal portals using JurisAtlas and flag any citation that cannot be verified as an official record.",
        ),
    ]
    for title, text in fallbacks:
        if len(prompts) >= 3:
            break
        if title not in seen_titles:
            prompts.append((title, text))
            seen_titles.add(title)

    return prompts[:3]


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


def run_gui(
    dry_run: bool = False,
    initial_countries: list[str] | None = None,
    initial_clients: list[str] | None = None,
    initial_mode: str = "unified",
    only_existing_subclients: bool = True,
    initial_lang: str | None = None,
) -> None:
    """Launch the cross-platform Tkinter graphical setup window (33 languages)."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    jurisdictions = get_all_jurisdictions()
    presets = get_regional_presets()
    detected_map = detect_installed_clients()
    detected_count = sum(1 for v in detected_map.values() if v)

    active_lang = [normalize_language_code(initial_lang) or detect_system_language()]

    def tr(key: str, **kwargs: object) -> str:
        return t(active_lang[0], key, **kwargs)

    root = tk.Tk()
    root.geometry("880x835")
    root.minsize(760, 650)

    is_mac = platform.system() == "Darwin"
    style = ttk.Style()
    if not is_mac:
        if "clam" in style.theme_names():
            style.theme_use("clam")
        root.configure(bg="#f8fafc")

    base_bg = root.cget("bg")
    font_family = "SF Pro Text" if is_mac else "Segoe UI"

    container = ttk.Frame(root, padding=(18, 12, 18, 12))
    container.pack(fill="both", expand=True)

    # Calm Header + Live 33-Language Selector Dropdown
    header_row = ttk.Frame(container)
    header_row.pack(fill="x", pady=(0, 4))
    header_lbl = ttk.Label(
        header_row,
        text=tr("header_title"),
        font=(font_family, 13, "bold"),
    )
    header_lbl.pack(side="left", anchor="w")

    header_right = ttk.Frame(header_row)
    header_right.pack(side="right", anchor="e")

    dry_badge: tk.Label | None = None
    if dry_run:
        dry_badge = tk.Label(
            header_right,
            text=f" {tr('dry_run_tag')} ",
            bg="#fef3c7",
            fg="#92400e",
            font=(font_family, 9, "bold"),
            padx=6,
            pady=2,
        )
        dry_badge.pack(side="left", padx=(0, 8))

    lang_lbl = ttk.Label(header_right, text=tr("language_label"), font=(font_family, 9))
    lang_lbl.pack(side="left", padx=(0, 4))

    display_values = [disp for _, disp in LANGUAGE_DISPLAY_OPTIONS]
    code_to_display = dict(LANGUAGE_DISPLAY_OPTIONS)
    display_to_code = {disp: code for code, disp in LANGUAGE_DISPLAY_OPTIONS}

    lang_var = tk.StringVar(value=code_to_display.get(active_lang[0], code_to_display["en"]))
    lang_combo = ttk.Combobox(
        header_right,
        textvariable=lang_var,
        values=display_values,
        state="readonly",
        width=20,
    )
    lang_combo.pack(side="left")

    info_box = tk.Frame(
        container,
        bg="#ecfdf5",
        highlightbackground="#6ee7b7",
        highlightthickness=1,
        padx=12,
        pady=8,
    )
    info_box.pack(fill="x", pady=(0, 10))
    info_lbl = tk.Label(
        info_box,
        text=f"{tr('trust_banner')}\n{tr('info_bullets')}",
        bg="#ecfdf5",
        fg="#064e3b",
        justify="left",
        anchor="w",
        font=(font_family, 9),
    )
    info_lbl.pack(fill="x")

    # Pack bottom section BEFORE middle expandable country list so buttons stay visible
    bottom_section = ttk.Frame(container)
    bottom_section.pack(side="bottom", fill="x")

    # Step 2: AI Client Selection with Auto-Detection
    client_frame = ttk.LabelFrame(
        bottom_section,
        text=tr("step2_frame"),
        padding=(10, 6),
    )
    client_frame.pack(fill="x", pady=(0, 8))

    client_toolbar = ttk.Frame(client_frame)
    client_toolbar.pack(fill="x", pady=(0, 4))

    prechecked_clients = set(initial_clients) if initial_clients is not None else {
        k for k, is_found in detected_map.items() if is_found
    }
    client_vars: dict[str, tk.BooleanVar] = {
        key: tk.BooleanVar(value=(key in prechecked_clients)) for key, _, _ in CLIENT_SPECS
    }

    def set_all_clients(state: bool) -> None:
        for var in client_vars.values():
            var.set(state)

    def select_detected_clients() -> None:
        for key, var in client_vars.items():
            var.set(bool(detected_map.get(key, False)))

    btn_sel_detected = ttk.Button(client_toolbar, text=tr("btn_select_detected"), command=select_detected_clients)
    btn_sel_detected.pack(side="left", padx=(0, 6))
    btn_sel_all = ttk.Button(client_toolbar, text=tr("btn_select_all"), command=lambda: set_all_clients(True))
    btn_sel_all.pack(side="left", padx=(0, 6))
    btn_clr_clients = ttk.Button(client_toolbar, text=tr("btn_clear"), command=lambda: set_all_clients(False))
    btn_clr_clients.pack(side="left")

    detected_lbl = ttk.Label(
        client_toolbar,
        text=tr("auto_detected_count", count=detected_count),
        font=(font_family, 9),
    )
    detected_lbl.pack(side="right")

    clients_grid = ttk.Frame(client_frame)
    clients_grid.pack(fill="x")
    clients_grid.columnconfigure(0, weight=1)
    clients_grid.columnconfigure(1, weight=1)

    client_cbs: dict[str, tuple[str, ttk.Checkbutton]] = {}
    for idx, (key, label, _default) in enumerate(CLIENT_SPECS):
        tag = f"  {tr('tag_detected')}" if detected_map.get(key) else f"  {tr('tag_not_detected')}"
        cb = ttk.Checkbutton(
            clients_grid,
            text=f"{label}{tag}",
            variable=client_vars[key],
        )
        cb.grid(row=idx // 2, column=idx % 2, sticky="w", padx=6, pady=2)
        client_cbs[key] = (label, cb)

    remote_note_lbl = tk.Label(
        client_frame,
        text=tr("remote_connector_note"),
        bg=base_bg,
        fg="#475569",
        justify="left",
        anchor="w",
        wraplength=800,
        font=(font_family, 8),
    )
    remote_note_lbl.pack(fill="x", pady=(4, 0))

    # Advanced Options Row (Standalone Mode + Pre-Warm)
    options_frame = ttk.Frame(bottom_section)
    options_frame.pack(fill="x", pady=(0, 4))

    standalone_var = tk.BooleanVar(value=(initial_mode == "standalone"))
    prewarm_var = tk.BooleanVar(value=False)
    standalone_warn_var = tk.StringVar(value="")

    standalone_cb = ttk.Checkbutton(
        options_frame,
        text=tr("opt_standalone"),
        variable=standalone_var,
    )
    standalone_cb.pack(side="left", padx=(0, 14))
    prewarm_cb = ttk.Checkbutton(
        options_frame,
        text=tr("opt_prewarm"),
        variable=prewarm_var,
    )
    prewarm_cb.pack(side="left")

    warn_label = tk.Label(
        bottom_section,
        textvariable=standalone_warn_var,
        bg=base_bg,
        fg="#b45309",
        justify="left",
        anchor="w",
        font=(font_family, 9),
    )
    warn_label.pack(fill="x", pady=(0, 2))

    # Progress & Action Section
    is_busy = [False]
    status_var = tk.StringVar(value=tr("status_ready_dry") if dry_run else tr("status_ready"))
    ttk.Label(bottom_section, textvariable=status_var, font=(font_family, 9)).pack(anchor="w", pady=(2, 4))

    progress = ttk.Progressbar(bottom_section, orient="horizontal", mode="determinate", maximum=100, value=0)
    progress.pack(fill="x", pady=(0, 8))

    btn_row = ttk.Frame(bottom_section)
    btn_row.pack(fill="x")

    install_btn = ttk.Button(
        btn_row,
        text=tr("btn_install_dry") if dry_run else tr("btn_install"),
        default="active",
    )
    install_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

    test_btn = ttk.Button(btn_row, text=tr("btn_test_connection"))
    test_btn.pack(side="left", padx=(0, 6))

    uninstall_btn = ttk.Button(btn_row, text=tr("btn_uninstall"))
    uninstall_btn.pack(side="left", padx=(0, 6))

    close_btn = ttk.Button(btn_row, text=tr("btn_close"), command=lambda: root.destroy())
    close_btn.pack(side="right")

    # Step 1: Expandable Country Selection + Regional Presets
    country_frame = ttk.LabelFrame(container, text=tr("step1_frame"), padding=(10, 6))
    country_frame.pack(side="top", fill="both", expand=True, pady=(0, 8))

    sorted_items = sorted(jurisdictions.items(), key=lambda x: x[1])
    prechecked_countries = set(initial_countries or [])
    country_vars: dict[str, tk.BooleanVar] = {
        code: tk.BooleanVar(value=(code in prechecked_countries)) for code, _ in sorted_items
    }
    search_var = tk.StringVar(value="")
    count_var = tk.StringVar(value="")

    def update_count(*_args: object) -> None:
        selected_n = sum(1 for v in country_vars.values() if v.get())
        suffix = tr("selected_all_suffix") if selected_n == len(sorted_items) else ""
        count_var.set(tr("selected_count", selected=selected_n, total=len(sorted_items)) + suffix)
        if standalone_var.get() and selected_n > STANDALONE_WARNING_THRESHOLD:
            standalone_warn_var.set(tr("standalone_inline_warn", count=selected_n))
        else:
            standalone_warn_var.set("")

    standalone_var.trace_add("write", update_count)

    def apply_preset(codes: list[str]) -> None:
        code_set = set(codes)
        for code, var in country_vars.items():
            var.set(code in code_set)
        update_count()

    def clear_all_countries() -> None:
        for var in country_vars.values():
            var.set(False)
        update_count()

    # Regional Presets Grid (2 neat rows)
    preset_row = ttk.Frame(country_frame)
    preset_row.pack(fill="x", pady=(0, 6))
    presets_lbl = ttk.Label(preset_row, text=tr("presets_label"), font=(font_family, 9, "bold"))
    presets_lbl.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=2)

    preset_items = list(presets.items())
    preset_btns: list[tuple[str, list[str], ttk.Button]] = []
    for p_idx, (preset_name, preset_codes) in enumerate(preset_items):
        grid_r = p_idx // 4
        grid_c = (p_idx % 4) + 1
        btn = ttk.Button(
            preset_row,
            text=preset_name,
            command=lambda c=preset_codes: apply_preset(c),
        )
        btn.grid(row=grid_r, column=grid_c, sticky="w", padx=(0, 4), pady=2)
        preset_btns.append((preset_name, preset_codes, btn))

    # Filter & Clear Toolbar
    toolbar = ttk.Frame(country_frame)
    toolbar.pack(fill="x", pady=(0, 6))
    btn_clr_countries = ttk.Button(toolbar, text=tr("btn_clear_selection"), command=clear_all_countries)
    btn_clr_countries.pack(side="left", padx=(0, 12))
    search_lbl = ttk.Label(toolbar, text=tr("search_label"))
    search_lbl.pack(side="left", padx=(0, 4))
    search_entry = ttk.Entry(toolbar, textvariable=search_var, width=24)
    search_entry.pack(side="left", padx=(0, 10))
    ttk.Label(toolbar, textvariable=count_var, font=(font_family, 10, "bold")).pack(side="right")

    list_container = ttk.Frame(country_frame)
    list_container.pack(fill="both", expand=True)

    canvas = tk.Canvas(list_container, highlightthickness=0, bd=0, bg=base_bg, height=180)
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
            cb.grid(row=idx // 3, column=idx % 3, sticky="w", padx=6, pady=2)
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

    def apply_language(lang_code: str) -> None:
        """Live-update every GUI widget and title immediately when language changes."""
        active_lang[0] = normalize_language_code(lang_code) or "en"
        title_suffix = f" {tr('dry_run_tag')}" if dry_run else ""
        root.title(tr("window_title", version=VERSION, count=len(jurisdictions)) + title_suffix)
        header_lbl.configure(text=tr("header_title"))
        lang_lbl.configure(text=tr("language_label"))
        if dry_badge is not None:
            dry_badge.configure(text=f" {tr('dry_run_tag')} ")
        info_lbl.configure(text=f"{tr('trust_banner')}\n{tr('info_bullets')}")
        country_frame.configure(text=tr("step1_frame"))
        presets_lbl.configure(text=tr("presets_label"))
        for preset_name, preset_codes, btn in preset_btns:
            i18n_key = PRESET_I18N_KEYS.get(preset_name)
            if i18n_key == "preset_all":
                btn.configure(text=tr("preset_all", count=len(preset_codes)))
            elif i18n_key:
                btn.configure(text=tr(i18n_key))
            else:
                btn.configure(text=preset_name)
        btn_clr_countries.configure(text=tr("btn_clear_selection"))
        search_lbl.configure(text=tr("search_label"))
        client_frame.configure(text=tr("step2_frame"))
        btn_sel_detected.configure(text=tr("btn_select_detected"))
        btn_sel_all.configure(text=tr("btn_select_all"))
        btn_clr_clients.configure(text=tr("btn_clear"))
        detected_lbl.configure(text=tr("auto_detected_count", count=detected_count))
        for key, (label, cb) in client_cbs.items():
            tag = f"  {tr('tag_detected')}" if detected_map.get(key) else f"  {tr('tag_not_detected')}"
            cb.configure(text=f"{label}{tag}")
        remote_note_lbl.configure(text=tr("remote_connector_note"))
        standalone_cb.configure(text=tr("opt_standalone"))
        prewarm_cb.configure(text=tr("opt_prewarm"))
        if not is_busy[0]:
            install_btn.configure(text=tr("btn_install_dry") if dry_run else tr("btn_install"))
            status_var.set(tr("status_ready_dry") if dry_run else tr("status_ready"))
        test_btn.configure(text=tr("btn_test_connection"))
        uninstall_btn.configure(text=tr("btn_uninstall"))
        close_btn.configure(text=tr("btn_close"))
        update_count()

    def on_language_selected(_event: object = None) -> None:
        chosen = display_to_code.get(lang_var.get()) or normalize_language_code(lang_var.get()) or "en"
        apply_language(chosen)

    lang_combo.bind("<<ComboboxSelected>>", on_language_selected)
    search_var.trace_add("write", render_countries)
    render_countries()
    apply_language(active_lang[0])

    def set_controls_busy(busy: bool, busy_text: str | None = None) -> None:
        is_busy[0] = busy
        state = "disabled" if busy else "normal"
        install_btn.configure(
            state=state,
            text=(busy_text or tr("status_installing"))
            if busy
            else (tr("btn_install_dry") if dry_run else tr("btn_install")),
        )
        test_btn.configure(state=state)
        uninstall_btn.configure(state=state)
        close_btn.configure(state=state)
        lang_combo.configure(state="disabled" if busy else "readonly")

    def show_first_60_seconds_dialog(chosen_codes: list[str], res: InstallResult) -> None:
        """Display completion summary + 3 copy-paste starter legal prompts."""
        dlg = tk.Toplevel(root)
        dry_prefix = f"{tr('dry_run_tag')} " if dry_run else ""
        dlg.title(f"{dry_prefix}{tr('done_dialog_title')}")
        dlg.geometry("700x580")
        dlg.minsize(580, 460)
        dlg.transient(root)
        dlg.grab_set()

        outer = ttk.Frame(dlg, padding=(16, 14, 16, 14))
        outer.pack(fill="both", expand=True)

        if len(chosen_codes) == len(jurisdictions):
            country_summary = tr("done_all_jurisdictions", count=len(jurisdictions))
        else:
            code_str = ", ".join(c.upper() for c in chosen_codes[:8]) + (" ..." if len(chosen_codes) > 8 else "")
            country_summary = tr("done_n_jurisdictions", count=len(chosen_codes), codes=code_str)
        mode_summary = tr("mode_unified") if res.mode == "unified" else tr("mode_standalone")
        file_count = len(res.unique_files)

        header_bg = "#fef3c7" if dry_run else "#ecfdf5"
        header_fg = "#92400e" if dry_run else "#065f46"
        banner = tk.Frame(outer, bg=header_bg, padx=12, pady=10, highlightthickness=1, highlightbackground="#a7f3d0")
        banner.pack(fill="x", pady=(0, 12))

        summary_lines = [
            f"{dry_prefix}{tr('done_heading')}",
            tr("done_summary", mode=mode_summary, jurisdictions=country_summary, files=file_count),
        ]
        if res.backups_created:
            summary_lines.append(tr("done_backups_line", count=len(res.backups_created)))
        if res.prewarm_status:
            summary_lines.append(f"• {res.prewarm_status}")
        summary_lines.append(tr("status_ready_dry") if dry_run else tr("done_restart_note"))

        tk.Label(
            banner,
            text="\n".join(summary_lines),
            bg=header_bg,
            fg=header_fg,
            justify="left",
            anchor="w",
            font=(font_family, 9),
        ).pack(fill="x")

        ttk.Label(
            outer,
            text=tr("first_60s_heading"),
            font=(font_family, 11, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        prompts = get_starter_prompts(chosen_codes)
        for p_idx, (p_title, p_text) in enumerate(prompts, start=1):
            card = ttk.LabelFrame(outer, text=f"{p_idx}. {p_title}", padding=(10, 6))
            card.pack(fill="x", pady=(0, 8))

            tk.Label(
                card,
                text=p_text,
                justify="left",
                anchor="w",
                wraplength=600,
                font=(font_family, 9),
            ).pack(fill="x", pady=(0, 6))

            copy_btn = ttk.Button(card, text=tr("btn_copy_prompt"))

            def _make_copier(txt: str, btn: ttk.Button) -> Callable[[], None]:
                def _copy() -> None:
                    dlg.clipboard_clear()
                    dlg.clipboard_append(txt)
                    dlg.update_idletasks()
                    btn.configure(text=tr("btn_copied"))
                    dlg.after(1600, lambda: btn.winfo_exists() and btn.configure(text=tr("btn_copy_prompt")))

                return _copy

            copy_btn.configure(command=_make_copier(p_text, copy_btn))
            copy_btn.pack(anchor="e")

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(8, 0))
        ttk.Button(footer, text=tr("btn_keep_open"), command=dlg.destroy).pack(side="left")
        ttk.Button(
            footer,
            text=tr("btn_done_close"),
            default="active",
            command=lambda: (dlg.destroy(), root.destroy()),
        ).pack(side="right")

    def start_install() -> None:
        chosen_codes = [code for code, _ in sorted_items if country_vars[code].get()]
        chosen_clients = [key for key, _, _ in CLIENT_SPECS if client_vars[key].get()]
        mode = "standalone" if standalone_var.get() else "unified"

        if not chosen_codes:
            messagebox.showwarning(tr("warn_no_country_title"), tr("warn_no_country_body"), parent=root)
            return
        if not chosen_clients:
            messagebox.showwarning(tr("warn_no_client_title"), tr("warn_no_client_body"), parent=root)
            return

        if mode == "standalone" and len(chosen_codes) > STANDALONE_WARNING_THRESHOLD:
            proceed = messagebox.askyesno(
                tr("warn_many_standalone_title"),
                tr("warn_many_standalone_body", count=len(chosen_codes)),
                parent=root,
            )
            if not proceed:
                return

        set_controls_busy(True, tr("status_installing"))
        progress.configure(value=5)
        status_var.set(tr("status_installing"))
        events: queue.Queue[tuple[str, Any]] = queue.Queue()
        lang_snapshot = active_lang[0]

        def worker() -> None:
            try:
                res = install_servers(
                    chosen_codes,
                    chosen_clients,
                    dry_run=dry_run,
                    mode=mode,
                    only_existing_subclients=only_existing_subclients,
                    prewarm=prewarm_var.get(),
                    progress_cb=lambda pct, msg: events.put(("progress", (pct, msg))),
                    lang=lang_snapshot,
                )
                events.put(("done", res))
            except Exception as exc:
                events.put(("error", str(exc)))

        def poll() -> None:
            try:
                while True:
                    kind, payload = events.get_nowait()
                    if kind == "progress":
                        pct, msg = payload
                        progress.configure(value=pct)
                        status_var.set(str(msg))
                    elif kind == "done":
                        set_controls_busy(False)
                        show_first_60_seconds_dialog(chosen_codes, payload)
                        return
                    elif kind == "error":
                        set_controls_busy(False)
                        status_var.set(tr("status_error", error=payload))
                        messagebox.showerror(tr("err_setup_title"), str(payload), parent=root)
                        return
            except queue.Empty:
                pass
            if root.winfo_exists():
                root.after(50, poll)

        threading.Thread(target=worker, daemon=True).start()
        root.after(50, poll)

    def start_test_connection() -> None:
        set_controls_busy(True, tr("btn_test_connection"))
        progress.configure(mode="indeterminate")
        progress.start(12)
        status_var.set(tr("status_testing"))
        events: queue.Queue[tuple[str, Any]] = queue.Queue()
        mode = "standalone" if standalone_var.get() else "unified"

        def worker() -> None:
            try:
                res = test_connection(mode=mode, check_server=True, timeout=15)
                events.put(("done", res))
            except Exception as exc:
                events.put(("error", str(exc)))

        def poll() -> None:
            try:
                while True:
                    kind, payload = events.get_nowait()
                    progress.stop()
                    progress.configure(mode="determinate", value=100 if kind == "done" else 0)
                    set_controls_busy(False)
                    if kind == "done":
                        res: ConnectionCheckResult = payload
                        status_var.set(res.summary)
                        body = res.summary + "\n\n" + "\n".join(f"• {d}" for d in res.details)
                        if res.ok:
                            messagebox.showinfo(tr("conn_check_title"), body, parent=root)
                        else:
                            messagebox.showwarning(tr("conn_check_title"), body, parent=root)
                        return
                    elif kind == "error":
                        status_var.set(tr("status_error", error=payload))
                        messagebox.showerror(tr("conn_check_title"), str(payload), parent=root)
                        return
            except queue.Empty:
                pass
            if root.winfo_exists():
                root.after(50, poll)

        threading.Thread(target=worker, daemon=True).start()
        root.after(50, poll)

    def start_uninstall() -> None:
        chosen_clients = [key for key, _, _ in CLIENT_SPECS if client_vars[key].get()]
        scope_text = (
            tr("uninstall_scope_selected", count=len(chosen_clients))
            if chosen_clients
            else tr("uninstall_scope_all")
        )
        dry_prefix = f"{tr('dry_run_tag')} " if dry_run else ""
        confirmed = messagebox.askyesno(
            f"{dry_prefix}{tr('uninstall_confirm_title')}",
            tr("uninstall_confirm_body", scope=scope_text),
            parent=root,
        )
        if not confirmed:
            return

        set_controls_busy(True, tr("status_removing"))
        progress.configure(value=10)
        status_var.set(tr("status_removing"))
        events: queue.Queue[tuple[str, Any]] = queue.Queue()

        def worker() -> None:
            try:
                res = uninstall_servers(
                    chosen_keys=chosen_clients if chosen_clients else None,
                    dry_run=dry_run,
                    progress_cb=lambda pct, msg: events.put(("progress", (pct, msg))),
                )
                events.put(("done", res))
            except Exception as exc:
                events.put(("error", str(exc)))

        def poll() -> None:
            try:
                while True:
                    kind, payload = events.get_nowait()
                    if kind == "progress":
                        pct, msg = payload
                        progress.configure(value=pct)
                        status_var.set(str(msg))
                    elif kind == "done":
                        res: UninstallResult = payload
                        set_controls_busy(False)
                        progress.configure(value=100)
                        if res.removed:
                            msg = f"{dry_prefix}{tr('uninstall_done_body', entries=len(res.removed), files=len(res.unique_files))}"
                            if res.backups_created:
                                msg += "\n" + tr("done_backups_line", count=len(res.backups_created))
                            if res.errors:
                                msg += "\n\n" + "\n".join(res.errors)
                            status_var.set(f"{dry_prefix}{tr('uninstall_done_title')}")
                            messagebox.showinfo(f"{dry_prefix}{tr('uninstall_done_title')}", msg, parent=root)
                        else:
                            status_var.set(tr("uninstall_none_body"))
                            msg = tr("uninstall_none_body")
                            if res.errors:
                                msg += "\n\n" + "\n".join(res.errors)
                            messagebox.showinfo(tr("uninstall_confirm_title"), msg, parent=root)
                        return
                    elif kind == "error":
                        set_controls_busy(False)
                        status_var.set(tr("status_error", error=payload))
                        messagebox.showerror(tr("err_setup_title"), str(payload), parent=root)
                        return
            except queue.Empty:
                pass
            if root.winfo_exists():
                root.after(50, poll)

        threading.Thread(target=worker, daemon=True).start()
        root.after(50, poll)

    install_btn.configure(command=start_install)
    test_btn.configure(command=start_test_connection)
    uninstall_btn.configure(command=start_uninstall)

    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    # Pure Tk focus activation (no macOS TCC permission popups!)
    topmost_id = None
    if is_mac:
        root.lift()
        root.attributes("-topmost", True)
        topmost_id = root.after(200, lambda: root.winfo_exists() and root.attributes("-topmost", False))
        root.focus_force()

    orig_destroy = root.destroy

    def clean_destroy() -> None:
        if topmost_id is not None:
            try:
                root.after_cancel(topmost_id)
            except Exception:
                pass
        orig_destroy()

    root.destroy = clean_destroy  # type: ignore[method-assign]
    root.mainloop()


def _prompt_for_language(default_lang: str) -> str:
    """Compact Step 0 language picker for interactive terminal `--cli` mode (ASCII codes or numbers)."""
    default_code = normalize_language_code(default_lang) or "en"
    default_name = SUPPORTED_LANGUAGES.get(default_code, "English")

    print(
        t(
            default_code,
            "cli_lang_header",
            default_name=default_name,
            default_code=default_code,
        )
    )
    items = list(SUPPORTED_LANGUAGES.items())
    cols = 3
    rows = (len(items) + cols - 1) // cols
    for r in range(rows):
        row_parts: list[str] = []
        for c in range(cols):
            idx = r + c * rows
            if idx < len(items):
                code, native = items[idx]
                row_parts.append(f"[{idx + 1:2d}] {code:<3} {native:<16}")
        print("  " + "  ".join(row_parts).rstrip())

    try:
        raw = input(t(default_code, "cli_lang_prompt", default_code=default_code)).strip()
    except EOFError:
        return default_code

    if not raw:
        return default_code

    if raw.isdigit():
        num = int(raw)
        if 1 <= num <= len(items):
            return items[num - 1][0]

    matched = normalize_language_code(raw)
    if matched is not None:
        return matched

    print(
        t(
            default_code,
            "cli_lang_invalid",
            raw=raw,
            default_name=default_name,
            default_code=default_code,
        )
    )
    return default_code


def _prompt_for_clients(detected_map: dict[str, bool], lang: str = "en") -> list[str]:
    """Prompt interactively for AI clients in terminal mode."""
    detected_keys = [k for k, is_found in detected_map.items() if is_found]
    print("\n--------------------------------------------------------------------------")
    print(t(lang, "cli_clients_heading"))
    for key, label, _ in CLIENT_SPECS:
        tag = f" {t(lang, 'tag_detected')}" if detected_map.get(key) else ""
        print(f"  [{key}] {label}{tag}")
    print(f"  {t(lang, 'cli_clients_all_opt')}")
    if detected_keys:
        print(f"  {t(lang, 'cli_clients_enter_detected', keys=', '.join(detected_keys))}")
    print(f"\n  {t(lang, 'remote_connector_note')}")

    while True:
        try:
            prompt_str = (
                f"\n{t(lang, 'cli_prompt_clients_detected')}"
                if detected_keys
                else f"\n{t(lang, 'cli_prompt_clients')}"
            )
            raw_clients = input(prompt_str).strip()
        except EOFError:
            if detected_keys:
                return detected_keys
            print(t(lang, "cli_clients_retry", max_n=len(CLIENT_SPECS)))
            sys.exit(1)

        if not raw_clients and detected_keys:
            return detected_keys

        chosen_keys = parse_client_selection(raw_clients, detected_keys=detected_keys)
        if chosen_keys:
            return chosen_keys
        print(t(lang, "cli_clients_retry", max_n=len(CLIENT_SPECS)))


def run_cli(
    countries_arg: str | None = None,
    clients_arg: str | None = None,
    dry_run: bool = False,
    mode: str = "unified",
    only_existing_subclients: bool = True,
    prewarm: bool = False,
    lang_arg: str | None = None,
) -> None:
    """Run the interactive (or argument-driven) terminal installer (33 languages)."""
    configure_console_utf8()

    if lang_arg is not None:
        resolved_lang = normalize_language_code(lang_arg)
        if resolved_lang is None:
            print(
                f"Unsupported language '{lang_arg}'. Supported codes: {', '.join(LANGUAGE_CODES)}",
                file=sys.stderr,
            )
            sys.exit(1)
        lang = resolved_lang
    else:
        detected_lang = detect_system_language()
        if countries_arg is None:
            print("\n==========================================================================")
            lang = _prompt_for_language(detected_lang)
        else:
            lang = detected_lang

    jurisdictions = get_all_jurisdictions()
    detected_map = detect_installed_clients()
    detected_keys = [k for k, is_found in detected_map.items() if is_found]

    print("\n==========================================================================")
    print(f"  {t(lang, 'window_title', version=VERSION, count=len(jurisdictions))}")
    print(f"  {t(lang, 'trust_banner')}")
    print("==========================================================================\n")

    if countries_arg is None:
        items = sorted(jurisdictions.items(), key=lambda x: x[1])
        half = (len(items) + 1) // 2
        for i in range(half):
            left_code, left_name = items[i]
            left_str = f"[{left_code}] {left_name:<26}"
            right_str = ""
            if i + half < len(items):
                right_code, right_name = items[i + half]
                right_str = f"[{right_code}] {right_name}"
            print(f"  {left_str}  {right_str}")
        print(f"\n  {t(lang, 'cli_all_line', count=len(jurisdictions))}")
        print(f"  {t(lang, 'presets_label')} eu-uk-ch | dach | common-law | nordics | western-balkans | tr-eu")

        print("\n--------------------------------------------------------------------------")
        raw_countries = input(t(lang, "cli_prompt_countries")).strip()
        if not raw_countries:
            print(t(lang, "cli_no_country_exit"))
            sys.exit(0)
    else:
        raw_countries = countries_arg

    selected_codes = parse_country_selection(raw_countries)
    if not selected_codes:
        print(t(lang, "cli_country_unmatched", raw=raw_countries))
        sys.exit(1)

    print(f"\n{t(lang, 'cli_selected_heading')}")
    if len(selected_codes) == len(jurisdictions):
        print(f"  -> {t(lang, 'done_all_jurisdictions', count=len(jurisdictions))}")
    else:
        for c in selected_codes:
            print(f"  -> {jurisdictions[c]} [{c}]")

    if mode == "standalone" and len(selected_codes) > STANDALONE_WARNING_THRESHOLD:
        print(f"\n[!] {t(lang, 'standalone_inline_warn', count=len(selected_codes))}")

    if clients_arg is not None:
        chosen_keys = parse_client_selection(clients_arg, detected_keys=detected_keys)
        if not chosen_keys:
            print(t(lang, "cli_clients_unmatched", raw=clients_arg))
            sys.exit(1)
    else:
        # Prompt interactively even when --countries was provided without --clients
        chosen_keys = _prompt_for_clients(detected_map, lang=lang)

    try:
        res = install_servers(
            selected_codes,
            chosen_keys,
            dry_run=dry_run,
            mode=mode,
            only_existing_subclients=only_existing_subclients,
            prewarm=prewarm,
            lang=lang,
        )
    except ConfigParseError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n==========================================================================")
    dry_tag = f" {t(lang, 'dry_run_tag')}" if dry_run else ""
    print(f"  {t(lang, 'done_heading')}{dry_tag}")
    mode_desc = t(lang, "mode_unified") if res.mode == "unified" else t(lang, "mode_standalone")
    j_summary = (
        t(lang, "done_all_jurisdictions", count=len(jurisdictions))
        if len(selected_codes) == len(jurisdictions)
        else t(lang, "done_n_jurisdictions", count=len(selected_codes), codes=", ".join(selected_codes))
    )
    for line in t(lang, "done_summary", mode=mode_desc, jurisdictions=j_summary, files=len(res.unique_files)).splitlines():
        print(f"  {line}")
    if res.backups_created:
        print(f"  {t(lang, 'done_backups_line', count=len(res.backups_created))}")
    seen_targets = list(dict.fromkeys((label, cfg_path) for label, _, cfg_path in res.links))
    for label, cfg_path in seen_targets:
        print(f"  [OK] {label} -> {cfg_path}")
    if res.prewarm_status:
        print(f"  [Check] {res.prewarm_status}")

    print(f"\n  {t(lang, 'first_60s_heading')}")
    for idx, (p_title, p_text) in enumerate(get_starter_prompts(selected_codes), start=1):
        print(f"    {idx}. {p_title}:")
        print(f'       "{p_text}"')
    print("==========================================================================\n")


def run_cli_uninstall(
    clients_arg: str | None = None,
    dry_run: bool = False,
    lang_arg: str | None = None,
) -> None:
    """Run 1-click uninstall from the terminal."""
    configure_console_utf8()
    lang = normalize_language_code(lang_arg) or detect_system_language()

    detected_map = detect_installed_clients()
    detected_keys = [k for k, is_found in detected_map.items() if is_found]
    chosen_keys: list[str] | None = None

    if clients_arg is not None:
        chosen_keys = parse_client_selection(clients_arg, detected_keys=detected_keys)
        if not chosen_keys:
            print(t(lang, "cli_clients_unmatched", raw=clients_arg))
            sys.exit(1)

    res = uninstall_servers(chosen_keys=chosen_keys, dry_run=dry_run)
    dry_tag = f" {t(lang, 'dry_run_tag')}" if dry_run else ""
    print(f"\n{t(lang, 'uninstall_confirm_title')}{dry_tag}")
    if res.removed:
        print(f"  {t(lang, 'uninstall_done_body', entries=len(res.removed), files=len(res.unique_files))}")
        for label, srv_name, cfg_path in res.removed:
            print(f"  [-] {srv_name} <- {label} ({cfg_path})")
        if res.backups_created:
            print(f"  {t(lang, 'done_backups_line', count=len(res.backups_created))}")
    else:
        print(f"  {t(lang, 'uninstall_none_body')}")
    if res.errors:
        for err in res.errors:
            print(f"  [!] {err}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jurisatlas",
        description=f"JurisAtlas v{VERSION} — Interactive Installer for Official Legal MCP Servers (33 Languages).",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--cli", action="store_true", help="Use interactive terminal mode instead of GUI")
    mode_group.add_argument("--gui", action="store_true", help="Launch graphical setup window")
    parser.add_argument(
        "--lang",
        help="Interface language code (33 supported: en, tr, de, fr, el, bg, ...; auto-detected by default)",
    )
    parser.add_argument(
        "--countries",
        help="Comma-separated jurisdiction codes/names, regional preset (e.g. dach, nordics), or 'all'",
    )
    parser.add_argument(
        "--clients",
        help="Comma-separated AI client numbers (1-8), names (e.g. claude,cursor), 'detected', or 'all'",
    )
    parser.add_argument(
        "--mode",
        choices=("unified", "standalone"),
        default="unified",
        help="Server architecture: 'unified' (default, 1 server) or 'standalone' (per-country servers)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Cleanly remove all JurisAtlas entries from AI client configs (preserves other MCP servers)",
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Verify uv/uvx availability and server startup readiness",
    )
    parser.add_argument(
        "--prewarm",
        action="store_true",
        help="Pre-warm server package cache after configuration",
    )
    parser.add_argument(
        "--all-subclients",
        action="store_true",
        help="Write to all sub-client config files even if their parent app/extension folder does not exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without modifying configuration files",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"jurisatlas {VERSION}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    configure_console_utf8()
    args = parse_args(argv)

    if args.lang is not None and normalize_language_code(args.lang) is None:
        print(
            f"Unsupported language '{args.lang}'. Supported codes: {', '.join(LANGUAGE_CODES)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.test_connection:
        res = test_connection(mode=args.mode, check_server=True)
        print(res.summary)
        for line in res.details:
            print(f"  - {line}")
        sys.exit(0 if res.ok else 1)

    if args.uninstall:
        run_cli_uninstall(clients_arg=args.clients, dry_run=args.dry_run, lang_arg=args.lang)
        return

    only_existing = not args.all_subclients

    # Explicit --cli or --countries (without explicit --gui) runs terminal mode
    if args.cli or (args.countries is not None and not args.gui):
        run_cli(
            countries_arg=args.countries,
            clients_arg=args.clients,
            dry_run=args.dry_run,
            mode=args.mode,
            only_existing_subclients=only_existing,
            prewarm=args.prewarm,
            lang_arg=args.lang,
        )
        return

    initial_countries = parse_country_selection(args.countries) if args.countries else None
    initial_clients = parse_client_selection(args.clients) if args.clients else None

    if _can_launch_gui(force_cli=args.cli, force_gui=args.gui):
        try:
            print("Launching JurisAtlas Setup Window... (Tip: pass --cli for terminal mode)")
            run_gui(
                dry_run=args.dry_run,
                initial_countries=initial_countries,
                initial_clients=initial_clients,
                initial_mode=args.mode,
                only_existing_subclients=only_existing,
                initial_lang=args.lang,
            )
            return
        except Exception as exc:
            if args.gui:
                print(f"Could not start GUI ({exc}).", file=sys.stderr)
                sys.exit(1)
            print(f"GUI unavailable ({exc}); switching to interactive terminal mode.")

    run_cli(
        countries_arg=args.countries,
        clients_arg=args.clients,
        dry_run=args.dry_run,
        mode=args.mode,
        only_existing_subclients=only_existing,
        prewarm=args.prewarm,
        lang_arg=args.lang,
    )


if __name__ == "__main__":
    main()
