"""Print format sync on a real site (Review Epic 0, F-1): ``bench run-tests --app erpnext_druckformate``.

- a second sync (= every ``migrate``) is a no-op: no delete/insert, ``modified`` unchanged;
- Desk edits are kept, ``force=True`` restores the shipped version;
- a new source version updates formats the site did not change;
- sites synced by the old hook (no stored state) are adopted.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_druckformate.print_format_sources import print_formats as pf

NAMES = (
	"Angebot",
	"Angebot Corevatis",
	"Ausgangsrechnung",
	"Auftragsbestätigung",
	"Lieferschein",
	"Angebotsanfrage",
	"Bestellung",
	"Mahnung",
)


def modified_of_all() -> dict:
	return {name: str(frappe.db.get_value("Print Format", name, "modified")) for name in NAMES}


class TestPrintFormatSync(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		pf.sync_print_formats(force=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		pf.sync_print_formats(force=True)
		frappe.db.commit()

	def test_all_formats_installed(self):
		for name in NAMES:
			self.assertTrue(frappe.db.exists("Print Format", name), name)

	def test_second_sync_is_noop(self):
		before = modified_of_all()
		versions = frappe.db.count("Version", {"ref_doctype": "Print Format"})
		report = pf.sync_print_formats()
		self.assertEqual(sorted(report["unchanged"]), sorted(NAMES), report)
		self.assertEqual(report["update"] + report["create"] + report["customized"], [])
		self.assertEqual(modified_of_all(), before)
		self.assertEqual(frappe.db.count("Version", {"ref_doctype": "Print Format"}), versions)

	def test_desk_edit_is_kept(self):
		doc = frappe.get_doc("Print Format", "Angebot")
		doc.css = (doc.css or "") + "\n/* Anpassung des Kunden */"
		doc.save()  # as Administrator: the stored hash, not modified_by, detects the edit
		report = pf.sync_print_formats()
		self.assertIn("Angebot", report["customized"])
		self.assertNotIn("Angebot", report["update"])
		self.assertIn("Anpassung des Kunden", frappe.db.get_value("Print Format", "Angebot", "css"))

		report = pf.sync_print_formats(force=True)
		self.assertIn("Angebot", report["update"])
		self.assertNotIn("Anpassung des Kunden", frappe.db.get_value("Print Format", "Angebot", "css"))
		self.assertIn("Angebot", pf.sync_print_formats()["unchanged"])

	def test_force_via_site_config(self):
		frappe.db.set_value("Print Format", "Mahnung", "css", "/* geändert */")
		with patch.dict(frappe.local.conf, {pf.FORCE_SYNC_CONF_KEY: 1}):
			report = pf.sync_print_formats()
		self.assertIn("Mahnung", report["update"])
		self.assertNotEqual(frappe.db.get_value("Print Format", "Mahnung", "css"), "/* geändert */")

	def test_new_source_updates_unchanged_format(self):
		real_build = pf.build_print_format_docs

		def build_new_version(root):
			docs = real_build(root)
			for doc in docs:
				if doc["name"] == "Lieferschein":
					doc["html"] += "\n{# neue Vorlagenversion #}"
			return docs

		with patch.object(pf, "build_print_format_docs", side_effect=build_new_version):
			report = pf.sync_print_formats()
		self.assertEqual(report["update"], ["Lieferschein"], report)
		self.assertIn("neue Vorlagenversion", frappe.db.get_value("Print Format", "Lieferschein", "html"))
		# back to the shipped source: site copy is what we wrote last -> updated again
		self.assertEqual(pf.sync_print_formats()["update"], ["Lieferschein"])

	def test_legacy_site_without_state(self):
		frappe.db.set_global(pf.STATE_KEY_PREFIX + "Bestellung", "")
		self.assertIn("Bestellung", pf.sync_print_formats()["adopt"])
		self.assertIsNotNone(pf._get_state("Bestellung"))

		# old hook state + edit by a customer user -> kept
		frappe.db.set_global(pf.STATE_KEY_PREFIX + "Bestellung", "")
		frappe.db.set_value(
			"Print Format", "Bestellung", {"css": "/* Kunde */", "modified_by": "Guest"}, update_modified=False
		)
		self.assertIn("Bestellung", pf.sync_print_formats()["customized"])
		self.assertEqual(frappe.db.get_value("Print Format", "Bestellung", "css"), "/* Kunde */")


class TestAngebotCorevatisSync(IntegrationTestCase):
	"""Aufgabe 4.3: das neue Format folgt denselben Regeln wie die übrigen."""

	NAME = "Angebot Corevatis"

	def setUp(self):
		frappe.set_user("Administrator")
		pf.sync_print_formats(force=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		pf.sync_print_formats(force=True)
		frappe.db.commit()

	def test_installiert_neben_angebot(self):
		self.assertEqual(frappe.db.get_value("Print Format", self.NAME, "doc_type"), "Quotation")
		self.assertEqual(frappe.db.get_value("Print Format", "Angebot", "doc_type"), "Quotation")
		self.assertEqual(frappe.db.get_value("Print Format", self.NAME, "standard"), "No")

	def test_unveraendert_wird_aktualisiert(self):
		real_build = pf.build_print_format_docs

		def neue_fassung(root):
			docs = real_build(root)
			for doc in docs:
				if doc["name"] == self.NAME:
					doc["html"] += "\n{# neue Fassung #}"
			return docs

		with patch.object(pf, "build_print_format_docs", side_effect=neue_fassung):
			report = pf.sync_print_formats()
		self.assertEqual(report["update"], [self.NAME], report)
		self.assertIn("neue Fassung", frappe.db.get_value("Print Format", self.NAME, "html"))

	def test_geaendert_bleibt(self):
		doc = frappe.get_doc("Print Format", self.NAME)
		doc.html += "\n<!-- Anpassung Büro -->"
		doc.save()
		real_build = pf.build_print_format_docs

		def neue_fassung(root):
			docs = real_build(root)
			for d in docs:
				if d["name"] == self.NAME:
					d["html"] += "\n{# neue Fassung #}"
			return docs

		with patch.object(pf, "build_print_format_docs", side_effect=neue_fassung):
			report = pf.sync_print_formats()
		self.assertIn(self.NAME, report["customized"])
		html = frappe.db.get_value("Print Format", self.NAME, "html")
		self.assertIn("Anpassung Büro", html)
		self.assertNotIn("neue Fassung", html)

	def test_jinja_methode_registriert(self):
		from frappe.utils.jinja import get_jenv

		self.assertIn("angebot_corevatis_daten", get_jenv().globals)
