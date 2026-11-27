# -*- coding: utf-8 -*-
"""Comprehensive isolated test suite for JurisAtlas CLI & GUI Installer v2.0.0."""
from __future__ import annotations

import copy
import io
import json
import pathlib
import platform
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

# Ensure repos/cli is importable regardless of current working directory
CLI_DIR = pathlib.Path(__file__).resolve().parent.parent
REPOS_DIR = CLI_DIR.parent
if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))

import jurisatlas_cli as cli  # noqa: E402
import jurisatlas_i18n as i18n  # noqa: E402


class TestCountryAndClientParsing(unittest.TestCase):
    def test_select_all_aliases(self) -> None:
        all_codes = sorted(cli.get_all_jurisdictions().keys())
        self.assertGreaterEqual(len(all_codes), 42)
        self.assertIn("tr", all_codes)
        for token in ("a", "A", "all", "ALL", "*", "tümü", "tumu", "hepsi", "uk, all"):
            with self.subTest(token=token):
                self.assertEqual(cli.parse_country_selection(token), all_codes)

    def test_specific_codes_names_and_turkiye_aliases(self) -> None:
        self.assertEqual(cli.parse_country_selection("uk, de; ba"), ["ba", "de", "uk"])
        self.assertEqual(cli.parse_country_selection("uk de"), ["de", "uk"])
        self.assertEqual(cli.parse_country_selection("united kingdom, germany"), ["de", "uk"])
        self.assertEqual(cli.parse_country_selection("fr-legal-mcp"), ["fr"])
        for tr_tok in ("tr", "TR", "turkey", "türkiye", "turkiye", "tr-legal-mcp", "uyap"):
            with self.subTest(tr_tok=tr_tok):
                self.assertEqual(cli.parse_country_selection(tr_tok), ["tr"])

    def test_parse_country_rejects_short_unknown_codes_never_matches_austria_or_australia(self) -> None:
        # 1. With EXTRA_MCP_BUNDLES temporarily cleared, "tr" MUST return [] — NEVER ["at", "au"]!
        saved_bundles = copy.deepcopy(cli.EXTRA_MCP_BUNDLES)
        try:
            cli.EXTRA_MCP_BUNDLES.clear()
            self.assertEqual(cli.parse_country_selection("tr"), [])
            self.assertNotIn("at", cli.parse_country_selection("tr"))
            self.assertNotIn("au", cli.parse_country_selection("tr"))
        finally:
            cli.EXTRA_MCP_BUNDLES.clear()
            cli.EXTRA_MCP_BUNDLES.update(saved_bundles)

        # 2. Even with EXTRA_MCP_BUNDLES active, "tr" must never match Austria/Australia
        tr_result = cli.parse_country_selection("tr")
        self.assertNotIn("at", tr_result)
        self.assertNotIn("au", tr_result)

        # 3. Other 1- and 2-char unknown codes must never fuzzy-match
        for bad in ("x", "in", "en", "zz", "qq", "   ", "zzzz"):
            with self.subTest(bad=bad):
                self.assertEqual(cli.parse_country_selection(bad), [])

    def test_safe_prefix_and_word_boundary_matching(self) -> None:
        self.assertEqual(cli.parse_country_selection("aus"), ["at", "au"])
        self.assertEqual(cli.parse_country_selection("switz"), ["ch"])
        self.assertEqual(cli.parse_country_selection("kingdom"), ["uk"])
        # Suffix "land" is NOT a word start in Finland/Iceland/Ireland/Netherlands/Poland/Switzerland
        self.assertEqual(cli.parse_country_selection("land"), [])

    def test_regional_presets_complete_and_parseable(self) -> None:
        presets = cli.get_regional_presets()
        all_known = set(cli.get_all_jurisdictions().keys())
        for expected_name in (
            "EU + UK + CH",
            "DACH (DE/AT/CH)",
            "Common Law (UK/US/AU/NZ/IE)",
            "Nordics",
            "Western Balkans",
            "All Jurisdictions",
        ):
            self.assertIn(expected_name, presets)
            self.assertTrue(set(presets[expected_name]).issubset(all_known))

        self.assertEqual(cli.parse_country_selection("dach"), ["at", "ch", "de"])
        self.assertEqual(cli.parse_country_selection("nordics"), ["dk", "fi", "is", "no", "se"])
        self.assertEqual(cli.parse_country_selection("common-law"), ["au", "ie", "nz", "uk", "us"])
        self.assertEqual(cli.parse_country_selection("western-balkans"), ["al", "ba", "me", "mk", "rs", "xk"])
        self.assertEqual(len(cli.parse_country_selection("eu-uk-ch")), 30)
        self.assertEqual(cli.parse_country_selection("tr-eu"), ["eu", "tr"])

    def test_client_selection_numbers_aliases_and_detected(self) -> None:
        all_keys = ["1", "2", "3", "4", "5", "6", "7", "8"]
        self.assertEqual(cli.parse_client_selection(""), [])
        self.assertEqual(cli.parse_client_selection("   "), [])
        self.assertEqual(cli.parse_client_selection("a"), all_keys)
        self.assertEqual(cli.parse_client_selection("all"), all_keys)
        self.assertEqual(cli.parse_client_selection("1, 6, 6, 7"), ["1", "6", "7"])
        self.assertEqual(cli.parse_client_selection("2 3 8"), ["2", "3", "8"])
        self.assertEqual(cli.parse_client_selection("claude, vscode, lmstudio, continue"), ["1", "5", "7", "8"])
        self.assertEqual(cli.parse_client_selection("detected", detected_keys=["1", "3"]), ["1", "3"])
        self.assertEqual(cli.parse_client_selection("99"), [])

    def test_no_ai_clients_statically_defaulted(self) -> None:
        self.assertFalse(any(default for _key, _label, default in cli.CLIENT_SPECS))


