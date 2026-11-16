# -*- coding: utf-8 -*-
import json
import pathlib
import tempfile
import unittest

import jurisatlas_cli as cli


class TestCountryAndClientParsing(unittest.TestCase):
    def test_select_all_aliases(self) -> None:
        all_codes = sorted(cli.JURISDICTIONS.keys())
        self.assertEqual(len(all_codes), 42)
        for token in ("a", "A", "all", "ALL", "*", "tümü", "tumu", "hepsi", "uk, all"):
            with self.subTest(token=token):
                self.assertEqual(cli.parse_country_selection(token), all_codes)

    def test_specific_codes_and_names(self) -> None:
        self.assertEqual(cli.parse_country_selection("uk, de; ba"), ["ba", "de", "uk"])
        self.assertEqual(cli.parse_country_selection("uk de"), ["de", "uk"])
        self.assertEqual(cli.parse_country_selection("united kingdom, germany"), ["de", "uk"])
        self.assertEqual(cli.parse_country_selection("fr-legal-mcp"), ["fr"])

    def test_single_unknown_char_does_not_fuzzy_match(self) -> None:
        self.assertEqual(cli.parse_country_selection("x"), [])
        self.assertEqual(cli.parse_country_selection("zzzz"), [])
        self.assertEqual(cli.parse_country_selection("   "), [])

    def test_client_selection(self) -> None:
        all_keys = ["1", "2", "3", "4", "5", "6", "7"]
        self.assertEqual(cli.parse_client_selection(""), all_keys)
        self.assertEqual(cli.parse_client_selection("a"), all_keys)
        self.assertEqual(cli.parse_client_selection("all"), all_keys)
        self.assertEqual(cli.parse_client_selection("1, 6, 6"), ["1", "6"])
        self.assertEqual(cli.parse_client_selection("2 3"), ["2", "3"])
        self.assertEqual(cli.parse_client_selection("99"), [])


class TestClientPathsAndInstall(unittest.TestCase):
    def test_macos_paths_include_antigravity_chatgpt_and_roo(self) -> None:
        fake_home = pathlib.Path("/tmp/fake_mac_home")
        paths = cli.get_client_paths("uk-legal-mcp", home=fake_home, system_name="Darwin")

        antigravity_paths = [str(p) for p in paths["6"][1]]
        self.assertIn(str(fake_home / ".gemini" / "antigravity" / "mcp_config.json"), antigravity_paths)
        self.assertIn(str(fake_home / ".gemini" / "config" / "mcp_config.json"), antigravity_paths)
        self.assertIn(str(fake_home / ".gemini" / "settings.json"), antigravity_paths)

        chatgpt_paths = [str(p) for p in paths["2"][1]]
        self.assertIn(
            str(fake_home / "Library" / "Application Support" / "ChatGPT" / "mcp.json"),
            chatgpt_paths,
        )

        vscode_paths = [str(p) for p in paths["5"][1]]
        self.assertTrue(any("rooveterinaryinc.roo-cline" in p for p in vscode_paths))

    def test_install_all_42_preserves_existing_and_backs_up_corrupt_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)

            # Seed existing valid Antigravity config with unrelated server
            ag_cfg = fake_home / ".gemini" / "antigravity" / "mcp_config.json"
            ag_cfg.parent.mkdir(parents=True, exist_ok=True)
            ag_cfg.write_text(
                json.dumps({"mcpServers": {"custom-tool": {"command": "echo"}}, "theme": "dark"}),
                encoding="utf-8",
            )

            # Seed invalid JSON in Cursor config to verify .bak creation
            cursor_cfg = fake_home / ".cursor" / "mcp.json"
            cursor_cfg.parent.mkdir(parents=True, exist_ok=True)
            cursor_cfg.write_text("{broken json", encoding="utf-8")

            # Seed existing Codex TOML with another section
            codex_toml = fake_home / ".codex" / "config.toml"
            codex_toml.parent.mkdir(parents=True, exist_ok=True)
            codex_toml.write_text('[model]\nname = "gpt-5"\n', encoding="utf-8")

            all_codes = sorted(cli.JURISDICTIONS.keys())
            all_clients = ["1", "2", "3", "4", "5", "6", "7"]
            cli.install_servers(
                all_codes,
                all_clients,
                uvx_cmd="/opt/homebrew/bin/uvx",
                home=fake_home,
                system_name="Darwin",
            )
            # Second run should remain idempotent in config.toml
            cli.install_servers(
                all_codes,
                all_clients,
                uvx_cmd="/opt/homebrew/bin/uvx",
                home=fake_home,
                system_name="Darwin",
            )

            ag_data = json.loads(ag_cfg.read_text(encoding="utf-8"))
            self.assertEqual(ag_data["theme"], "dark")
            self.assertIn("custom-tool", ag_data["mcpServers"])
            self.assertEqual(len(ag_data["mcpServers"]), 43)
            self.assertEqual(ag_data["mcpServers"]["uk-legal-mcp"]["command"], "/opt/homebrew/bin/uvx")

            self.assertTrue(cursor_cfg.with_name("mcp.json.bak").exists())
            cursor_data = json.loads(cursor_cfg.read_text(encoding="utf-8"))
            self.assertEqual(len(cursor_data["mcpServers"]), 42)

            toml_text = codex_toml.read_text(encoding="utf-8")
            self.assertIn('[model]\nname = "gpt-5"', toml_text)
            self.assertEqual(toml_text.count("[mcp_servers.uk-legal-mcp]"), 1)
            self.assertEqual(toml_text.count("[mcp_servers."), 42)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = pathlib.Path(tmp)
            cli.install_servers(
                ["uk", "de"],
                ["1", "2", "6"],
                uvx_cmd="uvx",
                home=fake_home,
                system_name="Darwin",
                dry_run=True,
            )
            self.assertEqual(list(fake_home.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
