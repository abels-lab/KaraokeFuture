import re
import unittest
from pathlib import Path

class TestTvLayout(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.html_path = self.root / "static" / "tv.html"
        self.css_path = self.root / "static" / "theme.css"
        self.assertTrue(self.html_path.exists())
        self.assertTrue(self.css_path.exists())
        with open(self.html_path, "r", encoding="utf-8") as f:
            self.html = f.read()
        with open(self.css_path, "r", encoding="utf-8") as f:
            self.css = f.read()
        self.html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', self.html))

    def test_dom_ids_coverage(self):
        files_to_check = [
            "static/tv.js",
            "static/tv-side.js",
            "static/agent.js",
            "static/game-panel.js",
            "static/guide.js",
            "static/intro-run.js",
            "static/stage.js",
            "static/mic-setup.js",
        ]
        for rel_path in files_to_check:
            file_path = self.root / rel_path
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            dollar_calls = set(re.findall(r'\$\(["\']([^"\']+)["\']\)', code))
            by_id = set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', code))
            needed_ids = dollar_calls | by_id
            missing = needed_ids - self.html_ids
            self.assertEqual(missing, set(), f"{rel_path} has missing DOM IDs: {missing}")

    def test_three_column_grid_css(self):
        # Verify 3-column workstation grid definition exists in theme.css
        self.assertIn("body.tv #tv-layout", self.css)
        self.assertIn("grid-template-columns:", self.css)
        self.assertIn("minmax(18rem, 23rem)", self.css)
        self.assertIn("minmax(0, 1fr)", self.css)
        self.assertIn("var(--side-panel-width, 26rem)", self.css)

    def test_column_elements_present(self):
        # Column 1 (Left)
        self.assertIn('id="qr"', self.html)
        self.assertIn('id="qr-url"', self.html)
        self.assertIn('id="agent-drawer"', self.html)
        self.assertIn('id="agent-messages"', self.html)
        self.assertIn('id="agent-input"', self.html)

        # Column 2 (Center)
        self.assertIn('id="idle"', self.html)
        self.assertIn('id="idle-mic"', self.html)
        self.assertIn('id="loading"', self.html)
        self.assertIn('id="stage"', self.html)
        self.assertIn('id="monitor"', self.html)
        self.assertIn('id="stage-video"', self.html)
        self.assertIn('id="line-main"', self.html)
        self.assertIn('id="line-next"', self.html)
        self.assertIn('id="btn-video"', self.html)
        self.assertIn('id="btn-lyrics"', self.html)
        self.assertIn('id="open-screen"', self.html)
        self.assertIn('id="game-controls"', self.html)
        self.assertIn('id="open-mics"', self.html)

        # Column 3 (Right)
        self.assertIn('id="np-singer"', self.html)
        self.assertIn('id="np-title"', self.html)
        self.assertIn('id="seek"', self.html)
        self.assertIn('id="btn-play"', self.html)
        self.assertIn('id="btn-prev"', self.html)
        self.assertIn('id="btn-next"', self.html)
        self.assertIn('id="guide"', self.html)
        self.assertIn('id="tv-sidebar"', self.html)
        self.assertIn('id="tab-side-upcoming"', self.html)
        self.assertIn('id="tab-side-played"', self.html)
        self.assertIn('id="tab-side-all"', self.html)
        self.assertIn('id="side-lists"', self.html)

    def test_idle_does_not_override_display(self):
        # `#idle` in theme.css MUST NOT define display: flex (or any display override)
        # because ID selectors have higher specificity than Tailwind's .hidden (display: none).
        # Tailwind classes (flex / hidden) must control display on both /tv and /screen.
        matches = re.findall(r'(#idle\b[^{]*\{[^}]*\})', self.css)
        for rule in matches:
            self.assertNotIn("display:", rule, f"Rule '{rule}' must not override display on #idle")

        # Also ensure control-panel specific idle rules in theme.css are scoped with #tv-layout
        self.assertIn("#tv-layout #idle-mic", self.css)
        self.assertIn("#tv-layout #idle.has-loading", self.css)

    def test_preview_screen_clean_box(self):
        # Ensure the extra '1:1 Projector Screen Mirror' label was removed
        self.assertNotIn("1:1 Projector Screen Mirror", self.html)

        # Ensure #idle and #stage have expected Tailwind flex/hidden classes
        self.assertRegex(self.html, r'<section\s+id="idle"\s+class="[^"]*\bflex\b')
        self.assertRegex(self.html, r'<section\s+id="stage"\s+class="[^"]*\bhidden\b[^"]*\bflex\b')

    def test_guide_control_is_div_and_slider_classes(self):
        # Verify #guide-control is a <div> (not <label>) to prevent click interference with dragging
        self.assertRegex(self.html, r'<div\s+id="guide-control"')
        self.assertNotRegex(self.html, r'<label\s+id="guide-control"')

        # Verify #guide has guide-slider and 25% width Tailwind classes
        self.assertRegex(self.html, r'<input\s+id="guide"[^>]*class="[^"]*guide-slider[^"]*"')
        self.assertRegex(self.html, r'<input\s+id="guide"[^>]*class="[^"]*w-1/4[^"]*"')
        self.assertRegex(self.html, r'<input\s+id="guide"[^>]*class="[^"]*min-w-\[5\.5rem\][^"]*"')
        self.assertRegex(self.html, r'<input\s+id="guide"[^>]*class="[^"]*max-w-\[7\.5rem\][^"]*"')

    def test_control_panel_columns_and_cards(self):
        # Columns
        self.assertIn('id="col-left"', self.html)
        self.assertIn('id="col-center"', self.html)
        self.assertIn('id="col-right"', self.html)

        # Cards and panels
        self.assertIn('id="qr-card"', self.html)
        self.assertIn('id="preview-card"', self.html)
        self.assertIn('id="display-panel"', self.html)
        self.assertIn('id="nav-panel"', self.html)
        self.assertIn('id="now-playing-card"', self.html)
        self.assertIn('id="custom-controls"', self.html)
        self.assertIn('id="custom-nav-controls"', self.html)
        self.assertIn('id="custom-transport-controls"', self.html)

        # Scripts
        self.assertIn('src="/static/tv-ui.js"', self.html)

    def test_guide_slider_css(self):
        # CSS rules for .guide-slider and smiley thumb
        self.assertIn(".guide-slider", self.css)
        self.assertIn("width: var(--guide-slider-width, 25%)", self.css)
        self.assertIn("min-width: 5.5rem", self.css)
        self.assertIn("max-width: 7.5rem", self.css)
        self.assertIn("body.smiley-guide", self.css)


    def test_funding_and_support_links(self):
        repo_root = self.root.parent
        # 1. .github/FUNDING.yml exists
        funding_file = repo_root / ".github" / "FUNDING.yml"
        self.assertTrue(funding_file.exists(), "FUNDING.yml must exist at repo root .github/")
        funding_text = funding_file.read_text(encoding="utf-8")
        self.assertIn("github:", funding_text)
        self.assertIn("abels-lab", funding_text)

        # 2. support_url and show_support_on_remote exist in core/settings.py client_values()
        from core import settings
        client_vals = settings.client_values()
        self.assertIn("support_url", client_vals)
        self.assertIn("show_support_on_remote", client_vals)
        self.assertEqual(client_vals["support_url"], "https://github.com/sponsors/abels-lab")
        self.assertTrue(client_vals["show_support_on_remote"])

        # 3. #support-link is present in static/tv.html, static/settings.html, and static/remote.html
        tv_html = (self.root / "static" / "tv.html").read_text(encoding="utf-8")
        settings_html = (self.root / "static" / "settings.html").read_text(encoding="utf-8")
        remote_html = (self.root / "static" / "remote.html").read_text(encoding="utf-8")

        self.assertIn('id="support-link"', tv_html)
        self.assertIn('id="support-link"', settings_html)
        self.assertIn('id="support-link"', remote_html)
        self.assertIn('id="support-footer"', remote_html)

    def test_desktop_wrapper_files(self):
        import json
        repo_root = self.root.parent
        # 4. desktop/package.json, desktop/main.js, desktop/preload.js, start-desktop.bat, and start-desktop.ps1 exist and are valid
        pkg_json_file = repo_root / "desktop" / "package.json"
        self.assertTrue(pkg_json_file.exists(), "desktop/package.json must exist")
        with open(pkg_json_file, "r", encoding="utf-8") as f:
            pkg_data = json.load(f)
        self.assertEqual(pkg_data["name"], "ai-karaoke-desktop")
        self.assertIn("electron", pkg_data.get("devDependencies", {}))

        main_js_file = repo_root / "desktop" / "main.js"
        self.assertTrue(main_js_file.exists(), "desktop/main.js must exist")
        main_js = main_js_file.read_text(encoding="utf-8")
        self.assertIn("autoplay-policy", main_js)
        self.assertIn("no-user-gesture-required", main_js)
        self.assertIn("getAllDisplays", main_js)
        self.assertIn("setPermissionRequestHandler", main_js)

        preload_js_file = repo_root / "desktop" / "preload.js"
        self.assertTrue(preload_js_file.exists(), "desktop/preload.js must exist")
        preload_js = preload_js_file.read_text(encoding="utf-8")
        self.assertIn("contextBridge", preload_js)
        self.assertIn("karaokeDesktop", preload_js)

        start_bat_file = repo_root / "start-desktop.bat"
        self.assertTrue(start_bat_file.exists(), "start-desktop.bat must exist")

        start_ps1_file = repo_root / "start-desktop.ps1"
        self.assertTrue(start_ps1_file.exists(), "start-desktop.ps1 must exist")
        ps1_text = start_ps1_file.read_text(encoding="utf-8")
        self.assertIn("electron", ps1_text)


if __name__ == "__main__":
    unittest.main()