class TestClientPathsAndAutoDetection(unittest.TestCase):
    def test_accurate_client_paths_no_fake_chatgpt_or_perplexity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            paths = cli.get_client_paths("jurisatlas-mcp", home=fake_home, system_name="Darwin")

            # No fake ChatGPT Desktop or Perplexity local config files anywhere
            all_path_strs = [str(p).lower() for _, plist in paths.values() for p in plist]
            self.assertFalse(any("chatgpt" in s for s in all_path_strs))
            self.assertFalse(any("perplexity" in s for s in all_path_strs))

            # Codex CLI uses config.toml
            self.assertEqual(paths["2"][0], "OpenAI Codex CLI")
            self.assertEqual(paths["2"][1], [fake_home / ".codex" / "config.toml"])

            # LM Studio has its real path ~/.lmstudio/mcp.json
            self.assertEqual(paths["7"][0], "LM Studio")
            self.assertEqual(paths["7"][1], [fake_home / ".lmstudio" / "mcp.json"])

            # Continue.dev is separate at ~/.continue/mcpServers/<server>.json
            self.assertEqual(paths["8"][0], "Continue.dev")
            self.assertEqual(paths["8"][1], [fake_home / ".continue" / "mcpServers" / "jurisatlas-mcp.json"])

    def test_claude_desktop_windows_msix_detection_and_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            appdata = fake_home / "AppData" / "Roaming"
            localappdata = fake_home / "AppData" / "Local"
            msix_pkg = localappdata / "Packages" / "Claude_pzs8sxrjxfjjc"
            msix_roaming = msix_pkg / "LocalCache" / "Roaming" / "Claude"
            msix_roaming.mkdir(parents=True, exist_ok=True)
            msix_cfg = msix_roaming / "claude_desktop_config.json"

            found = cli.find_claude_msix_configs(localappdata)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0][0], msix_cfg)

            detected = cli.detect_installed_clients(
                home=fake_home,
                system_name="Windows",
                appdata=appdata,
                localappdata=localappdata,
            )
            self.assertTrue(detected["1"])
            self.assertFalse(detected["3"])

            cli.install_servers(
                ["uk", "eu"],
                ["1"],
                uvx_cmd=r"C:\Users\Alice\.local\bin\uvx.exe",
                home=fake_home,
                system_name="Windows",
                appdata=appdata,
                localappdata=localappdata,
            )
            self.assertTrue(msix_cfg.exists())
            data = json.loads(msix_cfg.read_text(encoding="utf-8"))
            self.assertIn("jurisatlas-mcp", data["mcpServers"])
            self.assertEqual(
                data["mcpServers"]["jurisatlas-mcp"]["args"][-2:],
                ["--countries", "eu,uk"],
            )
            # Classic APPDATA\Claude & ~/.claude.json should NOT be created because they weren't present
            self.assertFalse((appdata / "Claude" / "claude_desktop_config.json").exists())
            self.assertFalse((fake_home / ".claude.json").exists())

    def test_auto_detect_installed_clients_in_isolated_tempdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            (fake_home / ".cursor").mkdir()
            (fake_home / ".lmstudio").mkdir()
            (fake_home / ".codex").mkdir()

            detected = cli.detect_installed_clients(home=fake_home, system_name="Linux")
            self.assertEqual(
                {k for k, v in detected.items() if v},
                {"2", "3", "7"},
            )

    def test_only_existing_subclients_avoids_collateral_extension_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            vscode_user = fake_home / "Library" / "Application Support" / "Code" / "User"
            vscode_user.mkdir(parents=True, exist_ok=True)
            cline_dir = vscode_user / "globalStorage" / "saoudrizwan.claude-dev"
            roo_dir = vscode_user / "globalStorage" / "rooveterinaryinc.roo-cline"

            # Only VS Code exists -> should write ONLY Code/User/mcp.json
            cli.install_servers(["uk"], ["5"], uvx_cmd="uvx", home=fake_home, system_name="Darwin")
            self.assertTrue((vscode_user / "mcp.json").exists())
            self.assertFalse(cline_dir.exists())
            self.assertFalse(roo_dir.exists())

            # Now create Cline extension dir -> should write VS Code + Cline, still skip Roo
            cline_dir.mkdir(parents=True, exist_ok=True)
            cli.install_servers(["uk"], ["5"], uvx_cmd="uvx", home=fake_home, system_name="Darwin")
            self.assertTrue((cline_dir / "settings" / "cline_mcp_settings.json").exists())
            self.assertFalse(roo_dir.exists())


