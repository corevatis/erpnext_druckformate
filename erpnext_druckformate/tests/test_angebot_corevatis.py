"""Gruppierung und Kennzeichnung für „Angebot Corevatis“ (ohne Frappe):
``python -m unittest erpnext_druckformate.tests.test_angebot_corevatis`` aus der Repo-Wurzel."""

import unittest

from erpnext_druckformate import angebot_corevatis as ac


def pos(code, amount, raum=None, bauteil=None, **extra):
	return {"item_code": code, "amount": amount, "cv_raum": raum, "cv_bauteil": bauteil, **extra}


class TestGruppiere(unittest.TestCase):
	def test_ohne_raum_eine_gruppe_fortlaufend(self):
		gruppen = ac.gruppiere([pos("A", 10), pos("B", 20), pos("C", 5)])
		self.assertEqual(len(gruppen), 1)
		self.assertEqual(gruppen[0]["nr"], "")
		self.assertEqual(gruppen[0]["titel"], "")
		self.assertEqual([p["nr"] for p in gruppen[0]["positionen"]], ["1", "2", "3"])
		self.assertEqual(gruppen[0]["summe"], 35)

	def test_gruppen_nach_erstem_auftreten(self):
		items = [
			pos("A", 100, "Keller 1", "Innenwand"),
			pos("B", 50, "Keller 2", "Boden"),
			pos("C", 25, "Keller 1", "Innenwand"),
			pos("D", 10),
		]
		gruppen = ac.gruppiere(items)
		self.assertEqual([g["titel"] for g in gruppen], ["Keller 1 – Innenwand", "Keller 2 – Boden", ac.GRUPPE_OHNE_ANGABE])
		self.assertEqual([g["nr"] for g in gruppen], ["1", "2", "3"])
		self.assertEqual([p["nr"] for p in gruppen[0]["positionen"]], ["1.1", "1.2"])
		self.assertEqual([p["row"]["item_code"] for p in gruppen[0]["positionen"]], ["A", "C"])
		self.assertEqual([g["summe"] for g in gruppen], [125, 50, 10])

	def test_nur_raum_oder_nur_bauteil(self):
		gruppen = ac.gruppiere([pos("A", 1, "Keller"), pos("B", 1, None, "Sockel")])
		self.assertEqual([g["titel"] for g in gruppen], ["Keller", "Sockel"])

	def test_leerzeichen_und_none_gleich(self):
		gruppen = ac.gruppiere([pos("A", 1, " Keller ", ""), pos("B", 1, "Keller", None)])
		self.assertEqual(len(gruppen), 1)

	def test_eventual_und_alternativ_nicht_in_summe(self):
		items = [
			pos("A", 100, "Keller"),
			pos("E", 40, "Keller", cv_eventualposition=1, is_alternative=1),
			pos("X", 70, "Keller", cv_alternativposition=1, is_alternative=1),
			pos("Y", 30, "Keller", is_alternative=1),
		]
		gruppe = ac.gruppiere(items)[0]
		self.assertEqual(gruppe["summe"], 100)
		self.assertEqual(
			[p["art"] for p in gruppe["positionen"]], [None, ac.EVENTUAL, ac.ALTERNATIV, ac.ALTERNATIV]
		)
		self.assertEqual([p["in_summe"] for p in gruppe["positionen"]], [True, False, False, False])

	def test_summe_gerundet_und_robust(self):
		gruppe = ac.gruppiere([pos("A", 0.1), pos("B", 0.2), pos("C", None), pos("D", "x")])[0]
		self.assertEqual(gruppe["summe"], 0.3)

	def test_leer(self):
		self.assertEqual(ac.gruppiere(None), [])
		self.assertEqual(ac.gruppiere([]), [])


class TestTexte(unittest.TestCase):
	def test_titel(self):
		self.assertEqual(ac.titel_und_bauvorhaben("Kellerabdichtung", "Weg 1, 47877 Willich"), ("Kellerabdichtung", "Weg 1, 47877 Willich"))
		self.assertEqual(ac.titel_und_bauvorhaben(None, "Weg 1, 47877 Willich"), ("Angebot – Weg 1, 47877 Willich", ""))
		self.assertEqual(ac.titel_und_bauvorhaben("  ", ""), ("Angebot", ""))

	def test_objekt_adresse(self):
		self.assertEqual(ac.objekt_adresse({"strasse": "Weg 1", "plz": "47877", "ort": "Willich"}), "Weg 1, 47877 Willich")
		self.assertEqual(ac.objekt_adresse({"strasse": None, "plz": None, "ort": "Willich"}), "Willich")
		self.assertEqual(ac.objekt_adresse(None), "")

	def test_text_als_html_maskiert(self):
		self.assertEqual(ac.text_als_html("a < b\n<script>x</script>"), "a &lt; b<br>&lt;script&gt;x&lt;/script&gt;")
		self.assertEqual(ac.text_als_html(None), "")

	def test_langtext(self):
		self.assertEqual(ac.langtext({"item_name": "A", "description": "A"}), "")
		self.assertEqual(ac.langtext({"item_name": "A", "description": "<p>A</p>"}), "")
		self.assertEqual(ac.langtext({"item_name": "A", "description": None}), "")
		# ohne Bereinigung maskiert, mit Bereinigung deren Ergebnis
		self.assertEqual(ac.langtext({"item_name": "A", "description": "<b>x</b>"}), "&lt;b&gt;x&lt;/b&gt;")
		self.assertEqual(ac.langtext({"item_name": "A", "description": "<b>x</b>"}, lambda h: "OK"), "OK")

	def test_html_zu_zeilen(self):
		self.assertEqual(ac.html_zu_zeilen("Weg 1<br>\n47877 Willich<br/>"), "Weg 1, 47877 Willich")
		self.assertEqual(ac.html_zu_zeilen("M&uuml;ller &amp; S&ouml;hne<br>"), "Müller & Söhne")
		self.assertEqual(ac.html_zu_zeilen(None), "")


if __name__ == "__main__":
	unittest.main()
