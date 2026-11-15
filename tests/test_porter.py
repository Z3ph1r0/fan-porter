"""Controlli sulle cose che si sono già rotte. Si lancia con il Python del programma."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import (  # noqa: E402
    ZIP_LIMIT_BYTES,
    PrepareError,
    _guard_zip_budget,
    detect_family,
    match_input_profile,
    match_profile,
)
from splash import PNG_LEN, render_loading_png  # noqa: E402


def profiles():
    found = []
    for directory in sorted(p for p in (ROOT / "profili").iterdir() if p.is_dir()):
        path = directory / "perfil.json"
        if path.is_file():
            found.append((directory.name, directory, json.loads(path.read_text(encoding="utf-8"))))
    return found


class MatchTests(unittest.TestCase):
    def test_rejuvenation_is_not_reborn(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / "Scripts").mkdir()
            (game / "Scripts" / "ScriptLoader.rb").write_text("module ScriptLoader\nend\n", encoding="utf-8")
            rejuv = match_profile(game, "Pokemon Rejuvenation", profiles())
            reborn = match_profile(game, "Pokemon Reborn", profiles())
        self.assertEqual(rejuv[0], "pokemon-rejuvenation")
        self.assertEqual(reborn[0], "pokemon-reborn")

    def test_scriptloader_alone_does_not_steal_a_titled_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / "Scripts").mkdir()
            (game / "Scripts" / "ScriptLoader.rb").write_text("# loader\n", encoding="utf-8")
            matched = match_profile(game, "Pokemon Relict", profiles())
        self.assertEqual(matched[0], "relict")


class FamilyTests(unittest.TestCase):
    def test_ruby3_dll_wins_over_rgss102(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / "x64-msvcrt-ruby300.dll").write_bytes(b"")
            (game / "RGSS102E.dll").write_bytes(b"")
            self.assertEqual(detect_family(game, "Game"), "ruby31")

    def test_rgss102_alone_is_ruby18(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / "RGSS102E.dll").write_bytes(b"")
            self.assertEqual(detect_family(game, "Game"), "ruby18")

    def test_realidea_forces_ruby18_even_with_a_ruby3_dll(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "Realidea System"
            game.mkdir()
            (game / "x64-msvcrt-ruby300.dll").write_bytes(b"")
            (game / "RGSS102E.dll").write_bytes(b"")
            self.assertEqual(detect_family(game, "Game"), "ruby31")
            spec = match_input_profile(game, "Realidea System")
        self.assertEqual(spec["family"], "ruby18")
        self.assertEqual(spec["tasti"], "rgss")

    def test_reminiscencia_stays_ruby31(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "Reminiscencia"
            game.mkdir()
            (game / "x64-msvcrt-ruby310.dll").write_bytes(b"")
            (game / "RGSS102E.dll").write_bytes(b"")
            spec = match_input_profile(game, "Reminiscencia")
            seen = detect_family(game, "Game")
        self.assertEqual(seen, "ruby31")
        self.assertEqual(spec["family"], "ruby31")


class ZipTests(unittest.TestCase):
    def test_over_two_gigabytes_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            data = game / "Data"
            data.mkdir()
            big = data / "Audio.rxdata"
            with big.open("wb") as handle:
                handle.seek(ZIP_LIMIT_BYTES)
                handle.write(b"x")
            with self.assertRaises(PrepareError):
                _guard_zip_budget(game, ["Data"], set())


class SplashTests(unittest.TestCase):
    def test_loading_png_is_the_engine_slot(self):
        self.assertEqual(len(render_loading_png("Pokemon Relict", lang="it")), PNG_LEN)
        self.assertEqual(len(render_loading_png("Pokemon Relict", lang="en")), PNG_LEN)
        self.assertEqual(PNG_LEN, 21405)


if __name__ == "__main__":
    unittest.main()
