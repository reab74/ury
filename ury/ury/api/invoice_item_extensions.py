"""Optional app resolvers for authoritative POS invoice item data.

Resolvers return None for ordinary menu items. They must validate permissions,
quantity and pricing themselves. No submitted rate is trusted by this module.
"""
import frappe
from frappe import _


def resolve_invoice_item(item, context):
    resolved = None
    for path in frappe.get_hooks("ury_invoice_item_resolvers") or []:
        candidate = frappe.get_attr(path)(item, context)
        if candidate is not None:
            if resolved is not None:
                frappe.throw(_("Multiple apps tried to price the same POS item."))
            resolved = candidate
    if item.get("custom_flora_arrangement") and resolved is None:
        frappe.throw(_("Arrangement pricing is unavailable. Check the installed POS integration."))
    return resolved


def validate_arrangement_references(items):
    seen = set()
    for item in items:
        reference = item.get("custom_flora_arrangement")
        if reference in (None, ""):
            continue
        if not isinstance(reference, str) or reference.strip() != reference or len(reference) > 140:
            frappe.throw(_("Invalid arrangement reference."))
        if reference in seen:
            frappe.throw(_("An arrangement cannot appear on multiple order rows."))
        seen.add(reference)


def run_order_guards(hook, invoice, **context):
    """Optional app guards run before cancellation/split side effects."""
    for path in frappe.get_hooks(hook) or []:
        frappe.get_attr(path)(invoice, **context)
