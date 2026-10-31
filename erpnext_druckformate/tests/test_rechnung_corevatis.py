"""Rechnungsart, Positionen, Summenblock, Abschlagsübersicht und § 35a-Block für „Rechnung Corevatis“
(ohne Frappe): ``python -m unittest erpnext_druckformate.tests.test_rechnung_corevatis`` aus der
Repo-Wurzel. Zahlen aus der Testrechnung in docs/7.2-schlussrechnung.md (Repo Handwerker)."""

import unittest
from datetime import date

from erpnext_druckformate import rechnung_corevatis as rc


def pos(code, qty, rate, art=None, **extra):
	return {
		"item_code": code,
		"item_name": code,
		"qty": qty,
		"rate": rate,
		"amount": round(qty * rate, 2),
		"cv_positionsart": art,
		**extra,
	}


ABSCHLAEGE = [
	{"nr": 1, "rechnung": "RE-2026-00003", "datum": "2026-11-03", "netto": 1202.74, "steuer": 228.52, "brutto": 1431.26, "bezahlt": 1},
	{"nr": 2, "rechnung": "RE-2026-00005", "datum": date(2026, 11, 10), "netto": 1603.65, "steuer": 304.69, "brutto": 1908.34, "bezahlt": 0},
]


def schlussrechnung(**extra):
	return {
		"name": "RE-2026-00007",
		"cv_schlussrechnung": 1,
		"cv_auftrag": "AB-2026-00008",
		"cv_leistung_netto": 4196.88,
		"cv_leistung_steuer": 797.41,
		"cv_leistung_brutto": 4994.29,
		"cv_abschlaege_netto": 2806.39,
		"cv_abschlaege_steuer": 533.21,
		"cv_abschlaege_brutto": 3339.60,
		"net_total": 1390.49,
		"total_taxes_and_charges": 264.19,
		"grand_total": 1654.68,
		"cv_lohnanteil_netto": 2114.67,
		"cv_lohnanteil_steuer": 401.79,
		"cv_lohnanteil_brutto": 2516.46,
		"cv_lohnanteil_prozent": 50.39,
		"cv_abschlaege": ABSCHLAEGE,
		**extra,
	}


class TestRechnungsart(unittest.TestCase):
	def test_arten(self):
		self.assertEqual(rc.rechnungsart({}), rc.RECHNUNG)
		self.assertEqual(rc.rechnungsart({"cv_abschlag": 1}), rc.ABSCHLAG)
		self.assertEqual(rc.rechnungsart({"cv_schlussrechnung": 1}), rc.SCHLUSS)
		self.assertEqual(rc.rechnungsart({"is_return": 1, "cv_schlussrechnung": 1}), rc.GUTSCHRIFT)

	def test_betreff(self):
		auftrag = {"name": "AB-2026-00008", "cv_titel": "Kellerabdichtung Musterweg 3", "transaction_date": "2026-10-20"}
		self.assertEqual(
			rc.betreff({"cv_abschlag": 1, "cv_auftrag": "AB-2026-00008", "cv_abschlag_nr": 1}, auftrag),
			("Abschlagsrechnung Nr. 1 zum Auftrag AB-2026-00008", "Kellerabdichtung Musterweg 3"),
		)
		self.assertEqual(
			rc.betreff({"cv_schlussrechnung": 1, "cv_auftrag": "AB-2026-00008"}, {"name": "AB-2026-00008", "transaction_date": date(2026, 10, 20)}),
			("Schlussrechnung zum Auftrag AB-2026-00008", "Auftrag vom 20.10.2026"),
		)
		self.assertEqual(rc.betreff({}, None), ("Rechnung", ""))
		self.assertEqual(rc.betreff({"is_return": 1, "return_against": "RE-1"}, None), ("Gutschrift zur Rechnung RE-1", ""))
		# Abschlag ohne Auftrag (fremde Rechnung mit Haken): nur die Art
		self.assertEqual(rc.betreff({"cv_abschlag": 1}, None), ("Abschlagsrechnung", ""))


