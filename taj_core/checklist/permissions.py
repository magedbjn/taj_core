import frappe


MANAGER_ROLES = {"Checklist Manager", "System Manager"}


def is_checklist_manager(user=None):
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    return bool(MANAGER_ROLES.intersection(roles))


def checklist_answer_has_permission(doc, user=None, permission_type=None):
    user = user or frappe.session.user

    if is_checklist_manager(user):
        return True

    if permission_type == "create":
        return False

    assignment_type = getattr(doc, "assignment_type", None)
    assigned_user = getattr(doc, "assigned_user", None)

    if assignment_type == "Specific User":
        return assigned_user == user

    if assignment_type == "Any User in Department":
        return True

    return False


def checklist_answer_query_conditions(user=None):
    user = user or frappe.session.user

    if is_checklist_manager(user):
        return ""

    user_escaped = frappe.db.escape(user)

    return f"""
        (
            `tabChecklist Answer`.`assignment_type` = 'Any User in Department'
            OR (
                `tabChecklist Answer`.`assignment_type` = 'Specific User'
                AND `tabChecklist Answer`.`assigned_user` = {user_escaped}
            )
        )
    """