class TestSchemasBackupsAndAtomicity(unittest.TestCase):
    def test_windows_codex_toml_double_run_backslash_safety_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            codex_toml = fake_home / ".codex" / "config.toml"
            codex_toml.parent.mkdir(parents=True, exist_ok=True)
            codex_toml.write_text(
                '[model]\nname = "gpt-5"\n\n[mcp_servers.custom-other]\ncommand = "node"\nargs = ["server.js"]\n',
                encoding="utf-8",
            )

            win_uvx = r"C:\Users\Alice\.local\bin\uvx.exe"

            # Run 1 (Unified mode)
            res1 = cli.install_servers(
                ["uk", "de"],
                ["2"],
                uvx_cmd=win_uvx,
                home=fake_home,
                system_name="Windows",
            )
            self.assertIn(str(codex_toml), res1.unique_files)

            parsed1 = tomllib.loads(codex_toml.read_text(encoding="utf-8"))
            self.assertEqual(parsed1["mcp_servers"]["jurisatlas-mcp"]["command"], win_uvx)
            self.assertEqual(
                parsed1["mcp_servers"]["jurisatlas-mcp"]["env"],
                {"PYTHONIOENCODING": "utf-8"},
            )
            self.assertEqual(parsed1["model"]["name"], "gpt-5")
            self.assertEqual(parsed1["mcp_servers"]["custom-other"]["command"], "node")

            # Run 2 (must NOT corrupt Windows backslashes!)
            cli.install_servers(
                ["uk", "de", "ch"],
                ["2"],
                uvx_cmd=win_uvx,
                home=fake_home,
                system_name="Windows",
            )
            toml_text2 = codex_toml.read_text(encoding="utf-8")
            parsed2 = tomllib.loads(toml_text2)
            self.assertEqual(parsed2["mcp_servers"]["jurisatlas-mcp"]["command"], win_uvx)
            self.assertEqual(
                parsed2["mcp_servers"]["jurisatlas-mcp"]["args"][-2:],
                ["--countries", "ch,de,uk"],
            )
            self.assertEqual(
                parsed2["mcp_servers"]["jurisatlas-mcp"]["env"],
                {"PYTHONIOENCODING": "utf-8"},
            )
            self.assertEqual(toml_text2.count("[mcp_servers.jurisatlas-mcp]"), 1)

            # Verify timestamped backups created on both runs
            backups = sorted(codex_toml.parent.glob("config.toml.bak.*"))
            self.assertEqual(len(backups), 2)

    def test_vscode_native_servers_schema_and_cline_roo_mcp_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            appdata = fake_home / "AppData" / "Roaming"
            vscode_base = appdata / "Code" / "User"
            cline_dir = vscode_base / "globalStorage" / "saoudrizwan.claude-dev"
            roo_dir = vscode_base / "globalStorage" / "rooveterinaryinc.roo-cline"
            vscode_base.mkdir(parents=True, exist_ok=True)
            cline_dir.mkdir(parents=True, exist_ok=True)
            roo_dir.mkdir(parents=True, exist_ok=True)

            cli.install_servers(
                ["ch", "uk"],
                ["5"],
                uvx_cmd="/usr/local/bin/uvx",
                home=fake_home,
                system_name="Windows",
                appdata=appdata,
            )

            # Native VS Code mcp.json MUST use top-level "servers" with "type": "stdio"
            vscode_data = json.loads((vscode_base / "mcp.json").read_text(encoding="utf-8"))
            self.assertIn("servers", vscode_data)
            self.assertNotIn("mcpServers", vscode_data)
            srv = vscode_data["servers"]["jurisatlas-mcp"]
            self.assertEqual(srv["type"], "stdio")
            self.assertEqual(srv["command"], "/usr/local/bin/uvx")
            self.assertEqual(srv["env"], {"PYTHONIOENCODING": "utf-8"})

            # Cline & Roo Code MUST keep top-level "mcpServers"
            cline_data = json.loads(
                (cline_dir / "settings" / "cline_mcp_settings.json").read_text(encoding="utf-8")
            )
            roo_data = json.loads((roo_dir / "settings" / "mcp_settings.json").read_text(encoding="utf-8"))
            self.assertIn("mcpServers", cline_data)
            self.assertNotIn("servers", cline_data)
            self.assertIn("jurisatlas-mcp", cline_data["mcpServers"])
            self.assertIn("mcpServers", roo_data)
            self.assertIn("jurisatlas-mcp", roo_data["mcpServers"])

    def test_jsonc_utf8_bom_comments_trailing_commas_and_timestamped_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "mcp.json"
            jsonc_content = (
                "// Top-level comment\n"
                "{\n"
                '  /* Multi-line\n'
                '     block comment */\n'
                '  "url": "https://example.com//keep-slashes/*not-comment*/",\n'
                '  "note": "comma inside string, }", \n'
                '  "servers": {\n'
                '    "existing": {\n'
                '      "type": "stdio",\n'
                '      "command": "echo",\n'
                '      "args": ["hi",],\n'
                "    },\n"
                "  },\n"
                "}\n"
            )
            cfg.write_bytes(b"\xef\xbb\xbf" + jsonc_content.encode("utf-8"))

            backup = cli.upsert_json_mcp_file(
                cfg,
                {"jurisatlas-mcp": cli.build_unified_server_entry(["uk"], "uvx")},
                root_key="servers",
                include_type_stdio=True,
            )

            self.assertIsNotNone(backup)
            assert backup is not None
            self.assertTrue(backup.exists())
            self.assertRegex(backup.name, r"^mcp\.json\.bak\.\d{8}-\d{6}")

            parsed = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(parsed["url"], "https://example.com//keep-slashes/*not-comment*/")
            self.assertEqual(parsed["note"], "comma inside string, }")
            self.assertIn("existing", parsed["servers"])
            self.assertIn("jurisatlas-mcp", parsed["servers"])
            self.assertEqual(parsed["servers"]["jurisatlas-mcp"]["type"], "stdio")

    def test_unparseable_config_never_silently_wiped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / ".claude.json"
            broken_raw = "{broken json — user settings that must never be wiped!"
            cfg.write_text(broken_raw, encoding="utf-8")

            with self.assertRaises(cli.ConfigParseError):
                cli.upsert_json_mcp_file(
                    cfg,
                    {"jurisatlas-mcp": cli.build_unified_server_entry(["uk"], "uvx")},
                )

            # Original file MUST remain completely intact
            self.assertEqual(cfg.read_text(encoding="utf-8"), broken_raw)

    def test_atomic_write_creates_no_orphan_tmp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "nested" / "config.json"
            cli.atomic_write_text(target, '{"ok": true}\n')
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})
            leftovers = list(target.parent.glob("*.tmp"))
            self.assertEqual(leftovers, [])