class TestPositionen(unittest.TestCase):
	def test_abzug_entfaellt_und_hinweise(self):
		items = [
			pos("IA-01", 23.32, 31.88, "Auftragsposition", cv_menge_auftrag=23.32),
			pos("IA-01", 1.68, 31.88, "Mehrmenge"),
			pos("SP-08", 22.0, 23.85, "Auftragsposition", cv_menge_auftrag=23.32),
			pos("NT-1", 1, 180, "Nachtrag"),
			pos("ABSCHLAG", 1, -1202.74, "Abzug Abschlag"),
			pos("ABSCHLAG", 1, -1603.65, "Abzug Abschlag"),
		]
		p = rc.positionen(items)
		self.assertEqual([x["nr"] for x in p], ["1", "2", "3", "4"])
		self.assertEqual([x["hinweis"] for x in p], [None, "Mehrmenge", "Mindermenge", "Nachtrag"])
		self.assertEqual([x["menge_auftrag"] for x in p], [None, None, 23.32, None])
		self.assertEqual(p[0]["art"], "Auftragsposition")

	def test_ohne_felder_wie_gewoehnliche_rechnung(self):
		p = rc.positionen([{"item_code": "A", "qty": 2, "rate": 5, "amount": 10}, {"item_code": "B", "qty": 1, "rate": 1, "amount": 1}])
		self.assertEqual([(x["nr"], x["art"], x["hinweis"]) for x in p], [("1", None, None), ("2", None, None)])
		self.assertEqual(rc.positionen(None), [])

	def test_mehrmenge_in_auftragszeile(self):
		p = rc.positionen([pos("IA-05", 18.2, 31.88, "Auftragsposition", cv_menge_auftrag=16.61)])
		self.assertEqual((p[0]["hinweis"], p[0]["menge_auftrag"]), ("Mehrmenge", 16.61))


class TestSummen(unittest.TestCase):
	def test_schlussrechnung_mit_abzug(self):
		s = rc.summen(schlussrechnung())
		self.assertTrue(s["mit_abzug"])
		self.assertEqual(s["leistung"], {"netto": 4196.88, "steuer": 797.41, "brutto": 4994.29})
		self.assertEqual(s["abschlaege"], {"netto": 2806.39, "steuer": 533.21, "brutto": 3339.60})
		self.assertEqual(s["rest"], {"netto": 1390.49, "steuer": 264.19, "brutto": 1654.68})
		# Steuer je Beleg gerundet: 797,41 − 533,21 − 264,19 = 0,01
		self.assertEqual(s["rundungsdifferenz"], 0.01)
		self.assertIsNone(s["kumuliert"])
		self.assertEqual(s["bisherige_abschlaege"], [])

	def test_abschlaege_zeilen(self):
		ab = rc.abschlaege(schlussrechnung())
		self.assertEqual([(z["nr"], z["rechnung"], z["datum"], z["bezahlt"]) for z in ab], [(1, "RE-2026-00003", "03.11.2026", True), (2, "RE-2026-00005", "10.11.2026", False)])
		self.assertEqual(round(sum(z["netto"] for z in ab), 2), 2806.39)
		# Summen der Abschläge auch ohne cv_abschlaege_*-Felder aus der Tabelle
		s = rc.summen(schlussrechnung(cv_abschlaege_netto=None, cv_abschlaege_steuer=None, cv_abschlaege_brutto=None))
		self.assertEqual(s["abschlaege"], {"netto": 2806.39, "steuer": 533.21, "brutto": 3339.60})
		self.assertTrue(s["mit_abzug"])

	def test_unstimmig_faellt_auf_erpnext_summen_zurueck(self):
		# Leistung − Abschläge ≠ Rest (z. B. manuell geänderte Positionen): keine widersprüchlichen Zahlen
		s = rc.summen(schlussrechnung(net_total=1500.00))
		self.assertFalse(s["mit_abzug"])
		self.assertEqual(s["rundungsdifferenz"], 0.0)
		# Schlussrechnung ohne Abschläge: gewöhnlicher Summenblock
		self.assertFalse(rc.summen(schlussrechnung(cv_abschlaege=[], net_total=4196.88))["mit_abzug"])
		# Cent-Toleranz
		self.assertTrue(rc.summen(schlussrechnung(net_total=1390.50))["mit_abzug"])

	def test_abschlagsrechnung_kumuliert(self):
		doc = {
			"cv_abschlag": 1,
			"cv_abschlag_nr": 2,
			"cv_abschlag_prozent": 40,
			"cv_auftragssumme_netto": 4009.12,
			"cv_kumuliert_prozent": 70,
			"cv_kumuliert_netto": 2806.39,
			"net_total": 1603.65,
			"total_taxes_and_charges": 304.69,
			"grand_total": 1908.34,
			"cv_abschlaege": ABSCHLAEGE[:1],
		}
		s = rc.summen(doc)
		self.assertFalse(s["mit_abzug"])
		self.assertEqual(s["kumuliert"], {"prozent": "70", "netto": 2806.39, "auftragssumme": 4009.12, "dieser_prozent": "40"})
		self.assertEqual([z["rechnung"] for z in s["bisherige_abschlaege"]], ["RE-2026-00003"])
		self.assertEqual(rc.summen({"cv_abschlag": 1, "grand_total": 10})["kumuliert"], None)

	def test_gewoehnliche_rechnung(self):
		s = rc.summen({"net_total": 100, "total_taxes_and_charges": 19, "grand_total": 119})
		self.assertFalse(s["mit_abzug"])
		self.assertEqual(s["rest"], {"netto": 100.0, "steuer": 19.0, "brutto": 119.0})


