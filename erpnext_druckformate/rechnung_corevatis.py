"""Daten für das Druckformat „Rechnung Corevatis“ (Corevatis, Aufgabe 7.3, Handwerker#50).

Das Format (``print_format/rechnung_corevatis.jinja``) ruft ``rechnung_corevatis_daten(doc)`` auf
(Jinja-Methode, ``hooks.jinja``). Rechnungsart, Positionen, Summenblock, Abschlagsübersicht und
§ 35a-Block liegen hier statt im Template, damit sie ohne Site testbar sind
(``tests/test_rechnung_corevatis.py``).

Felder aus ``corevatis_erpnext`` (Custom Fields der Abrechnung 7.1/7.2) werden nur über
``doc.get(...)`` gelesen; ohne die App druckt das Format eine gewöhnliche Rechnung mit den
ERPNext-Summen:

- Sales Invoice: ``cv_abschlag`` (Abschlagsrechnung), ``cv_schlussrechnung``, ``cv_auftrag``,
  ``cv_abschlag_nr``, ``cv_abschlag_prozent``, ``cv_auftragssumme_netto``, ``cv_kumuliert_prozent``,
  ``cv_kumuliert_netto``, ``cv_leistung_netto/_steuer/_brutto``, ``cv_abschlaege_netto/_steuer/_brutto``,
  Tabelle ``cv_abschlaege`` (nr, rechnung, datum, bezeichnung, netto, steuer, brutto, bezahlt),
  ``cv_lohnanteil_netto/_steuer/_brutto/_prozent``
- Sales Invoice Item: ``cv_positionsart`` (Auftragsposition, Mehrmenge, Nachtrag, Abschlag,
  Abzug Abschlag), ``cv_menge_auftrag``

Summen: Die Abzugszeilen der Schlussrechnung (negativer Preis, ``Abzug Abschlag``) stehen nicht in
der Positionsliste; stattdessen zeigt der Summenblock die Leistung (``cv_leistung_*``), die
Abschlagsübersicht aus ``cv_abschlaege`` und den verbleibenden Betrag = ERPNext-Summen der Rechnung
(``net_total``, Steuer, ``grand_total``). Stimmt Leistung − Abschläge nicht mit dem Rest überein,
fällt der Block auf die ERPNext-Summen zurück (nie widersprüchliche Zahlen drucken).
"""

from __future__ import annotations

from datetime import date, datetime

from erpnext_druckformate.angebot_corevatis import (
	TECHNISCHE_BENUTZER,
	_text,
	_zahl,
	html_sicher,
	html_zu_zeilen,
	langtext,
	objekt_adresse,
)

ART_AUFTRAG, ART_MEHRMENGE, ART_NACHTRAG, ART_ABSCHLAG, ART_ABZUG = (
	"Auftragsposition",
	"Mehrmenge",
	"Nachtrag",
	"Abschlag",
	"Abzug Abschlag",
)
RECHNUNG, ABSCHLAG, SCHLUSS, GUTSCHRIFT = "Rechnung", "Abschlagsrechnung", "Schlussrechnung", "Gutschrift"
# Toleranz für den Abgleich Leistung − Abschläge = Rest (Rundung je Beleg)
CENT = 0.011


def _datum(value) -> str:
	"""Datum als ``dd.mm.yyyy`` (date, datetime oder ISO-String); leer, wenn nicht lesbar."""
	if not value:
		return ""
	if isinstance(value, datetime):
		value = value.date()
	if isinstance(value, date):
		return value.strftime("%d.%m.%Y")
	text = _text(value)[:10]
	try:
		return datetime.strptime(text, "%Y-%m-%d").strftime("%d.%m.%Y")
	except ValueError:
		return text


def _prozent(value) -> str:
	"""Prozent ohne überflüssige Nullen, deutsches Komma: 30 → „30“, 33,333 → „33,33“."""
	wert = round(_zahl(value), 2)
	text = f"{wert:.2f}".rstrip("0").rstrip(".")
	return text.replace(".", ",")


def rechnungsart(doc) -> str:
	if doc.get("is_return"):
		return GUTSCHRIFT
	if doc.get("cv_schlussrechnung"):
		return SCHLUSS
	if doc.get("cv_abschlag"):
		return ABSCHLAG
	return RECHNUNG


