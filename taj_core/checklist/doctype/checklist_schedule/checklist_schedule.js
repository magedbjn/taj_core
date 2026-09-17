frappe.ui.form.on("Checklist Schedule", {
    refresh(frm) {
        set_schedule_help(frm);
        const doc = frm.doc;
        if (!frm.is_new() && doc.schedule_type === "Manual") {
            frm.add_custom_button(__("Create Checklist"), () => create_manual_checklist(frm));
        }
    },

    schedule_type(frm) {
        clear_irrelevant_schedule_fields(frm);
        set_schedule_help(frm);
    }
});

function clear_irrelevant_schedule_fields(frm) {
    const type = frm.doc.schedule_type;

    if (!["Weekly", "Weeks of Month"].includes(type)) {
        frm.set_value("day_of_week", null);
    }

    if (type !== "Weeks of Month") {
        ["week_1", "week_2", "week_3", "week_4", "week_5"].forEach((fieldname) => {
            frm.set_value(fieldname, 0);
        });
    }

    if (!["Monthly", "Quarterly", "Yearly"].includes(type)) {
        frm.set_value("day_of_month", null);
    }

    if (type !== "Yearly") {
        frm.set_value("month_of_year", null);
    }

    if (!["Daily", "Weekly", "Monthly"].includes(type)) {
        frm.set_value("interval", 1);
    }
}

function set_schedule_help(frm) {
    const help = {
        Manual: __("No automatic checklist will be created."),
        Daily: __("Runs every N days starting from Start Date."),
        Weekly: __("Runs every N weeks on the selected weekday."),
        Monthly: __("Runs every N months on the selected day of month."),
        "Weeks of Month": __("Choose Week 1-5 and a weekday. Week 1 means days 1-7."),
        Quarterly: __("Runs every three months on the selected day of month."),
        Yearly: __("Runs once per year on the selected month and day.")
    };
    frm.set_df_property("schedule_type", "description", help[frm.doc.schedule_type] || "");
}
async function create_manual_checklist(frm) {
    const response = await frappe.call({
        method: "taj_core.checklist.doctype.checklist_schedule.checklist_schedule.create_checklist",
        args: { schedule_name: frm.doc.name },
        freeze: true,
        freeze_message: __("Creating checklist...")
    });

    const result = response.message || {};
    if (result.name) {
        frappe.set_route("Form", "Checklist Answer", result.name);
    }
}
