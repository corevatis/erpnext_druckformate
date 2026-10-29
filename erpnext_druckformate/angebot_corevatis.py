"""Daten für das Druckformat „Angebot Corevatis“ (Corevatis, Aufgabe 4.3).

Das Format (``print_format/angebot_corevatis.jinja``) ruft ``angebot_corevatis_daten(doc)``
auf (Jinja-Methode, ``hooks.jinja``). Die Gruppierung und Nummerierung der Positionen liegt
hier statt im Template, damit sie ohne Site testbar ist (``tests/test_angebot_corevatis.py``).

Felder aus ``corevatis_erpnext`` (Custom Fields, Aufgabe 4.1) werden nur über ``doc.get(...)``
gelesen: ohne die App druckt das Format wie ein gewöhnliches Angebot (eine Gruppe, Titel
„Angebot“, keine Vorbemerkung, kein Garantiehinweis).

- Quotation: ``cv_titel``, ``cv_objekt`` (Link Objekt aus ``corevatis``), ``cv_vorbemerkung``
  (Text Editor), ``cv_garantiehinweis`` (Small Text)
- Quotation Item: ``cv_raum``, ``cv_bauteil`` (Gruppe), ``cv_eventualposition``,
  ``cv_alternativposition`` (Kennzeichnung)

Summen: Eventual- und Alternativpositionen stehen nicht in der Angebotssumme. Die Summen des
Formats sind die von ERPNext (``net_total``, Steuerzeilen, ``grand_total``); ERPNext lässt
Positionen mit ``is_alternative`` aus allen Summen und Steuern heraus. Die Gruppensummen
rechnet dieses Modul aus ``amount`` der übrigen Positionen, ihre Summe ist ``doc.total``.
"""

from __future__ import annotations

import re
from html import escape, unescape

GRUPPE_OHNE_ANGABE = "Allgemeine Leistungen"
EVENTUAL = "Eventualposition"
ALTERNATIV = "Alternativposition"
# Benutzer, die nicht als Ansprechpartner auf einem Angebot stehen sollen
TECHNISCHE_BENUTZER = frozenset({"Administrator", "Guest"})


def _text(value) -> str:
	return "" if value is None else str(value).strip()