def betreff(doc, auftrag: dict | None, art: str | None = None) -> tuple[str, str]:
	"""Betreff und Unterzeile.

	Abschlag: „Abschlagsrechnung Nr. 1 zum Auftrag AB-2026-00008“; Schlussrechnung:
	„Schlussrechnung zum Auftrag AB-2026-00008“; Gutschrift: „Gutschrift zur Rechnung RE-…“;
	sonst „Rechnung“. Unterzeile: Titel des Auftrags (``cv_titel``) bzw. Auftragsdatum."""
	art = art or rechnungsart(doc)
	auftrag_name = _text(doc.get("cv_auftrag")) or _text((auftrag or {}).get("name"))
	if art == GUTSCHRIFT:
		gegen = _text(doc.get("return_against"))
		return (f"Gutschrift zur Rechnung {gegen}" if gegen else "Gutschrift"), ""
	if art == ABSCHLAG and auftrag_name:
		nr = int(_zahl(doc.get("cv_abschlag_nr"))) or None
		titel = f"Abschlagsrechnung Nr. {nr} zum Auftrag {auftrag_name}" if nr else f"Abschlagsrechnung zum Auftrag {auftrag_name}"
	elif art == SCHLUSS and auftrag_name:
		titel = f"Schlussrechnung zum Auftrag {auftrag_name}"
	elif auftrag_name:
		titel = f"Rechnung zum Auftrag {auftrag_name}"
	else:
		return art, ""
	unterzeile = _text((auftrag or {}).get("cv_titel"))
	if not unterzeile and (auftrag or {}).get("transaction_date"):
		unterzeile = f"Auftrag vom {_datum(auftrag['transaction_date'])}"
	return titel, unterzeile


def positionen(items) -> list[dict]:
	"""Positionen für den Druck: ohne Abzugszeilen, fortlaufend nummeriert.

	Je Position ``nr``, ``row``, ``art`` (``cv_positionsart`` oder leer), ``hinweis`` („Nachtrag“,
	„Mehrmenge“, „Auftragsmenge …“ bei Mindermenge), ``menge_auftrag`` (nur wenn abweichend)."""
	ergebnis = []
	nr = 0
	for row in items or []:
		art = _text(row.get("cv_positionsart"))
		if art == ART_ABZUG:
			continue
		nr += 1
		menge_auftrag = _zahl(row.get("cv_menge_auftrag"))
		menge = _zahl(row.get("qty"))
		hinweis = None
		abweichend = None
		if art == ART_NACHTRAG:
			hinweis = "Nachtrag"
		elif art == ART_MEHRMENGE:
			hinweis = "Mehrmenge"
		elif art == ART_AUFTRAG and menge_auftrag and abs(menge_auftrag - menge) > 1e-9:
			hinweis = "Mindermenge" if menge < menge_auftrag else "Mehrmenge"
			abweichend = menge_auftrag
		ergebnis.append(
			{"nr": str(nr), "row": row, "art": art or None, "hinweis": hinweis, "menge_auftrag": abweichend}
		)
	return ergebnis


def abschlaege(doc) -> list[dict]:
	"""Zeilen der Abschlagsübersicht (``cv_abschlaege``) als einfache Dicts, Datum formatiert."""
	zeilen = []
	for z in doc.get("cv_abschlaege") or []:
		zeilen.append(
			{
				"nr": int(_zahl(z.get("nr"))) or len(zeilen) + 1,
				"rechnung": _text(z.get("rechnung")),
				"datum": _datum(z.get("datum")),
				"bezeichnung": _text(z.get("bezeichnung")),
				"netto": round(_zahl(z.get("netto")), 2),
				"steuer": round(_zahl(z.get("steuer")), 2),
				"brutto": round(_zahl(z.get("brutto")), 2),
				"bezahlt": bool(z.get("bezahlt")),
			}
		)
	return zeilen


