import frappe
from html import escape
from ury.ury.api.kot_access import require_kot_access, can_read_kot
from frappe.utils import add_to_date, now_datetime


def get_users_with_role(role_name):
    users_with_role = frappe.get_all(
        "Has Role", filters={"role": role_name}, fields=["parent as user"]
    )

    user_ids = [user["user"] for user in users_with_role]
    user_details = frappe.get_all(
        "User",
        filters={"name": ("in", user_ids), "enabled": 1, "user_type": "System User"},
        fields=["name", "full_name", "email"],
    )

    return user_details


@frappe.whitelist(methods=["POST"])
def order_delay_notification(id):
    if frappe.request and frappe.request.method != "POST":
        frappe.throw("POST requests only", frappe.PermissionError)
    kot = require_kot_access(id, "write")
    if kot.docstatus != 1 or kot.order_status != "Ready For Prepare":
        return
    subject = f"Order {kot.invoice} / {kot.name} Delayed"
    message = (
        "<ul><li><b>Table:</b> " + escape(kot.restaurant_table or "Take Away")
        + "</li><li><b>Order Type:</b> " + escape(kot.type or "") + "</li></ul>"
    )
    roles = frappe.get_all(
        "URY Notification Recipient", fields=["receiver_by_role"],
        filters={"parent": kot.pos_profile, "parenttype": "POS Profile"},
        order_by="idx",
    )
    notified = set()
    for row in roles:
        for user in get_users_with_role(row.receiver_by_role):
            if user.name not in notified and can_read_kot(kot, user.name):
                create_system_notification(message, user.name, subject)
                notified.add(user.name)


def create_system_notification(message, user, subject):
    recent_duplicate = frappe.db.exists(
        "Notification Log",
        {
            "for_user": user,
            "subject": subject,
            "creation": [">", add_to_date(now_datetime(), minutes=-5)],
        },
    )
    if recent_duplicate:
        return

    communication = frappe.get_doc(
        {
            "doctype": "Notification Log",
            "email_content": message,
            "for_user": user,
            "subject": subject,
            "type": "Alert",
        }
    )

    communication.insert(ignore_permissions=True)
