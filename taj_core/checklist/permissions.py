import frappe

DEFAULT_MANAGER_ROLES = {"Checklist Manager", "System Manager", "Department Manager"}


def _get_roles_from_settings():
    roles = set(DEFAULT_MANAGER_ROLES)

    if frappe.db.exists("DocType", "Checklist Settings"):
        try:
            doc = frappe.get_single("Checklist Settings")
            extra = getattr(doc, "manager_roles", "") or ""
            roles.update({r.strip() for r in extra.splitlines() if r and r.strip()})
        except Exception:
            pass

    return roles


def is_checklist_manager(user=None):
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    return bool(_get_roles_from_settings().intersection(roles))


def _get_user_departments(user=None):
    user = user or frappe.session.user

    if not frappe.db.exists("DocType", "Employee"):
        return set()

    employees = frappe.get_all(
        "Employee",
        filters={"user_id": user, "status": "Active"},
        pluck="department",
    )
    return {d for d in employees if d}


def checklist_answer_has_permission(doc, user=None, permission_type=None):
    user = user or frappe.session.user

    if is_checklist_manager(user):
        return True

    assignment_type = getattr(doc, "assignment_type", None)
    assigned_user = getattr(doc, "assigned_user", None)
    answer_by = getattr(doc, "answer_by", None)
    taken_by = getattr(doc, "taken_by", None)
    department = getattr(doc, "department", None)

    if permission_type == "create":
        return False

    if assignment_type == "Specific User":
        return assigned_user == user or answer_by == user or taken_by == user

    if assignment_type == "Any User in Department":
        user_departments = _get_user_departments(user)
        if department and department not in user_departments:
            return False
        return (not taken_by) or taken_by == user or answer_by == user or assigned_user == user

    return answer_by == user or taken_by == user


def checklist_answer_query_conditions(user=None):
    user = user or frappe.session.user

    if is_checklist_manager(user):
        return ""

    user_escaped = frappe.db.escape(user)
    departments = list(_get_user_departments(user))
    if departments:
        dept_sql = ", ".join(frappe.db.escape(d) for d in departments)
        dept_clause = f"`tabChecklist Answer`.`department` IN ({dept_sql})"
    else:
        dept_clause = "1 = 0"

    return f"""
        (
            (
                `tabChecklist Answer`.`assignment_type` = 'Specific User'
                AND `tabChecklist Answer`.`assigned_user` = {user_escaped}
            )
            OR (
                `tabChecklist Answer`.`assignment_type` = 'Any User in Department'
                AND {dept_clause}
                AND (
                    ifnull(`tabChecklist Answer`.`taken_by`, '') = ''
                    OR `tabChecklist Answer`.`taken_by` = {user_escaped}
                    OR ifnull(`tabChecklist Answer`.`answer_by`, '') = {user_escaped}
                )
            )
            OR ifnull(`tabChecklist Answer`.`answer_by`, '') = {user_escaped}
            OR ifnull(`tabChecklist Answer`.`taken_by`, '') = {user_escaped}
        )
    """