def summen(doc, art: str | None = None) -> dict:
	"""Summenblock.

	``mit_abzug``: Schlussrechnung mit Abschlagsübersicht - Leistung (``cv_leistung_*``), Summe der
	Abschläge, verbleibender Betrag (ERPNext-Summen). Nur wenn Leistung − Abschläge = Rest (netto,
	Cent-Toleranz), sonst ``False`` und das Format druckt die ERPNext-Summen allein.
	``kumuliert``: Stand der Abrechnung einer Abschlagsrechnung (Prozent, netto, Auftragssumme)."""
	art = art or rechnungsart(doc)
	ab = abschlaege(doc)
	rest = {
		"netto": round(_zahl(doc.get("net_total")), 2),
		"steuer": round(_zahl(doc.get("total_taxes_and_charges")), 2),
		"brutto": round(_zahl(doc.get("grand_total")), 2),
	}
	leistung = {
		"netto": round(_zahl(doc.get("cv_leistung_netto")), 2),
		"steuer": round(_zahl(doc.get("cv_leistung_steuer")), 2),
		"brutto": round(_zahl(doc.get("cv_leistung_brutto")), 2),
	}
	abzug = {
		"netto": round(_zahl(doc.get("cv_abschlaege_netto")) or sum(z["netto"] for z in ab), 2),
		"steuer": round(_zahl(doc.get("cv_abschlaege_steuer")) or sum(z["steuer"] for z in ab), 2),
		"brutto": round(_zahl(doc.get("cv_abschlaege_brutto")) or sum(z["brutto"] for z in ab), 2),
	}
	mit_abzug = (
		art == SCHLUSS
		and bool(ab)
		and leistung["netto"] > 0
		and abs(leistung["netto"] - abzug["netto"] - rest["netto"]) <= CENT
	)
	kumuliert = None
	if art == ABSCHLAG and _zahl(doc.get("cv_auftragssumme_netto")) > 0:
		kumuliert = {
			"prozent": _prozent(doc.get("cv_kumuliert_prozent")),
			"netto": round(_zahl(doc.get("cv_kumuliert_netto")), 2),
			"auftragssumme": round(_zahl(doc.get("cv_auftragssumme_netto")), 2),
			"dieser_prozent": _prozent(doc.get("cv_abschlag_prozent")),
		}
	return {
		"mit_abzug": mit_abzug,
		"leistung": leistung,
		"abschlaege": abzug,
		"rest": rest,
		"rundungsdifferenz": round(leistung["steuer"] - abzug["steuer"] - rest["steuer"], 2) if mit_abzug else 0.0,
		"kumuliert": kumuliert,
		"bisherige_abschlaege": ab if art == ABSCHLAG else [],
	}


def lohnanteil(doc) -> dict | None:
	"""§ 35a EStG: Lohn-, Fahrt- und Maschinenkosten in der Rechnung; ``None`` ohne Ausweis."""
	brutto = round(_zahl(doc.get("cv_lohnanteil_brutto")), 2)
	if brutto <= 0:
		return None
	return {
		"netto": round(_zahl(doc.get("cv_lohnanteil_netto")), 2),
		"steuer": round(_zahl(doc.get("cv_lohnanteil_steuer")), 2),
		"brutto": brutto,
		"prozent": _prozent(doc.get("cv_lohnanteil_prozent")) if _zahl(doc.get("cv_lohnanteil_prozent")) else "",
	}


def leistungszeitraum(von, bis) -> str:
	"""„03.11.2026 – 14.11.2026“, ein Tag → „14.11.2026“, nur Ende → „bis 14.11.2026“, nur Anfang →
	„ab 03.11.2026“, nichts → leer."""
	a, b = _datum(von), _datum(bis)
	if a and b:
		return a if a == b else f"{a} – {b}"
	if b:
		return f"bis {b}"
	if a:
		return f"ab {a}"
	return ""


def zahlungstext(art: str, betrag: str, faellig: str, name: str, mit_bank: bool) -> str:
	"""Satz zur Zahlung (reiner Text, im Format mit ``| e`` ausgeben)."""
	if art == GUTSCHRIFT:
		return f"Der Betrag von {betrag} wird Ihnen erstattet bzw. mit offenen Forderungen verrechnet."
	satz = f"Bitte überweisen Sie den Betrag von {betrag}"
	if faellig:
		satz += f" bis zum {faellig}"
	satz += f" unter Angabe der Rechnungsnummer {name}"
	satz += " auf das unten genannte Konto." if mit_bank else "."
	return satz


def bankverbindung(bank: dict | None) -> list[tuple[str, str]]:
	"""Zeilen „Bank“, „IBAN“, „BIC“, „Kontoinhaber“ ohne leere Werte."""
	if not bank:
		return []
	zeilen = [
		("Bank", _text(bank.get("bank"))),
		("IBAN", _text(bank.get("iban"))),
		("BIC", _text(bank.get("bic"))),
		("Kontoinhaber", _text(bank.get("kontoinhaber"))),
	]
	return [(k, v) for k, v in zeilen if v]


def kundennummer(doc) -> str:
	"""Kundennummer = Name des Kunden-Datensatzes, nur wenn er nicht einfach der Kundenname ist."""
	nummer = _text(doc.get("customer"))
	return "" if not nummer or nummer == _text(doc.get("customer_name")) else nummer


# --- mit Frappe --------------------------------------------------------------------------------


def _auftrag(doc) -> dict | None:
	import frappe

	name = doc.get("cv_auftrag")
	if not name or not frappe.db.exists("Sales Order", name):
		return None
	meta = frappe.get_meta("Sales Order")
	felder = ["name", "transaction_date", "project"]
	felder += [f for f in ("cv_titel", "cv_objekt") if meta.has_field(f)]
	return frappe.db.get_value("Sales Order", name, felder, as_dict=True)


