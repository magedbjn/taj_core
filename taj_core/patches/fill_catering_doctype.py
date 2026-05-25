import frappe


def execute():
    seed_catering_menu_row_type()
    seed_catering_meal_type()
    seed_catering_dish_type()
    seed_catering_dish_supply_mode()
    seed_catering_menu_section()
    seed_catering_workstation_calculation_methods()

def upsert(doctype, name_field, rows):
    for row in rows:
        name = row[name_field]
        if frappe.db.exists(doctype, name):
            doc = frappe.get_doc(doctype, name)
            doc.update(row)
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.get_doc({
                "doctype": doctype,
                **row
            })
            doc.insert(ignore_permissions=True)


def seed_catering_menu_row_type():
    upsert("Catering Menu Row Type", "row_type", [
        {"row_type": "Section", "row_type_arabic": "قسم", "is_active": 1, "is_calculated": 0, "is_visible_in_menu_print": 1, "sort_order": 10},
        {"row_type": "Item", "row_type_arabic": "صنف", "is_active": 1, "is_calculated": 1, "is_visible_in_menu_print": 1, "sort_order": 20},
        {"row_type": "New Item", "row_type_arabic": "صنف إنتاجي", "is_active": 1, "is_calculated": 0, "is_visible_in_menu_print": 1, "sort_order": 30},
        {"row_type": "Sub Item", "row_type_arabic": "مادة خام", "is_active": 1, "is_calculated": 1, "is_visible_in_menu_print": 0, "sort_order": 40},
    ])


def seed_catering_meal_type():
    upsert("Catering Meal Type", "meal_type", [
        {"meal_type": "Breakfast", "meal_type_arabic": "الفطور", "short_code": "B", "is_active": 1, "is_main_meal": 1, "sort_order": 100},
        {"meal_type": "Lunch", "meal_type_arabic": "الغداء", "short_code": "L", "is_active": 1, "is_main_meal": 1, "sort_order": 200},
        {"meal_type": "Dinner", "meal_type_arabic": "العشاء", "short_code": "D", "is_active": 1, "is_main_meal": 1, "sort_order": 300},
        {"meal_type": "Snack", "meal_type_arabic": "سناك", "short_code": "S", "is_active": 1, "is_main_meal": 0, "sort_order": 400},
    ])


def seed_catering_dish_supply_mode():
    upsert("Catering Dish Supply Mode", "supply_mode", [
        {"supply_mode": "Direct to Buffet", "supply_mode_arabic": "مباشر للبوفيه", "is_active": 1, "sort_order": 100},
        {"supply_mode": "Cooked On Site", "supply_mode_arabic": "طبخ في الموقع", "is_active": 1, "sort_order": 200},
        {"supply_mode": "Reheated On Site", "supply_mode_arabic": "تسخين في الموقع", "is_active": 1, "sort_order": 300},
    ])


def seed_catering_dish_type():
    upsert("Catering Dish Type", "dish_type", [
        {
            "dish_type": "Disposable Item",
            "dish_type_arabic": "مستهلكات",
            "is_active": 1,
            "requires_item_code": 1,
            "requires_recipe": 0,
            "include_in_purchase": 1,
            "include_in_production": 0,
            "show_in_menu_print": 0,
            "sort_order": 100,
        },
        {
            "dish_type": "Finished Product",
            "dish_type_arabic": "منتج نهائي",
            "is_active": 1,
            "requires_item_code": 1,
            "requires_recipe": 0,
            "include_in_purchase": 1,
            "include_in_production": 1,
            "show_in_menu_print": 1,
            "sort_order": 200,
        },
        {
            "dish_type": "Prepared Dish",
            "dish_type_arabic": "طبق محضر",
            "is_active": 1,
            "requires_item_code": 0,
            "requires_recipe": 1,
            "include_in_purchase": 1,
            "include_in_production": 1,
            "show_in_menu_print": 1,
            "sort_order": 300,
        },
        {
            "dish_type": "Direct Item",
            "dish_type_arabic": "صنف مباشر",
            "is_active": 1,
            "requires_item_code": 1,
            "requires_recipe": 0,
            "include_in_purchase": 1,
            "include_in_production": 0,
            "show_in_menu_print": 1,
            "sort_order": 400,
        },
        {
            "dish_type": "Display Only",
            "dish_type_arabic": "عرض فقط",
            "is_active": 1,
            "requires_item_code": 0,
            "requires_recipe": 0,
            "include_in_purchase": 0,
            "include_in_production": 0,
            "show_in_menu_print": 1,
            "sort_order": 500,
        },
    ])


def seed_catering_menu_section():
    upsert("Catering Menu Section", "section", [
        {"section": "Main Dishes", "section_name_arabic": "الأطباق الرئيسية", "is_active": 1, "is_main_dishes": 1, "sort_order": 10},
        {"section": "Side Dishes", "section_name_arabic": "الأطباق الجانبية", "is_active": 1, "is_main_dishes": 0, "sort_order": 20},
        {"section": "Beverages", "section_name_arabic": "المشروبات", "is_active": 1, "is_main_dishes": 0, "sort_order": 30},
        {"section": "Snacks", "section_name_arabic": "السناكات", "is_active": 1, "is_main_dishes": 0, "sort_order": 40},
        {"section": "Fruits", "section_name_arabic": "الفواكه", "is_active": 1, "is_main_dishes": 0, "sort_order": 50},
        {"section": "Disposables", "section_name_arabic": "المستهلكات", "is_active": 1, "is_main_dishes": 0, "sort_order": 60},
    ])

def seed_catering_workstation_calculation_methods():
    upsert("Catering Workstation Calculation Method", "calculation_method", [
        {
            "calculation_method": "Direct Quantity Load",
            "calculation_method_arabic": "تحميل مباشر بالكمية",
            "note": (
                "Use when workstation runs are based on total cooking quantity. "
                "Example: Kettle capacity is 300 KG per run. "
                "If total cooking quantity is 412 KG, runs = ceil(412 / 300) = 2."
            ),
        },
        {
            "calculation_method": "Receiving Unit Load",
            "calculation_method_arabic": "تحميل بوحدة الاستلام",
            "note": (
                "Use when workstation runs are based on receiving units such as Carton, Bag, or Basket. "
                "Example: receiving quantity is 20 Carton and workstation load is 5 Carton per run, "
                "runs = ceil(20 / 5) = 4."
            ),
        },
        {
            "calculation_method": "Output Unit Load",
            "calculation_method_arabic": "تحميل بوحدة المخرج",
            "note": (
                "Use when workstation runs are based on output units such as Basket, Chafing Dish, or Container. "
                "Example: output quantity is 24 Basket and workstation load is 20 Basket per run, "
                "runs = ceil(24 / 20) = 2."
            ),
        },
    ])