class TestUnifiedStandaloneUninstallAndDryRun(unittest.TestCase):
    def test_unified_mode_default_vs_standalone_and_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            all_base = sorted(cli.JURISDICTIONS.keys())

            # Unified mode with all 42 base jurisdictions -> ONE server with --countries all
            res_unified = cli.install_servers(
                all_base,
                ["3", "7"],
                uvx_cmd="/opt/homebrew/bin/uvx",
                home=fake_home,
                system_name="Darwin",
                mode="unified",
            )
            self.assertEqual(res_unified.warnings, [])
            cursor_data = json.loads((fake_home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
            lm_data = json.loads((fake_home / ".lmstudio" / "mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(list(cursor_data["mcpServers"].keys()), ["jurisatlas-mcp"])
            self.assertEqual(
                cursor_data["mcpServers"]["jurisatlas-mcp"]["args"][-2:],
                ["--countries", "all"],
            )
            self.assertEqual(list(lm_data["mcpServers"].keys()), ["jurisatlas-mcp"])

            # Standalone mode with >5 countries -> per-country servers + soft warning
            six_countries = ["at", "ch", "de", "eu", "fr", "uk"]
            res_standalone = cli.install_servers(
                six_countries,
                ["3"],
                uvx_cmd="/opt/homebrew/bin/uvx",
                home=fake_home,
                system_name="Darwin",
                mode="standalone",
            )
            self.assertEqual(len(res_standalone.warnings), 1)
            cursor_after = json.loads((fake_home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
            for code in six_countries:
                self.assertIn(f"{code}-legal-mcp", cursor_after["mcpServers"])

    def test_turkiye_extra_bundle_and_custom_bundle_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            cli.install_servers(
                ["tr", "uk", "ch"],
                ["3"],
                uvx_cmd="/usr/local/bin/uvx",
                home=fake_home,
                system_name="Darwin",
                mode="unified",
            )
            data = json.loads((fake_home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
            self.assertIn("jurisatlas-mcp", data["mcpServers"])
            self.assertIn("tr-legal-mcp", data["mcpServers"])
            self.assertEqual(
                data["mcpServers"]["jurisatlas-mcp"]["args"][-2:],
                ["--countries", "ch,uk"],
            )
            self.assertEqual(
                data["mcpServers"]["tr-legal-mcp"]["args"],
                [
                    "--from",
                    "https://github.com/jurisatlas/tr-legal-mcp/archive/refs/heads/main.zip",
                    "tr-legal-mcp",
                ],
            )

    def test_one_click_uninstall_removes_only_jurisatlas_preserves_other_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            appdata = fake_home / "AppData" / "Roaming"

            # Seed non-JurisAtlas servers across Claude, Codex, Cursor, VS Code, Antigravity, LM Studio, Continue
            claude_cfg = appdata / "Claude" / "claude_desktop_config.json"
            claude_cfg.parent.mkdir(parents=True, exist_ok=True)
            claude_cfg.write_text(
                json.dumps({"mcpServers": {"my-private-db": {"command": "python", "args": ["db.py"]}}}),
                encoding="utf-8",
            )

            codex_toml = fake_home / ".codex" / "config.toml"
            codex_toml.parent.mkdir(parents=True, exist_ok=True)
            codex_toml.write_text(
                '[model]\nname = "o3"\n\n[mcp_servers.my-codex-tool]\ncommand = "npx"\nargs = ["tool"]\n',
                encoding="utf-8",
            )

            vscode_cfg = appdata / "Code" / "User" / "mcp.json"
            vscode_cfg.parent.mkdir(parents=True, exist_ok=True)
            vscode_cfg.write_text(
                json.dumps({"servers": {"github": {"type": "stdio", "command": "npx", "args": ["gh"]}}}),
                encoding="utf-8",
            )

            lm_cfg = fake_home / ".lmstudio" / "mcp.json"
            lm_cfg.parent.mkdir(parents=True, exist_ok=True)
            lm_cfg.write_text(
                json.dumps({"mcpServers": {"local-notes": {"command": "node", "args": ["notes.js"]}}}),
                encoding="utf-8",
            )

            continue_other = fake_home / ".continue" / "mcpServers" / "custom.json"
            continue_other.parent.mkdir(parents=True, exist_ok=True)
            continue_other.write_text(
                json.dumps({"mcpServers": {"custom": {"command": "echo"}}}),
                encoding="utf-8",
            )

            # Install both unified + Türkiye bundle + legacy standalone into all clients
            all_clients = ["1", "2", "3", "4", "5", "6", "7", "8"]
            cli.install_servers(
                ["uk", "tr"],
                all_clients,
                uvx_cmd=r"C:\Users\Lawyer\.local\bin\uvx.exe",
                home=fake_home,
                system_name="Windows",
                appdata=appdata,
                mode="unified",
            )
            cli.install_servers(
                ["de"],
                ["1", "5"],
                uvx_cmd=r"C:\Users\Lawyer\.local\bin\uvx.exe",
                home=fake_home,
                system_name="Windows",
                appdata=appdata,
                mode="standalone",
            )

            # Run 1-click uninstall across all clients
            uninst = cli.uninstall_servers(
                home=fake_home,
                system_name="Windows",
                appdata=appdata,
            )
            self.assertEqual(uninst.errors, [])
            self.assertGreaterEqual(len(uninst.removed), 10)
            self.assertGreaterEqual(len(uninst.backups_created), 5)

            # Verify Claude kept my-private-db and removed all JurisAtlas entries
            claude_after = json.loads(claude_cfg.read_text(encoding="utf-8"))
            self.assertEqual(list(claude_after["mcpServers"].keys()), ["my-private-db"])

            # Verify Codex kept [model] and my-codex-tool and remains valid TOML
            codex_after = tomllib.loads(codex_toml.read_text(encoding="utf-8"))
            self.assertEqual(codex_after["model"]["name"], "o3")
            self.assertEqual(list(codex_after["mcp_servers"].keys()), ["my-codex-tool"])

            # Verify VS Code kept github and removed JurisAtlas
            vscode_after = json.loads(vscode_cfg.read_text(encoding="utf-8"))
            self.assertEqual(list(vscode_after["servers"].keys()), ["github"])

            # Verify LM Studio kept local-notes
            lm_after = json.loads(lm_cfg.read_text(encoding="utf-8"))
            self.assertEqual(list(lm_after["mcpServers"].keys()), ["local-notes"])

            # Verify Continue.dev removed JurisAtlas JSON files but preserved custom.json
            self.assertTrue(continue_other.exists())
            self.assertFalse((fake_home / ".continue" / "mcpServers" / "jurisatlas-mcp.json").exists())
            self.assertFalse((fake_home / ".continue" / "mcpServers" / "tr-legal-mcp.json").exists())

    def test_dry_run_writes_nothing_and_includes_codex_in_unique_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            res = cli.install_servers(
                ["uk", "de"],
                ["1", "2", "6"],
                uvx_cmd="uvx",
                home=fake_home,
                system_name="Darwin",
                dry_run=True,
            )
            self.assertEqual(list(fake_home.rglob("*")), [])
            self.assertTrue(any(p.endswith("config.toml") for p in res.unique_files))
            self.assertEqual(len(res.unique_files), 3)


class TestUXFlagsPromptsAndScripts(unittest.TestCase):
    def test_starter_prompts_tailored_to_selection(self) -> None:
        for selection, expected_word in (
            (["uk"], "UKSC"),
            (["eu"], "CELEX:32016R0679"),
            (["tr"], "Yargıtay"),
            (["li"], "Liechtenstein"),
        ):
            with self.subTest(selection=selection):
                prompts = cli.get_starter_prompts(selection)
                self.assertEqual(len(prompts), 3)
                joined = " ".join(title + " " + text for title, text in prompts)
                self.assertIn(expected_word, joined)

    def test_cli_flags_respect_clients_in_gui_and_prompt_when_countries_without_clients(self) -> None:
        # 1. Passing --clients without --countries/--cli should open GUI with pre-selected clients
        with mock.patch.object(cli, "_can_launch_gui", return_value=True), mock.patch.object(
            cli, "run_gui"
        ) as mock_gui:
            cli.main(["--clients", "1,3", "--dry-run"])
            mock_gui.assert_called_once()
            _, kwargs = mock_gui.call_args
            self.assertEqual(kwargs["initial_clients"], ["1", "3"])
            self.assertTrue(kwargs["dry_run"])

        # 2. Passing --countries without --clients prompts interactively instead of crashing immediately
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            real_install = cli.install_servers
            with mock.patch("builtins.input", return_value="3"), mock.patch.object(
                cli, "detect_installed_clients", return_value={k: False for k, _, _ in cli.CLIENT_SPECS}
            ), mock.patch.object(
                cli,
                "install_servers",
                side_effect=lambda codes, keys, **kw: real_install(
                    codes, keys, uvx_cmd="uvx", home=fake_home, system_name="Darwin", **kw
                ),
            ) as spy_install:
                cli.run_cli(countries_arg="uk", clients_arg=None, dry_run=True)
                spy_install.assert_called_once()
                self.assertEqual(spy_install.call_args[0][0], ["uk"])
                self.assertEqual(spy_install.call_args[0][1], ["3"])

    def test_register_custom_extra_bundle_end_to_end(self) -> None:
        saved = copy.deepcopy(cli.EXTRA_MCP_BUNDLES)
        try:
            cli.register_extra_bundle(
                "jp",
                {
                    "name": "Japan",
                    "server_name": "jp-custom-mcp",
                    "package_url": "https://example.org/jp-custom-mcp.zip",
                    "entrypoint": "jp-custom-mcp",
                    "aliases": ["japan", "nihon"],
                    "starter_prompts": [("Japan Law", "Search Japanese Civil Code Article 709.")],
                },
            )
            self.assertEqual(cli.parse_country_selection("japan"), ["jp"])
            with tempfile.TemporaryDirectory() as tmp:
                fake_home = pathlib.Path(tmp)
                cli.install_servers(["jp", "uk"], ["3"], uvx_cmd="uvx", home=fake_home, system_name="Darwin")
                cursor_cfg = fake_home / ".cursor" / "mcp.json"
                data = json.loads(cursor_cfg.read_text(encoding="utf-8"))
                self.assertIn("jp-custom-mcp", data["mcpServers"])
                self.assertIn("jurisatlas-mcp", data["mcpServers"])

                uninst = cli.uninstall_servers(home=fake_home, system_name="Darwin")
                removed_names = {srv for _, srv, _ in uninst.removed}
                self.assertEqual(removed_names, {"jp-custom-mcp", "jurisatlas-mcp"})
        finally:
            cli.EXTRA_MCP_BUNDLES.clear()
            cli.EXTRA_MCP_BUNDLES.update(saved)

    def test_timestamped_backups_never_overwrite_previous_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "mcp.json"
            cfg.write_text('{"mcpServers": {"a": {"command": "echo"}}}\n', encoding="utf-8")
            b1 = cli.upsert_json_mcp_file(cfg, {"jurisatlas-mcp": cli.build_unified_server_entry(["uk"], "uvx")})
            b2 = cli.upsert_json_mcp_file(cfg, {"jurisatlas-mcp": cli.build_unified_server_entry(["uk", "de"], "uvx")})
            self.assertIsNotNone(b1)
            self.assertIsNotNone(b2)
            self.assertNotEqual(b1, b2)
            assert b1 is not None and b2 is not None
            self.assertTrue(b1.exists())
            self.assertTrue(b2.exists())

    def test_no_macos_system_events_tcc_popup_in_source(self) -> None:
        source = (CLI_DIR / "jurisatlas_cli.py").read_text(encoding="utf-8")
        self.assertNotIn("System Events", source)
        self.assertNotIn("osascript", source)

    def test_connection_check_with_mocked_uvx(self) -> None:
        fake_proc = subprocess.CompletedProcess(args=["uvx", "--version"], returncode=0, stdout="uvx 0.13.6\n", stderr="")
        with mock.patch("subprocess.run", return_value=fake_proc):
            res = cli.test_connection(uvx_cmd="/usr/local/bin/uvx", check_server=False)
            self.assertTrue(res.ok)
            self.assertEqual(res.uvx_version, "uvx 0.13.6")

    def test_bootstrap_install_ps1_utf8_bom_and_powershell_51_ast(self) -> None:
        ps1_path = REPOS_DIR / ".github" / "install.ps1"
        if not ps1_path.exists():
            self.skipTest(f"Sibling .github repo not present in standalone checkout ({ps1_path})")
        raw = ps1_path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "install.ps1 must have a UTF-8 BOM for PowerShell 5.1")

        text = raw.decode("utf-8-sig")
        self.assertIn('$ErrorActionPreference = "Stop"', text)
        self.assertIn("Tls12", text)
        self.assertIn("$LASTEXITCODE", text)
        self.assertIn("Test-Path", text)
        # Must NOT pass unconditional --refresh
        self.assertNotRegex(text, r"uvx.*--refresh\s+--from")

        if platform.system() == "Windows":
            cmd = (
                "$tokens = $null; $errors = $null; "
                f"[void][System.Management.Automation.Language.Parser]::ParseFile('{ps1_path}', [ref]$tokens, [ref]$errors); "
                "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 } "
                "Write-Output 'AST_OK'"
            )
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"PowerShell 5.1 AST parse failed: {proc.stderr}")
            self.assertIn("AST_OK", proc.stdout)

    def test_bootstrap_install_sh_and_launchers(self) -> None:
        sh_path = REPOS_DIR / ".github" / "install.sh"
        if sh_path.exists():
            sh_raw = sh_path.read_bytes()
            self.assertNotIn(b"\r", sh_raw, "install.sh must use LF line endings only")
            sh_text = sh_raw.decode("utf-8")
            self.assertIn("command -v curl", sh_text)
            self.assertIn("command -v uvx", sh_text)
            self.assertIn("/dev/tty", sh_text)

        mac_cmd = CLI_DIR / "Click_Here_To_Install_Mac.command"
        self.assertTrue(mac_cmd.exists())
        mac_raw = mac_cmd.read_bytes()
        self.assertNotIn(b"\r", mac_raw, "Click_Here_To_Install_Mac.command must use LF line endings only")
        mac_text = mac_raw.decode("utf-8")
        self.assertIn("--managed-python 3.12", mac_text)
        self.assertIn("trap on_error ERR", mac_text)
        self.assertNotIn("System Events", mac_text)

        win_bat = CLI_DIR / "Click_Here_To_Install_Windows.bat"
        self.assertTrue(win_bat.exists())
        bat_text = win_bat.read_text(encoding="utf-8")
        self.assertIn("%LOCALAPPDATA%\\JurisAtlas", bat_text)
        self.assertIn("pause", bat_text.lower())
        self.assertNotIn("-WindowStyle Hidden", bat_text)

        # Full standard MIT license present in repos/cli/LICENSE
        license_text = (CLI_DIR / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', license_text)


class TestI18n33LanguagesAndUnicodeSafety(unittest.TestCase):
    EXPECTED_33_LANGS = {
        "en", "bg", "bs", "cnr", "cs", "da", "de", "el", "es", "et", "fi",
        "fr", "ga", "hr", "hu", "is", "it", "lb", "lt", "lv", "mk", "mt",
        "nl", "no", "pl", "pt", "ro", "sk", "sl", "sq", "sr", "sv", "tr",
    }

    def test_all_33_languages_have_100_percent_key_and_placeholder_parity(self) -> None:
        self.assertEqual(len(i18n.SUPPORTED_LANGUAGES), 33)
        self.assertEqual(set(i18n.SUPPORTED_LANGUAGES.keys()), self.EXPECTED_33_LANGS)
        self.assertEqual(set(i18n.TRANSLATIONS.keys()), self.EXPECTED_33_LANGS)

        en_table = i18n.TRANSLATIONS["en"]
        en_keys = set(en_table.keys())
        self.assertGreaterEqual(len(en_keys), 70)

        placeholder_re = re.compile(r"\{([a-zA-Z0-9_]+)\}")
        sample_kwargs = {
            "version": "2.0.0",
            "count": 43,
            "selected": 3,
            "total": 43,
            "error": "boom",
            "scope": "2 apps",
            "entries": 2,
            "files": 1,
            "mode": "Unified",
            "jurisdictions": "UK, TR",
            "codes": "UK, TR",
            "default_name": "English",
            "default_code": "en",
            "raw": "xyz",
            "keys": "1, 3",
            "max_n": 8,
            "label": "Cursor",
            "filename": "mcp.json",
        }

        for lang in sorted(self.EXPECTED_33_LANGS):
            table = i18n.TRANSLATIONS[lang]
            with self.subTest(lang=lang):
                self.assertEqual(set(table.keys()), en_keys, f"Key mismatch in language '{lang}'")
                for key, en_val in en_table.items():
                    loc_val = table[key]
                    self.assertTrue(isinstance(loc_val, str) and loc_val.strip(), f"Empty value for {lang}.{key}")
                    en_ph = set(placeholder_re.findall(en_val))
                    loc_ph = set(placeholder_re.findall(loc_val))
                    self.assertEqual(
                        loc_ph,
                        en_ph,
                        f"Placeholder mismatch in {lang}.{key}: expected {en_ph}, got {loc_ph}",
                    )
                    # Verify every string formats cleanly without KeyError/ValueError
                    formatted = i18n.t(lang, key, **{p: sample_kwargs[p] for p in en_ph})
                    self.assertTrue(formatted)

    def test_detect_system_language_env_lcid_and_locale_mappings(self) -> None:
        # Environment variable mappings
        self.assertEqual(i18n.detect_system_language(env={"LANG": "tr_TR.UTF-8"}, system_name="Linux"), "tr")
        self.assertEqual(i18n.detect_system_language(env={"LC_ALL": "de_CH.UTF-8"}, system_name="Darwin"), "de")
        self.assertEqual(i18n.detect_system_language(env={"LANG": "nb_NO.UTF-8"}, system_name="Linux"), "no")
        self.assertEqual(i18n.detect_system_language(env={"LANG": "nn_NO"}, system_name="Linux"), "no")
        self.assertEqual(i18n.detect_system_language(env={"LANG": "el_GR.UTF-8"}, system_name="Linux"), "el")
        self.assertEqual(i18n.detect_system_language(env={"LANG": "bg_BG.UTF-8"}, system_name="Linux"), "bg")
        self.assertEqual(i18n.detect_system_language(env={"LANG": "sr_ME.UTF-8"}, system_name="Linux"), "cnr")
        self.assertEqual(
            i18n.detect_system_language(env={"LC_ALL": "C", "LANGUAGE": "pl_PL:en_US"}, system_name="Linux"),
            "pl",
        )
        self.assertEqual(
            i18n.detect_system_language(env={"JURISATLAS_LANG": "fr", "LANG": "de_DE"}, system_name="Linux"),
            "fr",
        )

        # Windows LCID mappings (including 0x1A hr/sr/bs/cnr discrimination)
        for lcid, expected in (
            (0x041F, "tr"),
            (0x0407, "de"),
            (0x0807, "de"),
            (0x0408, "el"),
            (0x0402, "bg"),
            (0x0414, "no"),
            (0x0814, "no"),
            (0x041A, "hr"),
            (0x141A, "bs"),
            (0x2C1A, "cnr"),
            (0x241A, "sr"),
            (0x0411, "en"),  # Unsupported Japanese defaults cleanly to en
        ):
            with self.subTest(lcid=hex(lcid)):
                self.assertEqual(
                    i18n.detect_system_language(
                        env={},
                        system_name="Windows",
                        win_lcid=lcid,
                        locale_getter=lambda: (None, None),
                    ),
                    expected,
                )

        # locale.getlocale() fallback
        self.assertEqual(
            i18n.detect_system_language(
                env={},
                system_name="Linux",
                locale_getter=lambda: ("Turkish_Turkey", "1254"),
            ),
            "tr",
        )
        self.assertEqual(
            i18n.detect_system_language(
                env={},
                system_name="Linux",
                locale_getter=lambda: ("ja_JP", "UTF-8"),
            ),
            "en",
        )

    def test_configure_console_utf8_and_printing_multilingual_strings_never_crashes(self) -> None:
        i18n.configure_console_utf8()

        # Verify printing Turkish, Greek, Cyrillic, Polish, and Balkan UI strings onto both
        # UTF-8 and strict legacy cp1252 (with errors="replace") streams never raises UnicodeEncodeError
        sample_langs = ("tr", "el", "bg", "mk", "pl", "bs", "hr", "sr", "cnr", "sl", "sq", "cs", "ro", "hu")
        for enc in ("utf-8", "cp1252", "ascii"):
            buf = io.BytesIO()
            stream = io.TextIOWrapper(buf, encoding=enc, errors="replace")
            for lang in sample_langs:
                print(i18n.SUPPORTED_LANGUAGES[lang], file=stream)
                print(i18n.t(lang, "header_title"), file=stream)
                print(i18n.t(lang, "trust_banner"), file=stream)
                print(i18n.t(lang, "uninstall_done_body", entries=2, files=1), file=stream)
            stream.flush()
            self.assertGreater(len(buf.getvalue()), 0)

    def test_lang_cli_flows_produce_identical_ascii_safe_mcp_configs(self) -> None:
        snapshots: dict[str, dict[str, bytes]] = {}
        for lang in ("en", "tr", "el", "bg", "pl", "de"):
            with tempfile.TemporaryDirectory() as tmp:
                fake_home = pathlib.Path(tmp)
                appdata = fake_home / "AppData" / "Roaming"
                real_install = cli.install_servers
                with mock.patch.object(
                    cli,
                    "install_servers",
                    side_effect=lambda codes, keys, **kw: real_install(
                        codes,
                        keys,
                        uvx_cmd=r"C:\Users\Lawyer\.local\bin\uvx.exe",
                        home=fake_home,
                        system_name="Windows",
                        appdata=appdata,
                        **kw,
                    ),
                ), mock.patch.object(
                    cli, "detect_installed_clients", return_value={k: False for k, _, _ in cli.CLIENT_SPECS}
                ):
                    cli.run_cli(
                        countries_arg="uk,tr",
                        clients_arg="1,2,3,5,7",
                        dry_run=False,
                        lang_arg=lang,
                    )

                files_map: dict[str, bytes] = {}
                for p in sorted(fake_home.rglob("*")):
                    if p.is_file():
                        raw = p.read_bytes()
                        # Generated MCP configs MUST be 100% ASCII-safe regardless of UI language
                        raw.decode("ascii")
                        files_map[str(p.relative_to(fake_home))] = raw
                self.assertEqual(len(files_map), 5)
                snapshots[lang] = files_map

        baseline = snapshots["en"]
        for lang, files_map in snapshots.items():
            with self.subTest(lang=lang):
                self.assertEqual(files_map, baseline)

    def test_step0_language_picker_and_gui_lang_flag(self) -> None:
        # Enter keeps auto-detected default
        with mock.patch("builtins.input", return_value=""):
            self.assertEqual(cli._prompt_for_language("tr"), "tr")
        # ASCII code selection (never requires non-Latin input)
        with mock.patch("builtins.input", return_value="el"):
            self.assertEqual(cli._prompt_for_language("en"), "el")
        with mock.patch("builtins.input", return_value="bg"):
            self.assertEqual(cli._prompt_for_language("en"), "bg")
        # Numeric selection (1 = en, 33 = tr)
        with mock.patch("builtins.input", return_value="33"):
            self.assertEqual(cli._prompt_for_language("en"), "tr")
        # Unknown input preserves default safely
        with mock.patch("builtins.input", return_value="unknown_xyz"):
            self.assertEqual(cli._prompt_for_language("de"), "de")

        # --lang passed through to run_gui
        with mock.patch.object(cli, "_can_launch_gui", return_value=True), mock.patch.object(
            cli, "run_gui"
        ) as mock_gui:
            cli.main(["--lang", "tr", "--clients", "1"])
            mock_gui.assert_called_once()
            self.assertEqual(mock_gui.call_args.kwargs["initial_lang"], "tr")

    def test_windows_bat_pure_7bit_ascii_and_i18n_packaging(self) -> None:
        bat_raw = (CLI_DIR / "Click_Here_To_Install_Windows.bat").read_bytes()
        non_ascii = [(idx, b) for idx, b in enumerate(bat_raw) if b >= 128]
        self.assertEqual(non_ascii, [], f"Click_Here_To_Install_Windows.bat contains non-ASCII bytes: {non_ascii[:5]}")

        bat_text = bat_raw.decode("ascii")
        self.assertIn('PYTHONUTF8=1', bat_text)
        self.assertIn('PYTHONIOENCODING=utf-8', bat_text)
        self.assertIn("jurisatlas_i18n.py", bat_text)

        mac_text = (CLI_DIR / "Click_Here_To_Install_Mac.command").read_text(encoding="utf-8")
        self.assertIn("PYTHONUTF8=1", mac_text)
        self.assertIn("PYTHONIOENCODING=utf-8", mac_text)
        self.assertIn("LANG=", mac_text)
        self.assertIn("jurisatlas_i18n.py", mac_text)

        pyproject = tomllib.loads((CLI_DIR / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["tool"]["setuptools"]["py-modules"], ["jurisatlas_cli", "jurisatlas_i18n"])


if __name__ == "__main__":
    unittest.main()
