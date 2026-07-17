from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FONT_HASHES = {
    Path("assets/fonts/literata/Literata-Variable.ttf"):
        "b41138c9373112f32abb589cc22e8674b06ed4048b0c513be922bdd26f274440",
    Path("assets/fonts/ibm-plex-sans/IBMPlexSans-Regular.woff2"):
        "ba711a3085ff9f27440b6b9c4550cfc47c97bf36591d5da958b975bb3add8c1a",
    Path("assets/fonts/ibm-plex-sans/IBMPlexSans-SemiBold.woff2"):
        "f78048030eab62e860efa39a0df79e2e5581bf122eb95b9bc42c0b8a4988d205",
    Path("assets/fonts/ibm-plex-sans/IBMPlexSans-Bold.woff2"):
        "fa7130d854a660b39a7fc9e6e0f2dc23dba5f1346e2adea3e1fe37b6d884133d",
}
LICENSES = (
    Path("assets/fonts/literata/OFL.txt"),
    Path("assets/fonts/ibm-plex-sans/OFL.txt"),
)


class FontAssetTests(unittest.TestCase):
    def test_pinned_assets_and_licenses_are_present_and_exact(self) -> None:
        for relative_path, expected_hash in FONT_HASHES.items():
            path = ROOT / relative_path
            self.assertTrue(path.is_file(), relative_path)
            self.assertGreater(path.stat().st_size, 1_000, relative_path)
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual_hash, expected_hash, relative_path)
        for relative_path in LICENSES:
            path = ROOT / relative_path
            self.assertTrue(path.is_file(), relative_path)
            self.assertGreater(path.stat().st_size, 1_000, relative_path)

    def test_provenance_records_official_pins_paths_and_hashes(self) -> None:
        provenance = (ROOT / "assets/fonts/README.md").read_text(encoding="utf-8")
        for token in (
            "https://github.com/googlefonts/literata",
            "Pinned release: 3.103",
            "fonts/variable/Literata[opsz,wght].ttf",
            "https://github.com/IBM/plex",
            "@ibm/plex-sans@1.1.0",
            "fonts/complete/woff2/IBMPlexSans-{Regular,SemiBold,Bold}.woff2",
            "ships WOFF and WOFF2, not TTF",
        ):
            self.assertIn(token, provenance)
        for relative_path, expected_hash in FONT_HASHES.items():
            self.assertIn(relative_path.as_posix(), provenance)
            self.assertIn(expected_hash, provenance)

    def test_install_script_is_user_scoped_offline_and_complete(self) -> None:
        script = (
            ROOT / "scripts/install_attentiveslides_demo_fonts.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("XDG_DATA_HOME", script)
        self.assertIn("$HOME/.local/share", script)
        self.assertIn("fc-cache -f", script)
        for relative_path in FONT_HASHES:
            self.assertIn(relative_path.as_posix(), script)
        for forbidden in ("sudo ", "curl ", "wget ", "npm ", "git clone"):
            self.assertNotIn(forbidden, script)

    def test_ui_css_and_html_have_no_remote_font_loader(self) -> None:
        forbidden = (
            "fonts.googleapis.com",
            "fonts.gstatic.com",
            "cdn.jsdelivr.net",
            "@import url(http://",
            "@import url(https://",
        )
        candidates = (
            path
            for path in (ROOT / "modules/ui").rglob("*")
            if path.suffix.lower() in {".css", ".html"}
        )
        for path in candidates:
            content = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, content, path)


if __name__ == "__main__":
    unittest.main()
