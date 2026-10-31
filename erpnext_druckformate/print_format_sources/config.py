# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

"""Source-of-truth mapping for **Print Format** docs synced by ``print_formats.py``.

Per format:
- key            **Print Format** name (shown in Desk)
- ``DocType``    the DocType the format prints (required); maps to the Print Format ``doc_type`` field
- ``template``   ``*.jinja`` filename next to this module (required)
- ``css``        optional hand-added override: a filename next to this module, or
                 ``None`` for no CSS. Omit to use ``SHARED_CSS`` (the default);
                 if you add one, drop the file in this folder yourself.
- ``fields``     optional dict of additional **Print Format** field overrides
                 (e.g. ``module``, ``pdf_generator``, ``default_print_language``,
                 margins, page number, ...)
"""

from __future__ import annotations

SHARED_CSS = "print_formats.css"

PRINT_FORMATS: dict[str, dict] = {
	"Angebot": {
		"DocType": "Quotation",
		"template": "quotation.jinja",
	},
	# Corevatis (Aufgabe 4.3): Titel, Positionen nach Raum/Bauteil, Textbausteine, Garantiehinweis;
	# Daten aus erpnext_druckformate/angebot_corevatis.py (Jinja-Methode, hooks.jinja)
	"Angebot Corevatis": {
		"DocType": "Quotation",
		"template": "angebot_corevatis.jinja",
	},
	"Ausgangsrechnung": {
		"DocType": "Sales Invoice",
		"template": "sales_invoice.jinja",
	},
	# Corevatis (Aufgabe 7.3, Handwerker#50): Abschlags-/Schlussrechnung mit Abschlagsübersicht,
	# § 35a-Block, Pflichtangaben; Daten aus erpnext_druckformate/rechnung_corevatis.py
	"Rechnung Corevatis": {
		"DocType": "Sales Invoice",
		"template": "rechnung_corevatis.jinja",
	},
	"Auftragsbestätigung": {
		"DocType": "Sales Order",
		"template": "sales_order.jinja",
	},
	"Lieferschein": {
		"DocType": "Delivery Note",
		"template": "delivery_note.jinja",
	},
	"Angebotsanfrage": {
		"DocType": "Request for Quotation",
		"template": "request_for_quotation.jinja",
	},
	"Bestellung": {
		"DocType": "Purchase Order",
		"template": "purchase_order.jinja",
	},
	"Mahnung": {
		"DocType": "Dunning",
		"template": "dunning.jinja",
	},
	# Corevatis (Aufgabe 7.5, Handwerker#77): Mahnung in Handwerkersprache;
	# Daten aus erpnext_druckformate/mahnung_corevatis.py
	"Mahnung Corevatis": {
		"DocType": "Dunning",
		"template": "mahnung_corevatis.jinja",
	},
}
