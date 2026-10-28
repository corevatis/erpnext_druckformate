# Copyright (c) 2026, ALYF GmbH and Contributors
# See license.txt

"""Build **Print Format** docs from ``config.PRINT_FORMATS`` (+ templates, CSS) and sync on migrate.

Sync rules (``sync_print_formats``, run by ``after_install`` and ``after_migrate``):

- missing format -> created;
- format unchanged on the site and source unchanged since the last sync -> no-op
  (no delete/insert, no new ``modified``, no Version entry);
- source changed and the site copy is still exactly what the last sync wrote -> updated;
- site copy edited in Desk (content hash differs from the last sync) -> **kept**, a warning
  is printed/logged. Customise by duplicating a format, not by editing it; to take the
  shipped version anyway run ``sync_print_formats(force=True)``
  (``bench --site <site> execute erpnext_druckformate.print_format_sources.print_formats.sync_print_formats --kwargs '{"force": true}'``)
  or set ``erpnext_druckformate_force_sync: 1`` in the site config for one migrate.

The last synced hashes (source and site copy) are stored per format as a global default
(``erpnext_druckformate:<name>``). Sites synced before this rule existed have no stored
hash: a copy identical to the source is adopted, a copy last modified by ``Administrator``
(the user hooks run as) is treated as unmodified and updated, anything else is kept.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .config import PRINT_FORMATS, SHARED_CSS

# Baseline for **Print Format** import; override per-format under ``fields`` only when you need to differ.
# Frappe's own ``doctype`` marker ("Print Format") is set explicitly at doc construction.
PRINT_FORMAT_DEFAULTS: dict[str, Any] = {
	"print_format_type": "Jinja",
	"disabled": 0,
	# "Yes" would make Frappe export a .json into whichever app owns the module —
	# ERPNext's, since we set no `module`. Sources here stay the only copy.
	"standard": "No",
	"custom_format": 1,
	"align_labels_right": 0,
	"show_section_headings": 0,
	"line_breaks": 0,
	"absolute_value": 0,
	"font_size": 14,
	"page_number": "Hide",
	"font": None,
	"format_data": None,
	"print_format_builder": 0,
	"print_format_builder_beta": 0,
	"raw_printing": 0,
	"raw_commands": None,
	"default_print_language": None,
	"margin_top": 15.0,
	"margin_bottom": 15.0,
	"margin_left": 15.0,
	"margin_right": 15.0,
	"report": None,
	# Majority of current formats; sales-invoice variants override ``print_format_for`` / ``pdf_generator`` under ``fields``.
	"print_format_for": "DocType",
	"pdf_generator": "wkhtmltopdf",
}

# Anything in ``"fields"`` that isn't here raises during build (typo guard).
# = every defaulted field, plus ``module`` (allowed but not defaulted).
ALLOWED_FIELD_OVERRIDES = frozenset(PRINT_FORMAT_DEFAULTS) | {"module"}


def _load_text(path: Path) -> str:
	if not path.is_file():
		raise FileNotFoundError(path)
	return path.read_text(encoding="utf-8")


def build_print_format_docs(sources_root: Path) -> list[dict[str, Any]]:
	"""Return **Print Format** dicts ready for ``import_doc`` (no Frappe dependency)."""
	if not sources_root.is_dir():
		raise FileNotFoundError(f"print format sources not found: {sources_root}")

	docs: list[dict[str, Any]] = []
	for name, spec in PRINT_FORMATS.items():
		doc_type = spec.get("DocType")
		if not doc_type:
			raise ValueError(f"[{name}] missing DocType")
		template_rel = spec.get("template")
		if not template_rel:
			raise ValueError(f"[{name}] missing template")

		# Missing key -> shared default; ``None`` -> no CSS for this format.
		css_rel = spec.get("css", SHARED_CSS)
		css = _load_text(sources_root / css_rel) if css_rel else ""

		fields = spec.get("fields") or {}
		unknown = set(fields) - ALLOWED_FIELD_OVERRIDES
		if unknown:
			raise ValueError(f"[{name}] unknown field(s): {sorted(unknown)}")

		docs.append(
			{
				**PRINT_FORMAT_DEFAULTS,
				**fields,
				"doctype": "Print Format",
				"name": name,
				"doc_type": doc_type,
				"html": _load_text(sources_root / template_rel),
				"css": css,
			}
		)

	if not docs:
		raise ValueError("No print formats defined in config.PRINT_FORMATS")

	return docs


def _package_dir() -> Path:
	return Path(__file__).resolve().parent


# Keys of a built doc that are not part of the content comparison
_HASH_EXCLUDED = frozenset({"doctype", "name", "creation"})
# Users the install/migrate hooks run as; their ``modified_by`` counts as "synced by us"
SYNC_USERS = frozenset({"Administrator"})
STATE_KEY_PREFIX = "erpnext_druckformate:"
FORCE_SYNC_CONF_KEY = "erpnext_druckformate_force_sync"


def content_keys(doc: dict[str, Any]) -> list[str]:
	return sorted(set(doc) - _HASH_EXCLUDED)


def _normalize(value: Any) -> str:
	"""Make source values and database values comparable (None/"" , 1/1.0/True, CRLF)."""
	if value is None or value == "":
		return ""
	if isinstance(value, bool):
		value = int(value)
	if isinstance(value, int | float) or type(value).__name__ == "Decimal":
		number = float(value)
		return str(int(number)) if number.is_integer() else repr(number)
	return str(value).replace("\r\n", "\n")


def content_hash(doc: dict[str, Any], keys: list[str]) -> str:
	payload = {key: _normalize(doc.get(key)) for key in keys}
	return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def plan_sync(
	source_hash: str,
	site_hash: str | None,
	state: dict | None,
	modified_by: str | None,
	force: bool = False,
) -> str:
	"""Decide what to do with one format (no Frappe dependency).

	Returns ``create``, ``update``, ``unchanged``, ``adopt`` (record state only) or
	``customized`` (keep the site copy)."""
	if site_hash is None:
		return "create"
	if force:
		return "unchanged" if site_hash == source_hash and state else "update"
	if state:
		if site_hash != state.get("site"):
			return "customized"
		return "unchanged" if state.get("source") == source_hash else "update"
	# no state: synced by an older version of this hook (always import_doc(force))
	if site_hash == source_hash:
		return "adopt"
	if modified_by in SYNC_USERS:
		return "update"
	return "customized"


def _site_hash(name: str, keys: list[str]) -> tuple[str | None, str | None]:
	import frappe

	values = frappe.db.get_value("Print Format", name, [*keys, "modified_by"], as_dict=True)
	if not values:
		return None, None
	return content_hash(values, keys), values.get("modified_by")


def _get_state(name: str) -> dict | None:
	import frappe

	raw = frappe.db.get_global(STATE_KEY_PREFIX + name)
	try:
		state = json.loads(raw) if raw else None
	except ValueError:
		return None
	return state if isinstance(state, dict) else None


def _set_state(name: str, source_hash: str, site_hash: str | None) -> None:
	import frappe

	frappe.db.set_global(STATE_KEY_PREFIX + name, json.dumps({"source": source_hash, "site": site_hash}))


def sync_print_formats(force: bool = False) -> dict[str, list[str]]:
	"""``after_install``/``after_migrate`` hook: create or update formats (see module docstring).

	Returns a report ``{"create": [...], "update": [...], "unchanged": [...], "adopt": [...],
	"customized": [...]}``."""
	import frappe

	force = bool(force) or bool(frappe.conf.get(FORCE_SYNC_CONF_KEY))
	docs = build_print_format_docs(_package_dir())
	report: dict[str, list[str]] = {
		"create": [],
		"update": [],
		"unchanged": [],
		"adopt": [],
		"customized": [],
	}
	to_import: list[dict[str, Any]] = []
	hashes: dict[str, tuple[str, list[str]]] = {}
	for doc in docs:
		keys = content_keys(doc)
		source_hash = content_hash(doc, keys)
		site_hash, modified_by = _site_hash(doc["name"], keys)
		action = plan_sync(source_hash, site_hash, _get_state(doc["name"]), modified_by, force=force)
		report[action].append(doc["name"])
		hashes[doc["name"]] = (source_hash, keys)
		if action in ("create", "update"):
			to_import.append(doc)
		elif action == "adopt":
			_set_state(doc["name"], source_hash, site_hash)

	for name in report["customized"]:
		message = (
			f"Print Format {name!r} was changed on this site - not overwritten. "
			"Duplicate it to customise, or run sync_print_formats(force=True) to restore the shipped version."
		)
		print(message)
		frappe.logger().warning(message)

	print(
		"Print formats: "
		+ ", ".join(f"{len(names)} {action}" for action, names in report.items() if names)
	)
	if to_import:
		_import_docs(to_import)
		for doc in to_import:
			source_hash, keys = hashes[doc["name"]]
			_set_state(doc["name"], source_hash, _site_hash(doc["name"], keys)[0])
	return report


def _import_docs(docs: list[dict[str, Any]]) -> None:
	"""Export docs to a temp JSON file and ``import_doc`` (delete + insert per doc)."""
	import frappe
	from frappe.core.doctype.data_import.data_import import (
		import_doc as import_doc_from_path,
	)

	_preserve_existing_creation(docs)
	frappe.logger().info("Importing %s print formats from source", len(docs))

	tmp_path: str | None = None
	try:
		with NamedTemporaryFile(
			mode="w", suffix=".json", delete=False, encoding="utf-8"
		) as tmp:
			json.dump(docs, tmp, ensure_ascii=False)
			tmp.flush()
			tmp_path = tmp.name
		import_doc_from_path(tmp_path)
	finally:
		if tmp_path:
			Path(tmp_path).unlink(missing_ok=True)


def _preserve_existing_creation(docs: list[dict[str, Any]]) -> None:
	"""For each doc that already exists, copy its ``creation`` timestamp forward.
	``import_doc`` does delete+insert (resetting ``creation`` otherwise), but
	respects an explicit value if we set it."""
	import frappe

	for doc in docs:
		existing = frappe.db.get_value(doc["doctype"], doc["name"], "creation")
		if existing:
			doc["creation"] = str(existing)
