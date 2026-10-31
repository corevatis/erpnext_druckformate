app_name = "erpnext_druckformate"
app_title = "ERPNext Druckformate"
app_publisher = "ALYF GmbH"
app_description = "ERPNext-Druckformate nach DIN 5008"
app_email = "hallo@alyf.de"
app_license = "gpl-3.0"
required_apps = ["frappe/erpnext"]

# Druckformate aus print_format_sources/ (erzeugt mit frappe-pf-init) bei
# install-app und migrate in die Site importieren
after_install = ["erpnext_druckformate.print_format_sources.print_formats.sync_print_formats"]
after_migrate = ["erpnext_druckformate.print_format_sources.print_formats.sync_print_formats"]

# Jinja-Methoden der Corevatis-Formate: „Angebot Corevatis“ (Aufgabe 4.3: Gruppierung nach
# Raum/Bauteil, Positionsnummern, Titel, Textbausteine), „Rechnung Corevatis“ (7.3: Rechnungsart,
# Abschlagsübersicht, § 35a-Block, Bankverbindung), „Mahnung Corevatis“ (7.5: Mahnstufe, offene Posten)
jinja = {
	"methods": [
		"erpnext_druckformate.angebot_corevatis.angebot_corevatis_daten",
		"erpnext_druckformate.rechnung_corevatis.rechnung_corevatis_daten",
		"erpnext_druckformate.mahnung_corevatis.mahnung_corevatis_daten",
	]
}
