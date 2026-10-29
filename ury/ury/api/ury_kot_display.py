import json
import frappe
from ury.ury_pos.api import getBranch
from frappe.utils import get_datetime
from frappe import _
from ury.ury.api.kot_access import require_kot_access, permitted_profiles

# Function to set order status in a KOT document
@frappe.whitelist(methods=["POST"])
def serve_kot(name, time=None):
    if frappe.request and frappe.request.method != "POST":
        frappe.throw(_("POST requests only"), frappe.PermissionError)
    kot = require_kot_access(name, "write")
    if kot.docstatus != 1 or kot.type not in ("New Order", "Order Modified", "Duplicate"):
        frappe.throw(_("Only submitted preparation tickets can be served."))
    if kot.order_status == "Served":
        return {"status": "Served"}
    if kot.order_status != "Ready For Prepare":
        frappe.throw(_("This kitchen order is not ready for preparation."))
    current_time = get_datetime()
    minutes = max(0, (current_time - get_datetime(kot.creation)).total_seconds() / 60)
    frappe.db.set_value("URY KOT", kot.name, {
        "start_time_serv": current_time.strftime("%H:%M:%S"),
        "production_time": minutes, "order_status": "Served",
    })
    return {"status": "Served"}


# Function to mark it as verified in a cancel type KOT.
# The verifying user is derived from the session and must hold a manager-level
# role, so confirmation cannot be self-attributed or forged by the caller.
@frappe.whitelist(methods=["POST"])
def confirm_cancel_kot(name):
    if frappe.request and frappe.request.method != "POST":
        frappe.throw(_("POST requests only"), frappe.PermissionError)
    manager_roles = {"URY Manager", "URY Admin", "System Manager"}
    if frappe.session.user != "Administrator" and not manager_roles.intersection(frappe.get_roles()):
        frappe.throw(_("Only a manager can confirm a cancelled KOT."), frappe.PermissionError)
    kot = require_kot_access(name, "write")
    if kot.docstatus != 1 or kot.type not in ("Cancelled", "Partially cancelled"):
        frappe.throw(_("Only submitted cancellation tickets can be confirmed."))
    if not kot.verified:
        frappe.db.set_value("URY KOT", kot.name, {
            "verified": 1, "verified_by": frappe.session.user,
        })
    return {"status": "Confirmed"}


@frappe.whitelist(allow_guest=True)
def get_site_name():
    return {"site_name": frappe.local.site}

def build_dashboard_summary(kot_list):
    summary = {}

    for kot in kot_list:
        production = kot.get("production")

        if not production:
            continue

        if production not in summary:
            summary[production] = {
                "name": production,
                "active_orders": 0,
                "pending_orders": 0,
                "ready_orders": 0,
                "orders": []
            }

        summary[production]["active_orders"] += 1

        if kot.get("order_status") == "Ready For Prepare":
            summary[production]["ready_orders"] += 1
        else:
            summary[production]["pending_orders"] += 1

        summary[production]["orders"].append(kot)

    return list(summary.values())

@frappe.whitelist()
def kot_list():
    result = _list_kots("Ready For Prepare")
    result["Dashboard"] = build_dashboard_summary(result["KOT"])
    return result

@frappe.whitelist()
def served_kot_list():
    return _list_kots("Served")



def _list_kots(status):
    branch = getBranch()
    profiles = permitted_profiles(branch)
    profile = profiles[0] if profiles else None
    result = {
        "KOT": [], "Branch": branch,
        "kot_alert_time": profile.get("custom_kot_warning_time") if profile else None,
        "audio_alert": profile.get("custom_kot_alert") if profile else 0,
        "daily_order_number": profile.get("custom_reset_order_number_daily") if profile else 0,
    }
    if not profiles:
        return result
    rows = frappe.get_list(
        "URY KOT", fields=["name"],
        filters={
            "branch": branch, "pos_profile": ["in", [p.name for p in profiles]],
            "order_status": status, "docstatus": 1, "verified": 0,
            "type": ["in", ["New Order", "Order Modified", "Duplicate", "Cancelled", "Partially cancelled"]],
            "creation": [">=", frappe.utils.add_to_date(frappe.utils.now(), hours=-3)],
        }, order_by="creation desc, name desc", limit_page_length=0,
    )
    for row in rows:
        try:
            kot = require_kot_access(row.name)
        except (frappe.PermissionError, frappe.DoesNotExistError):
            continue
        if kot.production:
            unit = frappe.get_doc("URY Production Unit", kot.production)
            if unit.enable_order_type_wise_display_on_mosaic:
                order_type = frappe.db.get_value("POS Invoice", kot.invoice, "order_type")
                if order_type not in [r.order_type for r in unit.get("order_type", [])]:
                    continue
        result["KOT"].append(json.loads(frappe.as_json(kot)))
    return result