def _projekt(doc, auftrag: dict | None) -> dict | None:
	import frappe

	name = doc.get("project") or (auftrag or {}).get("project")
	if not name or not frappe.db.exists("Project", name):
		return None
	meta = frappe.get_meta("Project")
	felder = ["name", "project_name", "actual_start_date", "actual_end_date", "expected_start_date", "expected_end_date"]
	felder += [f for f in ("cv_abgenommen_am",) if meta.has_field(f)]
	return frappe.db.get_value("Project", name, felder, as_dict=True)


def _zeitraum(doc, projekt: dict | None, art: str) -> str:
	"""Leistungszeitraum (§ 14 UStG): Projektstart bis Abnahme (Schlussrechnung) bzw. bis zum
	Rechnungsdatum (Abschlag); ohne Projekt leer - das Format druckt dann den Hinweis
	„Leistungsdatum entspricht dem Rechnungsdatum“."""
	if not projekt:
		return ""
	von = projekt.get("actual_start_date") or projekt.get("expected_start_date")
	if art == SCHLUSS:
		bis = projekt.get("cv_abgenommen_am") or projekt.get("actual_end_date") or doc.get("posting_date")
	else:
		bis = doc.get("posting_date")
	if von and bis and str(von)[:10] > str(bis)[:10]:
		von = None
	return leistungszeitraum(von, bis)


def _bank(company: str | None) -> dict | None:
	import frappe

	if not company or not frappe.db.exists("DocType", "Bank Account"):
		return None
	filters = {"company": company, "is_company_account": 1, "disabled": 0}
	konto = frappe.db.get_value(
		"Bank Account", {**filters, "is_default": 1}, ["bank", "iban", "account_name"], as_dict=True
	) or frappe.db.get_value("Bank Account", filters, ["bank", "iban", "account_name"], as_dict=True)
	if not konto or not (konto.get("iban") or konto.get("bank")):
		return None
	bic = frappe.db.get_value("Bank", konto.bank, "swift_number") if konto.get("bank") else None
	return {
		"bank": konto.get("bank"),
		"iban": konto.get("iban"),
		"bic": bic,
		"kontoinhaber": frappe.db.get_value("Company", company, "company_name"),
	}


def _bauvorhaben(doc, auftrag: dict | None) -> str:
	import frappe

	adresse = ""
	objekt = (auftrag or {}).get("cv_objekt")
	if objekt and frappe.db.exists("DocType", "Objekt") and frappe.db.exists("Objekt", objekt):
		adresse = objekt_adresse(
			frappe.db.get_value("Objekt", objekt, ["strasse", "plz", "ort"], as_dict=True)
		)
	if not adresse and doc.get("shipping_address_name") and doc.get("shipping_address_name") != doc.get(
		"customer_address"
	):
		adresse = html_zu_zeilen(doc.get("shipping_address"))
	titel = _text((auftrag or {}).get("cv_titel"))
	return "" if adresse and adresse in titel else adresse


def rechnung_corevatis_daten(doc) -> dict:
	"""Jinja-Methode für „Rechnung Corevatis“: alles, was über die Standardfelder hinausgeht."""
	import frappe

	art = rechnungsart(doc)
	auftrag = _auftrag(doc)
	projekt = _projekt(doc, auftrag)
	titel, unterzeile = betreff(doc, auftrag, art)
	ansprechpartner = ""
	if doc.get("owner") and doc.owner not in TECHNISCHE_BENUTZER:
		ansprechpartner = _text(frappe.utils.get_fullname(doc.owner))
	pos = positionen(doc.get("items"))
	for p in pos:
		p["langtext"] = langtext(p["row"])
	bank = _bank(doc.get("company"))
	s = summen(doc, art)
	betrag = frappe.utils.fmt_money(s["rest"]["brutto"], currency=doc.get("currency"))
	faellig = _datum(doc.get("due_date")) if art != GUTSCHRIFT else ""
	# Ausgabe im Format: reine Texte mit „| e“, HTML-Felder (Langtext, Bedingungen, Anschrift)
	# hier mit html_sicher bereinigt (Security-Review 4.3)
	return {
		"art": art,
		"titel": titel,
		"unterzeile": unterzeile,
		"bauvorhaben": _bauvorhaben(doc, auftrag),
		"auftrag": auftrag,
		"projekt": projekt,
		"leistungszeitraum": _zeitraum(doc, projekt, art),
		"kundennummer": kundennummer(doc),
		"ansprechpartner": ansprechpartner,
		"anschrift": html_sicher(doc.get("address_display")),
		"bedingungen": html_sicher(doc.get("terms")),
		"positionen": pos,
		"summen": s,
		"lohnanteil": lohnanteil(doc),
		"bank": bankverbindung(bank),
		"faellig": faellig,
		"zahlungstext": zahlungstext(art, betrag, faellig, _text(doc.get("name")), bool(bank)),
	}
