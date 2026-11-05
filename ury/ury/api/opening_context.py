"""Resolve an opening profile without inheriting an inaccessible site company."""
import frappe
from frappe import _


def resolve_opening_context(pos_profile=None):
    from ury.ury_pos.api import getPosProfile, _get_allowed_pos_profiles, _require_ury_profile_access

    user = frappe.session.user
    data = None
    name = pos_profile
    if not name:
        try:
            data = getPosProfile()
            name = data.get("pos_profile") if data else None
        except frappe.PermissionError:
            raise  # Do not hide an actual branch/profile authorization failure.
        except frappe.ValidationError:
            data = None  # Missing branch setup may still permit profile selection.

    profile = _require_ury_profile_access(name) if name else None
    company = profile.company if profile else None
    allowed = _get_allowed_pos_profiles(company, user) if company else []

    if not company:
        # Pass the effective user explicitly and accept defaults only when that
        # user can read the company and has an assigned/available profile in it.
        for key in ("Company", "company"):
            candidate = frappe.defaults.get_user_default(key, user=user)
            if not candidate:
                continue
            try:
                candidate_profiles = _get_allowed_pos_profiles(candidate, user)
            except frappe.PermissionError:
                continue
            if candidate_profiles:
                company, allowed = candidate, candidate_profiles
                break

    if not company:
        # No usable default: infer only from permission-filtered, independently
        # authorized profiles when they identify a single company. Never choose
        # a company's global default or guess across multiple allowed companies.
        companies = set()
        for row in frappe.get_list("POS Profile", filters={"disabled": 0},
                                   fields=["name"], limit_page_length=0):
            try:
                candidate = _require_ury_profile_access(row.name)
            except frappe.PermissionError:
                continue
            companies.add(candidate.company)
        if len(companies) != 1:
            frappe.throw(_("Select an assigned POS Profile or set an allowed default Company for this user."))
        company = companies.pop()
        allowed = _get_allowed_pos_profiles(company, user)

    if name and name not in {row["name"] for row in allowed}:
        frappe.throw(_("The selected POS Profile is not allowed for this user and company."), frappe.PermissionError)
    if not name and allowed:
        name = allowed[0]["name"]
        profile = _require_ury_profile_access(name)
    if profile and not data:
        data = {"pos_profile": profile.name, "branch": profile.branch, "company": profile.company,
                "restaurant": profile.restaurant, "warehouse": profile.warehouse, "cashier": user,
                "multiple_cashier": profile.custom_enable_multiple_cashier,
                "custom_daily_pos_close": profile.custom_daily_pos_close}
    return company, allowed, data, name
