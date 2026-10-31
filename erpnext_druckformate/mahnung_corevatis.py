"""Daten für das Druckformat „Mahnung Corevatis“ (Corevatis, Aufgabe 7.5, Handwerker#77).

Das Format (``print_format/mahnung_corevatis.jinja``) druckt ERPNexts ``Dunning`` in Handwerkersprache:
Betreff ist die Mahnstufe (Zahlungserinnerung, 1. Mahnung, 2. Mahnung - der ``Dunning Type`` ohne das
Firmenkürzel, das ERPNext an den Namen hängt), darunter der Brieftext des Mahntyps, die Tabelle der
offenen Rechnungen (Nummer, Rechnungsdatum, fällig am, Tage überfällig, offener Betrag), Mahngebühr und
Zinsen, Gesamtbetrag, Zahlungsfrist und Bankverbindung aus den Firmendaten.

Felder aus ``corevatis_erpnext`` werden nur über ``doc.get(...)`` gelesen: ``cv_zahlungsfrist`` am
Dunning (Datum, bis zu dem gezahlt werden soll; ohne das Feld Buchungsdatum + ``FRIST_TAGE``),
``cv_mahnstufe`` am Dunning Type; an den Rechnungen ``cv_abschlag``/``cv_abschlag_nr``/
``cv_schlussrechnung``/``cv_auftrag`` für die Bezeichnung („Abschlagsrechnung Nr. 1 zum Auftrag …“).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from erpnext_druckformate.angebot_corevatis import TECHNISCHE_BENUTZER, _text, _zahl, html_sicher
from erpnext_druckformate.rechnung_corevatis import _datum, bankverbindung

FRIST_TAGE = 7
STUFEN = {0: "Zahlungserinnerung", 1: "1. Mahnung", 2: "2. Mahnung"}


def stufe_bezeichnung(dunning_type: str | None, bezeichnung: str | None = None, mahnstufe=None) -> str:
	"""Betreff: Bezeichnung des Mahntyps (``Dunning Type.dunning_type``), sonst der Name ohne
	Firmenkürzel („1. Mahnung - HST“ → „1. Mahnung“), sonst nach ``cv_mahnstufe``, sonst „Mahnung“."""
	text = _text(bezeichnung)
	if text:
		return text
	name = _text(dunning_type)
	if name:
		return name.rsplit(" - ", 1)[0] if " - " in name else name
	if mahnstufe is not None and int(_zahl(mahnstufe)) in STUFEN:
		return STUFEN[int(_zahl(mahnstufe))]
	return "Mahnung"


def _als_datum(value) -> date | None:
	if not value:
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	try:
		return datetime.strptime(_text(value)[:10], "%Y-%m-%d").date()
	except ValueError:
		return None


def zahlungsfrist(posting_date, cv_zahlungsfrist=None, tage: int = FRIST_TAGE) -> str:
	"""Zahlungsfrist als ``dd.mm.yyyy``: ``cv_zahlungsfrist`` (Adapter), sonst Buchungsdatum + Tage."""
	frist = _als_datum(cv_zahlungsfrist)
	if frist is None:
		basis = _als_datum(posting_date)
		if basis is None:
			return ""
		frist = basis + timedelta(days=tage)
	return frist.strftime("%d.%m.%Y")


def rechnungsbezeichnung(daten: dict | None) -> str:
	"""„Abschlagsrechnung Nr. 1 zum Auftrag AB-…“, „Schlussrechnung zum Auftrag AB-…“, sonst „Rechnung“."""
	if not daten:
		return "Rechnung"
	auftrag = _text(daten.get("cv_auftrag"))
	zusatz = f" zum Auftrag {auftrag}" if auftrag else ""
	if daten.get("cv_schlussrechnung"):
		return "Schlussrechnung" + zusatz
	if daten.get("cv_abschlag"):
		nr = int(_zahl(daten.get("cv_abschlag_nr")))
		return (f"Abschlagsrechnung Nr. {nr}" if nr else "Abschlagsrechnung") + zusatz
	return "Rechnung" + zusatz


def zeilen(overdue_payments, rechnungen: dict[str, dict] | None = None) -> list[dict]:
	"""Zeilen der Tabelle: Rechnung, Bezeichnung, Rechnungsdatum, fällig am, Tage überfällig, offen."""
	rechnungen = rechnungen or {}
	ergebnis = []
	for row in overdue_payments or []:
		name = _text(row.get("sales_invoice"))
		daten = rechnungen.get(name) or {}
		ergebnis.append(
			{
				"rechnung": name,
				"bezeichnung": rechnungsbezeichnung(daten),
				"rechnungsdatum": _datum(daten.get("posting_date")),
				"faellig": _datum(row.get("due_date")),
				"tage": int(_zahl(row.get("overdue_days"))),
				"offen": round(_zahl(row.get("outstanding")), 2),
				"stufe": int(_zahl(row.get("dunning_level"))) or 1,
			}
		)
	return ergebnis


def summen(doc) -> dict:
	return {
		"offen": round(_zahl(doc.get("total_outstanding")), 2),
		"gebuehr": round(_zahl(doc.get("dunning_fee")), 2),
		"zinsen": round(_zahl(doc.get("total_interest")), 2),
		"gesamt": round(_zahl(doc.get("grand_total")), 2),
	}


def zahlungstext(stufe: str, gesamt: str, frist: str, mit_bank: bool) -> str:
	"""Satz zur Zahlung (reiner Text, im Format mit ``| e`` ausgeben)."""
	satz = f"Bitte überweisen Sie den Gesamtbetrag von {gesamt}"
	if frist:
		satz += f" bis zum {frist}"
	satz += " auf das unten genannte Konto." if mit_bank else "."
	if stufe == STUFEN[0]:
		satz += " Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten haben, betrachten Sie es bitte als gegenstandslos."
	return satz


# --- mit Frappe --------------------------------------------------------------------------------


def _rechnungen(namen: list[str]) -> dict[str, dict]:
	import frappe

	namen = [n for n in namen if n]
	if not namen:
		return {}
	meta = frappe.get_meta("Sales Invoice")
	felder = ["name", "posting_date", "due_date", "grand_total"]
	felder += [
		f for f in ("cv_abschlag", "cv_abschlag_nr", "cv_schlussrechnung", "cv_auftrag") if meta.has_field(f)
	]
	return {
		r["name"]: r
		for r in frappe.get_all("Sales Invoice", filters={"name": ["in", namen]}, fields=felder)
	}


def _mahntyp(doc) -> tuple[str | None, int | None]:
	import frappe

	name = doc.get("dunning_type")
	if not name or not frappe.db.exists("Dunning Type", name):
		return None, None
	meta = frappe.get_meta("Dunning Type")
	felder = ["dunning_type"] + (["cv_mahnstufe"] if meta.has_field("cv_mahnstufe") else [])
	werte = frappe.db.get_value("Dunning Type", name, felder, as_dict=True) or {}
	stufe = werte.get("cv_mahnstufe")
	return werte.get("dunning_type"), (int(stufe) if stufe is not None else None)


def mahnung_corevatis_daten(doc) -> dict:
	"""Jinja-Methode für „Mahnung Corevatis“."""
	import frappe
	from erpnext_druckformate.rechnung_corevatis import _bank

	bezeichnung, mahnstufe = _mahntyp(doc)
	stufe = stufe_bezeichnung(doc.get("dunning_type"), bezeichnung, mahnstufe)
	rechnungen = _rechnungen([_text(r.get("sales_invoice")) for r in doc.get("overdue_payments") or []])
	bank = _bank(doc.get("company"))
	s = summen(doc)
	frist = zahlungsfrist(doc.get("posting_date"), doc.get("cv_zahlungsfrist"))
	ansprechpartner = ""
	if doc.get("owner") and doc.owner not in TECHNISCHE_BENUTZER:
		ansprechpartner = _text(frappe.utils.get_fullname(doc.owner))
	return {
		"stufe": stufe,
		"zeilen": zeilen(doc.get("overdue_payments"), rechnungen),
		"summen": s,
		"frist": frist,
		"zahlungstext": zahlungstext(
			stufe, frappe.utils.fmt_money(s["gesamt"], currency=doc.get("currency")), frist, bool(bank)
		),
		"bank": bankverbindung(bank),
		"anschrift": html_sicher(doc.get("address_display")),
		"text": html_sicher(doc.get("body_text")),
		"schluss": html_sicher(doc.get("closing_text")),
		"ansprechpartner": ansprechpartner,
		"kundennummer": ""
		if not doc.get("customer") or _text(doc.get("customer")) == _text(doc.get("customer_name"))
		else _text(doc.get("customer")),
	}