class TestTexte(unittest.TestCase):
	def test_lohnanteil(self):
		self.assertEqual(
			rc.lohnanteil(schlussrechnung()), {"netto": 2114.67, "steuer": 401.79, "brutto": 2516.46, "prozent": "50,39"}
		)
		self.assertIsNone(rc.lohnanteil({"cv_lohnanteil_brutto": 0}))
		self.assertIsNone(rc.lohnanteil({}))
		self.assertEqual(rc.lohnanteil({"cv_lohnanteil_brutto": 62.83, "cv_lohnanteil_netto": 52.8, "cv_lohnanteil_steuer": 10.03})["prozent"], "")

	def test_leistungszeitraum(self):
		self.assertEqual(rc.leistungszeitraum("2026-11-03", date(2026, 11, 14)), "03.11.2026 – 14.11.2026")
		self.assertEqual(rc.leistungszeitraum("2026-11-03", "2026-11-03"), "03.11.2026")
		self.assertEqual(rc.leistungszeitraum(None, "2026-11-14"), "bis 14.11.2026")
		self.assertEqual(rc.leistungszeitraum("2026-11-03", None), "ab 03.11.2026")
		self.assertEqual(rc.leistungszeitraum(None, None), "")
		self.assertEqual(rc._datum("2026-11-03 10:00:00"), "03.11.2026")
		self.assertEqual(rc._datum("kein Datum"), "kein Datum")

	def test_prozent(self):
		self.assertEqual(rc._prozent(30), "30")
		self.assertEqual(rc._prozent(33.3333), "33,33")
		self.assertEqual(rc._prozent("12.50"), "12,5")
		self.assertEqual(rc._prozent(None), "0")

	def test_zahlungstext(self):
		self.assertEqual(
			rc.zahlungstext(rc.SCHLUSS, "1.654,68 €", "28.11.2026", "RE-2026-00007", True),
			"Bitte überweisen Sie den Betrag von 1.654,68 € bis zum 28.11.2026 unter Angabe der Rechnungsnummer RE-2026-00007 auf das unten genannte Konto.",
		)
		self.assertEqual(
			rc.zahlungstext(rc.RECHNUNG, "10,00 €", "", "RE-1", False),
			"Bitte überweisen Sie den Betrag von 10,00 € unter Angabe der Rechnungsnummer RE-1.",
		)
		self.assertIn("erstattet", rc.zahlungstext(rc.GUTSCHRIFT, "10,00 €", "", "GS-1", True))

	def test_bankverbindung_und_kundennummer(self):
		self.assertEqual(
			rc.bankverbindung({"bank": "Sparkasse Krefeld", "iban": "DE02 1234 5678 0123 4567 89", "bic": None, "kontoinhaber": "Hülshoff"}),
			[("Bank", "Sparkasse Krefeld"), ("IBAN", "DE02 1234 5678 0123 4567 89"), ("Kontoinhaber", "Hülshoff")],
		)
		self.assertEqual(rc.bankverbindung(None), [])
		self.assertEqual(rc.kundennummer({"customer": "K-0001", "customer_name": "Feucht"}), "K-0001")
		self.assertEqual(rc.kundennummer({"customer": "Feucht", "customer_name": "Feucht"}), "")
		self.assertEqual(rc.kundennummer({}), "")


if __name__ == "__main__":
	unittest.main()
