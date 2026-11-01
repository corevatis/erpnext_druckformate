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

Material und Lohn (Handwerker#105, ``corevatis_erpnext``): je Position ``cv_materialanteil`` und
``cv_lohnanteil`` (Zeile „Material … · Lohn …“ unter dem Langtext, nur die Teile ungleich 0 -
Regiestunde nur „Lohn …“, reines Material nur „Material …“; abschaltbar mit der Einstellung „Lohn und
Material je Position ausweisen“), am Kopf ``cv_material_netto/_brutto`` und ``cv_lohn_netto/_brutto``
(Zeilen „davon Arbeitskosten (§ 35a EStG, begünstigt)“ und „davon Materialkosten“ unter den Summen,
``davon_zeilen``). „Arbeitskosten“ ist der Wortlaut von § 35a Abs. 3 EStG: Arbeitslohn einschließlich
Maschinen- und Fahrtkosten, ohne Material. Ohne die Felder (ältere Belege, ohne App) entfallen beide
Ausweise. Gleiche Hilfen für die Rechnung und - über ``lohn_material_daten`` - die Auftragsbestätigung.

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
# Einstellung „Lohn und Material je Position ausweisen“ (corevatis_erpnext, Standard an)
EINSTELLUNGEN_ABRECHNUNG = "Corevatis Abrechnung Einstellungen"
LOHN_MATERIAL_JE_POSITION = "lohn_material_je_position"
# Toleranz Material + Lohn = Betrag (Cent)
ANTEIL_TOLERANZ = 0.011
# Wortlaut (Handwerker#105): „Arbeitskosten“ wie § 35a Abs. 3 EStG, gleich auf allen Belegen
DAVON_ARBEITSKOSTEN = "davon Arbeitskosten (§ 35a EStG, begünstigt)"
DAVON_MATERIALKOSTEN = "davon Materialkosten"
HINWEIS_35A = "Die in dieser Rechnung ausgewiesenen Arbeitskosten können nach § 35a EStG steuerlich begünstigt sein."
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


def anteile_der_position(row) -> dict | None:
	"""Material und Lohn einer Position (#105) oder ``None``: beide Felder vorhanden, nicht beide 0 und
	zusammen der Positionsbetrag (sonst ist die Zeile nicht berechnet - nichts Falsches drucken)."""
	material, lohn = row.get("cv_materialanteil"), row.get("cv_lohnanteil")
	if material is None or lohn is None:
		return None
	material, lohn = round(_zahl(material), 2), round(_zahl(lohn), 2)
	betrag = round(_zahl(row.get("amount")), 2)
	if not (material or lohn) or abs(material + lohn - betrag) > ANTEIL_TOLERANZ:
		return None
	# Druck: nur die Teile ungleich 0 (Regiestunde nur „Lohn“, kein „Material € 0,00“)
	teile = [{"text": text, "betrag": wert} for text, wert in (("Material", material), ("Lohn", lohn)) if wert]
	return {"material": material, "lohn": lohn, "teile": teile}


def lohn_material_summen(doc) -> dict | None:
	"""„davon Materialkosten / davon Lohnkosten“ je netto und brutto (#105) oder ``None`` ohne Werte."""
	if doc.get("cv_material_netto") is None and doc.get("cv_lohn_netto") is None:
		return None
	werte = {
		art: {
			"netto": round(_zahl(doc.get(f"cv_{art}_netto")), 2),
			"brutto": round(_zahl(doc.get(f"cv_{art}_brutto")), 2),
		}
		for art in ("material", "lohn")
	}
	if not (werte["material"]["netto"] or werte["lohn"]["netto"]):
		return None
	return werte


def davon_zeilen(summen: dict | None) -> list[dict]:
	"""Zeilen unter den Summen: zuerst die Arbeitskosten (§ 35a), dann das Material, je ``text``,
	``netto``, ``brutto``; eine Zeile mit 0 entfällt (reine Regie- oder Materialbelege)."""
	if not summen:
		return []
	return [
		{"text": text, **summen[art]}
		for text, art in ((DAVON_ARBEITSKOSTEN, "lohn"), (DAVON_MATERIALKOSTEN, "material"))
		if summen[art]["netto"]
	]


def lohn_material_daten(doc) -> dict:
	"""Für Formate ohne eigene Daten-Methode (Auftragsbestätigung): ``davon`` (Zeilen unter den Summen)
	und ``positionen`` (Anteile je Zeile von ``doc.items``, gleiche Reihenfolge; leer mit der Einstellung
	aus)."""
	items = doc.get("items") or []
	je_position = lohn_material_je_position()
	return {
		"davon": davon_zeilen(lohn_material_summen(doc)),
		"positionen": [anteile_der_position(row) if je_position else None for row in items],
	}


def lohn_material_je_position() -> bool:
	"""Einstellung „Lohn und Material je Position ausweisen“; ohne App oder ohne gespeicherten Wert an.

	Roh aus ``tabSingles``: ``get_single_value`` gäbe für einen nie gespeicherten Check 0 zurück."""
	import frappe

	if not frappe.db.exists("DocType", EINSTELLUNGEN_ABRECHNUNG):
		return True
	wert = (frappe.db.get_singles_dict(EINSTELLUNGEN_ABRECHNUNG) or {}).get(LOHN_MATERIAL_JE_POSITION)
	return wert in (None, "") or bool(int(_zahl(wert)))


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


# Allowlist für Text-Editor-Inhalte im Druck: nur Formatierung, keine Attribute außer class
# (ql-editor), kein style, keine Ereignisse, keine Bilder/Links
HTML_TAGS = frozenset({"p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li", "span", "div"})
HTML_ATTRIBUTE = {"div": {"class"}, "span": {"class"}, "p": {"class"}}


def _ist_json(text: str) -> bool:
	import json

	if not text or text[0] not in "{[":
		return False
	try:
		json.loads(text)
	except ValueError:
		return False
	return True


def html_sicher(value) -> str:
	"""HTML aus Text-Editor-Feldern für den Druck bereinigen (Security-Review 4.3).

	Immer bereinigen (anders als ``frappe.utils.sanitize_html``, das JSON und Text ohne
	führendes Tag unverändert durchreicht): nh3 mit enger Allowlist (``HTML_TAGS``,
	``HTML_ATTRIBUTE``). JSON wird vollständig maskiert. Ohne nh3 (nur in Tests ohne Bench)
	wird alles maskiert."""
	text = _text(value)
	if not text:
		return ""
	if _ist_json(text):
		return escape(text)
	try:
		import nh3
	except ImportError:
		return escape(text)
	return nh3.clean(text, tags=set(HTML_TAGS), attributes={k: set(v) for k, v in HTML_ATTRIBUTE.items()}, url_schemes=set())


def langtext(row, sanitize=html_sicher) -> str:
	"""Langtext einer Position als bereinigtes HTML, leer wenn er nur den Kurztext wiederholt."""
	beschreibung = _text(row.get("description"))
	if not beschreibung or html_zu_zeilen(beschreibung) == _text(row.get("item_name")):
		return ""
	return sanitize(beschreibung)


def titel_und_bauvorhaben(cv_titel, adresse: str) -> tuple[str, str]:
	"""Betreff des Angebots und Zeile „Bauvorhaben“.

	Mit ``cv_titel``: Titel = ``cv_titel``, Bauvorhaben = Objektadresse. Ohne: Titel =
	„Angebot“ + Objektadresse, keine zweite Zeile."""
	titel = _text(cv_titel)
	if titel:
		# der Generator (4.1) nimmt die Objektadresse schon in den Titel auf
		return titel, "" if adresse and adresse in titel else adresse
	return ("Angebot – " + adresse) if adresse else "Angebot", ""


def kundennummer(doc) -> str:
	"""Kundennummer = Name des Kunden-Datensatzes; nur bei Kunden (nicht bei Leads) und nur,
	wenn er nicht einfach der Kundenname ist (Benennung nach Name)."""
	if doc.get("quotation_to") != "Customer":
		return ""
	nummer = _text(doc.get("party_name"))
	return "" if nummer == _text(doc.get("customer_name")) else nummer


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

	gruppen = gruppiere(doc.get("items"))
	lm = lohn_material_summen(doc)
	je_position = lohn_material_je_position()
	for gruppe in gruppen:
		for position in gruppe["positionen"]:
			position["langtext"] = langtext(position["row"])
			position["anteile"] = anteile_der_position(position["row"]) if je_position else None
	# Ausgabe im Format: reine Texte (Titel, Bauvorhaben, Gruppen, Namen) mit „| e“,
	# HTML-Felder (Vorbemerkung, Langtext, Bedingungen, Anschrift) hier mit html_sicher
	# bereinigt (Security-Review 4.3)
	return {
		"titel": titel,
		"bauvorhaben": bauvorhaben,
		"vorbemerkung": html_sicher(doc.get("cv_vorbemerkung")),
		"bedingungen": html_sicher(doc.get("terms")),
		"anschrift": html_sicher(doc.get("address_display")),
		"garantiehinweis": text_als_html(doc.get("cv_garantiehinweis")),
		"kundennummer": kundennummer(doc),
		"ansprechpartner": ansprechpartner,
		"gruppen": gruppen,
		"mit_gruppen": bool(gruppen and gruppen[0]["nr"]),
		"ausserhalb_summe": any(not p["in_summe"] for g in gruppen for p in g["positionen"]),
		"lohn_material": lm,
		"davon": davon_zeilen(lm),
	}
