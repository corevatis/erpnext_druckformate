"""Mahnstufe, Zeilen, Zahlungsfrist für „Mahnung Corevatis“ (ohne Frappe):
``python -m unittest erpnext_druckformate.tests.test_mahnung_corevatis`` aus der Repo-Wurzel."""

import unittest
from datetime import date

from erpnext_druckformate import mahnung_corevatis as mc


class TestStufe(unittest.TestCase):
	def test_bezeichnung(self):
		self.assertEqual(mc.stufe_bezeichnung("1. Mahnung - HST", "1. Mahnung"), "1. Mahnung")
		self.assertEqual(mc.stufe_bezeichnung("Zahlungserinnerung - HST", None), "Zahlungserinnerung")
		self.assertEqual(mc.stufe_bezeichnung("Erste Mahnung", None), "Erste Mahnung")
		self.assertEqual(mc.stufe_bezeichnung(None, None, 2), "2. Mahnung")
		self.assertEqual(mc.stufe_bezeichnung(None, None, None), "Mahnung")
		self.assertEqual(mc.stufe_bezeichnung(None, None, 7), "Mahnung")


class TestFristUndText(unittest.TestCase):
	def test_zahlungsfrist(self):
		self.assertEqual(mc.zahlungsfrist("2026-11-20", "2026-11-30"), "30.11.2026")
		self.assertEqual(mc.zahlungsfrist(date(2026, 11, 20), None), "27.11.2026")
		self.assertEqual(mc.zahlungsfrist("2026-11-20", None, tage=10), "30.11.2026")
		self.assertEqual(mc.zahlungsfrist(None, None), "")

	def test_zahlungstext(self):
		text = mc.zahlungstext("Zahlungserinnerung", "1.431,26 €", "27.11.2026", True)
		self.assertIn("Gesamtbetrag von 1.431,26 € bis zum 27.11.2026 auf das unten genannte Konto.", text)
		self.assertIn("gegenstandslos", text)
		text = mc.zahlungstext("2. Mahnung", "1.436,26 €", "", False)
		self.assertEqual(text, "Bitte überweisen Sie den Gesamtbetrag von 1.436,26 €.")

	def test_rechnungsbezeichnung(self):
		self.assertEqual(mc.rechnungsbezeichnung({"cv_abschlag": 1, "cv_abschlag_nr": 1, "cv_auftrag": "AB-1"}), "Abschlagsrechnung Nr. 1 zum Auftrag AB-1")
		self.assertEqual(mc.rechnungsbezeichnung({"cv_schlussrechnung": 1, "cv_auftrag": "AB-1"}), "Schlussrechnung zum Auftrag AB-1")
		self.assertEqual(mc.rechnungsbezeichnung({"cv_abschlag": 1}), "Abschlagsrechnung")
		self.assertEqual(mc.rechnungsbezeichnung({}), "Rechnung")
		self.assertEqual(mc.rechnungsbezeichnung(None), "Rechnung")


class TestZeilenUndSummen(unittest.TestCase):
	def test_zeilen(self):
		rows = [
			{"sales_invoice": "RE-2026-00003", "due_date": "2026-11-17", "overdue_days": "9", "outstanding": 1431.26, "dunning_level": 1},
			{"sales_invoice": "RE-2026-00005", "due_date": date(2026, 11, 24), "overdue_days": 2, "outstanding": "1908.34"},
		]
		rechnungen = {"RE-2026-00003": {"posting_date": "2026-11-03", "cv_abschlag": 1, "cv_abschlag_nr": 1, "cv_auftrag": "AB-2026-00008"}}
		z = mc.zeilen(rows, rechnungen)
		self.assertEqual(
			z[0],
			{
				"rechnung": "RE-2026-00003",
				"bezeichnung": "Abschlagsrechnung Nr. 1 zum Auftrag AB-2026-00008",
				"rechnungsdatum": "03.11.2026",
				"faellig": "17.11.2026",
				"tage": 9,
				"offen": 1431.26,
				"stufe": 1,
			},
		)
		self.assertEqual((z[1]["bezeichnung"], z[1]["rechnungsdatum"], z[1]["faellig"], z[1]["tage"], z[1]["offen"], z[1]["stufe"]), ("Rechnung", "", "24.11.2026", 2, 1908.34, 1))
		self.assertEqual(mc.zeilen(None), [])

	def test_summen(self):
		s = mc.summen({"total_outstanding": 1431.26, "dunning_fee": 5, "total_interest": 0, "grand_total": 1436.26})
		self.assertEqual(s, {"offen": 1431.26, "gebuehr": 5.0, "zinsen": 0.0, "gesamt": 1436.26})
		self.assertEqual(mc.summen({}), {"offen": 0.0, "gebuehr": 0.0, "zinsen": 0.0, "gesamt": 0.0})


if __name__ == "__main__":
	unittest.main()
