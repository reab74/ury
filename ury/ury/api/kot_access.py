"""Shared authorization for Mosaic HTTP actions and KOT event recipients.

These checks supplement Frappe document permissions; they never replace them.
No session impersonation and no permission-result cache is used for recipients.
"""
import frappe
from frappe import _
from frappe.realtime import get_user_room


def _deny():
    frappe.throw(_("Not permitted to access this kitchen order."), frappe.PermissionError)


def _require_permission(doc, permission, user):
    if not frappe.has_permission(doc.doctype, permission, doc=doc, user=user):
        _deny()


def _require_branch(branch, user):
    if not branch:
        _deny()
    # Administrative access still requires document and company permission.
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return
    if not frappe.db.exists("URY User", {
        "parent": branch, "parenttype": "Branch", "user": user,
    }):
        _deny()


def require_profile_access(name, user=None):
    user = user or frappe.session.user
    if user == "Guest" or not name:
        _deny()
    profile = frappe.get_doc("POS Profile", name)
    _require_permission(profile, "read", user)
    if not profile.company:
        _deny()
    company = frappe.get_doc("Company", profile.company)
    _require_permission(company, "read", user)
    _require_branch(profile.branch, user)
    return profile


def require_kot_access(kot, permission="read", user=None):
    user = user or frappe.session.user
    if user == "Guest":
        _deny()
    if isinstance(kot, str):
        kot = frappe.get_doc("URY KOT", kot)
    _require_permission(kot, "read", user)
    if permission != "read":
        _require_permission(kot, permission, user)
    profile = require_profile_access(kot.pos_profile, user)
    if kot.branch != profile.branch or not kot.invoice:
        _deny()
    # invoice is a Data field: explicitly validate its ownership chain.
    invoice = frappe.get_doc("POS Invoice", kot.invoice)
    if (invoice.company != profile.company or invoice.pos_profile != profile.name
            or invoice.branch != kot.branch):
        _deny()
    if kot.production:
        unit = frappe.get_doc("URY Production Unit", kot.production)
        _require_permission(unit, "read", user)
        if unit.pos_profile != profile.name or unit.branch != kot.branch:
            _deny()
    return kot


def can_read_kot(kot, user):
    try:
        require_kot_access(kot, user=user)
    except (frappe.PermissionError, frappe.DoesNotExistError):
        return False
    return True


def permitted_profiles(branch):
    result = []
    for row in frappe.get_list(
        "POS Profile", filters={"branch": branch}, fields=["name"],
        order_by="name asc", limit_page_length=0,
    ):
        try:
            result.append(require_profile_access(row.name))
        except (frappe.PermissionError, frappe.DoesNotExistError):
            continue
    return result


def get_kot_recipients(kot):
    """Enabled staff in this branch, plus administrators with actual access."""
    candidates = {"Administrator"}
    candidates.update(frappe.get_all(
        "URY User", filters={"parent": kot.branch, "parenttype": "Branch"},
        pluck="user", limit_page_length=0,
    ))
    candidates.update(frappe.get_all(
        "Has Role", filters={"role": "System Manager", "parenttype": "User"},
        pluck="parent", limit_page_length=0,
    ))
    candidates.discard(None)
    candidates.discard("Guest")
    users = frappe.get_all(
        "User", filters={"name": ["in", sorted(candidates)], "enabled": 1,
                         "user_type": "System User"},
        pluck="name", limit_page_length=0,
    )
    return [user for user in sorted(set(users)) if can_read_kot(kot, user)]


def publish_kot_event(kot, event, message):
    # Keep the existing event/payload contract. Target authenticated user rooms,
    # never the site-wide room; rolled-back transactions must emit nothing.
    for user in get_kot_recipients(kot):
        # An explicit room also prevents background task_id routing from
        # overriding the user destination or forcing immediate publication.
        frappe.publish_realtime(
            event, message, user=user, room=get_user_room(user), after_commit=True
        )
