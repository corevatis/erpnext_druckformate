"""Sync rules for the print formats (no Frappe needed): ``python -m unittest`` from the repo root.

Review Epic 0, F-1: formats must not be overwritten on every ``migrate``."""

import unittest
from pathlib import Path

from erpnext_druckformate.print_format_sources import print_formats as pf

SOURCES = Path(pf.__file__).resolve().parent


class TestPlanSync(unittest.TestCase):
	def test_missing_is_created(self):
		self.assertEqual(pf.plan_sync("s", None, None, None), "create")
		self.assertEqual(pf.plan_sync("s", None, {"source": "s", "site": "s"}, None), "create")

	def test_unchanged_is_noop(self):
		state = {"source": "s1", "site": "d1"}
		self.assertEqual(pf.plan_sync("s1", "d1", state, "Administrator"), "unchanged")

	def test_new_source_updates_unmodified_site_copy(self):
		state = {"source": "s1", "site": "d1"}
		self.assertEqual(pf.plan_sync("s2", "d1", state, "Administrator"), "update")

	def test_site_edit_is_kept(self):
		# also when Administrator edited in Desk and the source is new
		state = {"source": "s1", "site": "d1"}
		for source in ("s1", "s2"):
			self.assertEqual(pf.plan_sync(source, "d-edited", state, "Administrator"), "customized")

	def test_force_overwrites_edits(self):
		state = {"source": "s1", "site": "d1"}
		self.assertEqual(pf.plan_sync("s1", "d-edited", state, "kunde@x", force=True), "update")
		synced = {"source": "s1", "site": "s1"}
		self.assertEqual(pf.plan_sync("s1", "s1", synced, None, force=True), "unchanged")

	def test_legacy_sites_without_state(self):
		self.assertEqual(pf.plan_sync("s1", "s1", None, "kunde@x"), "adopt")
		self.assertEqual(pf.plan_sync("s1", "d-old", None, "Administrator"), "update")
		self.assertEqual(pf.plan_sync("s1", "d-edited", None, "buero@kunde.de"), "customized")


class TestContentHash(unittest.TestCase):
	def test_normalisation_db_vs_source(self):
		keys = ["a", "b", "c", "d", "e"]
		source = {"a": None, "b": 1, "c": 15.0, "d": "x\r\ny", "e": True}
		db = {"a": "", "b": 1.0, "c": 15, "d": "x\ny", "e": 1}
		self.assertEqual(pf.content_hash(source, keys), pf.content_hash(db, keys))
		self.assertNotEqual(pf.content_hash(source, keys), pf.content_hash({**db, "d": "x\ny "}, keys))

	def test_keys_exclude_identity(self):
		docs = pf.build_print_format_docs(SOURCES)
		self.assertEqual(len(docs), 7)
		for doc in docs:
			keys = pf.content_keys(doc)
			self.assertNotIn("name", keys)
			self.assertNotIn("creation", keys)
			self.assertIn("html", keys)
			self.assertIn("css", keys)


class TestMigratorTemplateInSync(unittest.TestCase):
	def test_generated_copy_matches_template(self):
		# frappe-pf-init --force copies template_files/print_formats.py; both must stay identical
		root = Path(__file__).resolve().parents[2]
		template = root / "src/erpnext_druckformate_migrator/template_files/print_formats.py"
		if not template.is_file():
			self.skipTest("migrator sources not present (installed app)")
		self.assertEqual(
			template.read_text(encoding="utf-8"), (SOURCES / "print_formats.py").read_text(encoding="utf-8")
		)


if __name__ == "__main__":
	unittest.main()
