# جلب آخر مكونات الراتب
import frappe
from frappe import _
from frappe.utils import flt, getdate
from datetime import datetime

try:
    from frappe.utils.safe_exec import safe_eval
except ImportError:
    # للإصدارات القديمة
    from frappe.utils import safe_eval

def get_last_assignment(employee: str):
    """Fetch the latest valid Salary Structure Assignment"""
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("❌ Employee {0} does not exist").format(employee))

    today = getdate()
    
    # ✅ استخدام get_all للحصول على أحدث تعيين (بدون to_date)
    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={
            "employee": employee,
            "docstatus": 1,
            "from_date": ["<=", today]
        },
        fields=["name", "salary_structure", "from_date", "base", "variable"],
        order_by="from_date desc",
        limit=1
    )

    if not assignments:
        frappe.throw(_("❌ No active Salary Structure Assignment found for employee {0}").format(employee))

    return assignments[0]


def validate_salary_structure(salary_structure: str):
    """Validate salary structure exists and is submitted"""
    if not frappe.db.exists("Salary Structure", salary_structure):
        frappe.throw(_("❌ Salary Structure {0} does not exist").format(salary_structure))
    
    structure = frappe.get_doc("Salary Structure", salary_structure)
    if structure.docstatus != 1:
        frappe.throw(_("❌ Salary Structure {0} is not submitted").format(salary_structure))
    
    return structure


def build_context(employee: str, base: float, variable: float):
    """Prepare safe context for evaluation"""
    emp_doc = frappe.get_doc("Employee", employee)
    return {
        "base": flt(base),
        "variable": flt(variable),
        "employee": {
            "name": emp_doc.name,
            "department": emp_doc.department,
            "designation": emp_doc.designation,
            "grade": emp_doc.grade,
            "company": emp_doc.company,
            "date_of_joining": emp_doc.date_of_joining,
            "branch": emp_doc.branch,
            "employment_type": emp_doc.employment_type
        }
    }


def calculate_components(components, context):
    """Calculate salary components safely"""
    result = []
    amounts = []

    for comp in components:
        amount = 0
        skip_component = False

        # ✅ شرط مكون الراتب
        if comp.condition and comp.condition.strip():
            try:
                if not safe_eval(comp.condition.strip(), context):
                    skip_component = True
            except Exception as ex:
                frappe.log_error(
                    title=f"Condition error in {comp.salary_component}",
                    message=f"Condition: {comp.condition}\nError: {str(ex)}"
                )
                skip_component = True

        if skip_component:
            continue

        # ✅ قيمة بالمعادلة أو ثابتة
        if comp.amount_based_on_formula and comp.formula and comp.formula.strip():
            try:
                amount = safe_eval(comp.formula.strip(), context)
            except Exception as ex:
                frappe.log_error(
                    title=f"Formula error in {comp.salary_component}",
                    message=f"Formula: {comp.formula}\nError: {str(ex)}"
                )
                amount = 0
        else:
            amount = flt(comp.amount or 0)

        amounts.append(amount)
        result.append({
            "component": comp.salary_component,
            "amount": round(amount, 2),
            "formula": comp.formula or "",
            "condition": comp.condition or ""
        })

    total = round(sum(amounts), 2) if amounts else 0
    return result, total


def calculate_salary(employee: str):
    """Main function to calculate salary breakdown for an employee"""
    try:
        assignment = get_last_assignment(employee)
        base = assignment.get("base", 0)
        variable = assignment.get("variable", 0)

        # ✅ التحقق من هيكل الراتب
        structure_doc = validate_salary_structure(assignment.salary_structure)
        
        context = build_context(employee, base, variable)
        
        earnings, total_earnings = calculate_components(structure_doc.earnings, context)
        deductions, total_deductions = calculate_components(structure_doc.deductions, context)

        net_pay = round(total_earnings - total_deductions, 2)

        return {
            "employee": employee,
            "assignment": assignment.name,
            "salary_structure": assignment.salary_structure,
            "base": round(flt(base), 2),
            "variable": round(flt(variable), 2),
            "from_date": assignment.from_date,
            "to_date": assignment.to_date,
            "earnings": earnings,
            "deductions": deductions,
            "total_earnings": total_earnings,
            "total_deductions": total_deductions,
            "net_pay": net_pay,
        }
    
    except Exception as e:
        frappe.log_error(
            title=f"Salary calculation failed for employee {employee}",
            message=str(e)
        )
        frappe.throw(_("❌ Failed to calculate salary: {0}").format(str(e)))