def _zahl(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def positionsart(row) -> str | None:
	"""``Eventualposition``, ``Alternativposition`` oder ``None`` (normale Position)."""
	if row.get("cv_eventualposition"):
		return EVENTUAL
	if row.get("cv_alternativposition") or row.get("is_alternative"):
		return ALTERNATIV
	return None


def in_summe(row) -> bool:
	"""Zählt die Position zur Angebotssumme? Nein bei Eventual- und Alternativpositionen."""
	return positionsart(row) is None


def gruppiere(items) -> list[dict]:
	"""Positionen nach Raum/Bauteil gruppieren und nummerieren (ohne Frappe).

	Gruppen in der Reihenfolge ihres ersten Auftretens, Positionen innerhalb einer Gruppe in
	Belegreihenfolge. Nummern ``1.1, 1.2, 2.1 …``; trägt keine Position Raum oder Bauteil,
	gibt es genau eine Gruppe ohne Titel und die Nummern ``1, 2, 3 …``. Positionen ohne
	Angabe landen, sobald andere gruppiert sind, in „Allgemeine Leistungen“.

	Rückgabe je Gruppe: ``nr``, ``titel``, ``positionen`` (je ``nr``, ``row``, ``art``,
	``in_summe``) und ``summe`` (Summe ``amount`` der Positionen in der Summe).
	"""
	reihenfolge: list[tuple[str, str]] = []
	zeilen: dict[tuple[str, str], list] = {}
	for row in items or []:
		key = (_text(row.get("cv_raum")), _text(row.get("cv_bauteil")))
		if key not in zeilen:
			reihenfolge.append(key)
			zeilen[key] = []
		zeilen[key].append(row)

	gruppiert = any(any(key) for key in reihenfolge)
	gruppen = []
	for gruppen_nr, key in enumerate(reihenfolge, start=1):
		positionen = []
		summe = 0.0
		for positions_nr, row in enumerate(zeilen[key], start=1):
			art = positionsart(row)
			if art is None:
				summe += _zahl(row.get("amount"))
			positionen.append(
				{
					"nr": f"{gruppen_nr}.{positions_nr}" if gruppiert else str(positions_nr),
					"row": row,
					"art": art,
					"in_summe": art is None,
				}
			)
		gruppen.append(
			{
				"nr": str(gruppen_nr) if gruppiert else "",
				"titel": " – ".join(teil for teil in key if teil) or (GRUPPE_OHNE_ANGABE if gruppiert else ""),
				"positionen": positionen,
				"summe": round(summe, 2),
			}
		)
	return gruppen


def html_zu_zeilen(value) -> str:
	"""HTML (z. B. Adressanzeige mit ``<br>``) als einzeilige Adresse: „Straße 1, 12345 Ort“.

	Ergebnis ist **reiner Text** (Entities aufgelöst): im Format nur mit ``| e`` ausgeben."""
	text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", _text(value), flags=re.IGNORECASE)
	text = unescape(re.sub(r"<[^>]+>", "", text))
	return ", ".join(zeile.strip() for zeile in text.splitlines() if zeile.strip())


def objekt_adresse(objekt: dict | None) -> str:
	if not objekt:
		return ""
	ort = " ".join(teil for teil in (_text(objekt.get("plz")), _text(objekt.get("ort"))) if teil)
	return ", ".join(teil for teil in (_text(objekt.get("strasse")), ort) if teil)


def text_als_html(value) -> str:
	"""Klartext (z. B. ``Small Text``) maskiert, Zeilenumbrüche als ``<br>``."""
	return "<br>".join(escape(zeile) for zeile in _text(value).splitlines())


def langtext(row, sanitize=None) -> str:
	"""Langtext einer Position als bereinigtes HTML, leer wenn er nur den Kurztext wiederholt.

	``sanitize``: HTML-Bereinigung (im Format ``frappe.utils.sanitize_html``); ohne wird
	der Text als reiner Text maskiert."""
	beschreibung = _text(row.get("description"))
	if not beschreibung or html_zu_zeilen(beschreibung) == _text(row.get("item_name")):
		return ""
	if sanitize:
		return sanitize(beschreibung)
	return escape(beschreibung)


def titel_und_bauvorhaben(cv_titel, adresse: str) -> tuple[str, str]:
	"""Betreff des Angebots und Zeile „Bauvorhaben“.

	Mit ``cv_titel``: Titel = ``cv_titel``, Bauvorhaben = Objektadresse. Ohne: Titel =
	„Angebot“ + Objektadresse, keine zweite Zeile."""
	titel = _text(cv_titel)
	if titel:
		return titel, adresse
	return ("Angebot – " + adresse) if adresse else "Angebot", ""


def angebot_corevatis_daten(doc) -> dict:
	"""Jinja-Methode für „Angebot Corevatis“: alles, was über die Standardfelder hinausgeht."""
	import frappe

	objekt = None
	objekt_name = doc.get("cv_objekt")
	if objekt_name and frappe.db.exists("DocType", "Objekt"):
		objekt = frappe.db.get_value("Objekt", objekt_name, ["titel", "strasse", "plz", "ort"], as_dict=True)
	adresse = objekt_adresse(objekt)
	if not adresse and doc.get("shipping_address_name") != doc.get("customer_address"):
		# Lieferadresse = Baustelle, wenn sie von der Rechnungsadresse abweicht
		adresse = html_zu_zeilen(doc.get("shipping_address"))
	titel, bauvorhaben = titel_und_bauvorhaben(doc.get("cv_titel"), adresse)

	ansprechpartner = ""
	if doc.get("owner") and doc.owner not in TECHNISCHE_BENUTZER:
		ansprechpartner = _text(frappe.utils.get_fullname(doc.owner))

	sanitize_html = frappe.utils.sanitize_html

	gruppen = gruppiere(doc.get("items"))
	for gruppe in gruppen:
		for position in gruppe["positionen"]:
			position["langtext"] = langtext(position["row"], sanitize_html)
	# Ausgabe im Format: reine Texte (Titel, Bauvorhaben, Gruppen, Namen) mit „| e“,
	# HTML-Felder (Vorbemerkung, Langtext) hier bereinigt (Security-Review 4.3)
	return {
		"titel": titel,
		"bauvorhaben": bauvorhaben,
		"vorbemerkung": sanitize_html(_text(doc.get("cv_vorbemerkung"))),
		"garantiehinweis": text_als_html(doc.get("cv_garantiehinweis")),
		"kundennummer": _text(doc.get("party_name")) if doc.get("quotation_to") == "Customer" else "",
		"ansprechpartner": ansprechpartner,
		"gruppen": gruppen,
		"mit_gruppen": bool(gruppen and gruppen[0]["nr"]),
		"ausserhalb_summe": any(not p["in_summe"] for g in gruppen for p in g["positionen"]),
	}
