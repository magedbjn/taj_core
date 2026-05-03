function add_material_coverage_legend(report) {
    const legend_id = "production-plan-material-coverage-legend";

    // Prevent duplicate legend after refresh / rerender
    $(`#${legend_id}`).remove();

    const html = `
        <div id="${legend_id}" style="
            margin: 10px 0 12px 0;
            padding: 10px 12px;
            border: 1px solid #d1d8dd;
            border-radius: 6px;
            background: #fafafa;
        ">
            <div style="font-weight: bold; margin-bottom: 8px;">
                ${__("Color Legend")}
            </div>

            <div style="
                display: flex;
                flex-wrap: wrap;
                gap: 10px 18px;
                font-size: 12px;
                line-height: 1.6;
            ">
                <div>
                    <span style="
                        display:inline-block;
                        width:14px;
                        height:14px;
                        background:#fff3cd;
                        border:1px solid #e0b65c;
                        border-radius:3px;
                        vertical-align:middle;
                    "></span>
                    <span style="margin-left:5px; color:#7a4f00; font-weight:bold;">
                        ${__("Hidden from MR Items")}
                    </span>
                    <span style="margin-left:4px;">
                        ${__("- Projected Qty covers the requirement")}
                    </span>
                </div>

                <div>
                    <span style="
                        display:inline-block;
                        width:14px;
                        height:14px;
                        background:#ffffff;
                        border:2px solid #c0392b;
                        border-radius:3px;
                        vertical-align:middle;
                    "></span>
                    <span style="margin-left:5px; color:#c0392b; font-weight:bold;">
                        ${__("Need Material Request / Shortage")}
                    </span>
                </div>

                <div>
                    <span style="
                        display:inline-block;
                        width:14px;
                        height:14px;
                        background:#ffffff;
                        border:2px solid #d35400;
                        border-radius:3px;
                        vertical-align:middle;
                    "></span>
                    <span style="margin-left:5px; color:#d35400; font-weight:bold;">
                        ${__("Covered by Open Material Request / Indented Qty")}
                    </span>
                </div>

                <div>
                    <span style="
                        display:inline-block;
                        width:14px;
                        height:14px;
                        background:#ffffff;
                        border:2px solid #16a085;
                        border-radius:3px;
                        vertical-align:middle;
                    "></span>
                    <span style="margin-left:5px; color:#16a085; font-weight:bold;">
                        ${__("Covered by Stock or Projected Qty")}
                    </span>
                </div>

                <div>
                    <span style="
                        display:inline-block;
                        width:14px;
                        height:14px;
                        background:#ffffff;
                        border:2px solid #8e44ad;
                        border-radius:3px;
                        vertical-align:middle;
                    "></span>
                    <span style="margin-left:5px; color:#8e44ad; font-weight:bold;">
                        ${__("Ignore Projected Qty is enabled")}
                    </span>
                </div>
            </div>
        </div>
    `;

    const $main = $(report.page.main);

    if ($main.find(".result").length) {
        $main.find(".result").before(html);
    } else if ($main.find(".report-wrapper").length) {
        $main.find(".report-wrapper").before(html);
    } else {
        $main.prepend(html);
    }
}


frappe.query_reports["Production Plan Material Coverage"] = {
    filters: [
        {
            fieldname: "production_plan",
            label: __("Production Plan"),
            fieldtype: "Link",
            options: "Production Plan",
            reqd: 1,
        },
        {
            fieldname: "item_code",
            label: __("Item Code"),
            fieldtype: "Link",
            options: "Item",
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse"),
            fieldtype: "Link",
            options: "Warehouse",
        },
        {
            fieldname: "ignore_projected_qty",
            label: __("Ignore Projected Qty"),
            fieldtype: "Check",
            default: 0,
        },
        {
            fieldname: "show_only_shortage",
            label: __("Show Only Shortage"),
            fieldtype: "Check",
            default: 0,
        },
        {
            fieldname: "show_only_hidden_from_mr",
            label: __("Show Only Hidden from MR Items"),
            fieldtype: "Check",
            default: 0,
        },
        {
            fieldname: "show_only_covered_by_open_mr",
            label: __("Show Only Covered by Open MR"),
            fieldtype: "Check",
            default: 0,
        },
        {
            fieldname: "show_only_covered_by_projected_qty",
            label: __("Show Only Covered / No Shortage"),
            fieldtype: "Check",
            default: 0,
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) {
            return value;
        }

        const is_hidden_from_mr =
            data.is_hidden_from_mr == 1 || data.is_hidden_from_mr === true;

        // Highlight full row cells for items hidden from mr_items
        if (
            is_hidden_from_mr &&
            !["mr_visibility", "decision"].includes(column.fieldname)
        ) {
            value = `<span style="
                display:block;
                background-color:#fff3cd;
                color:#7a4f00;
                padding:2px 4px;
                border-radius:4px;
                font-weight:${["item_code", "hidden_reason"].includes(column.fieldname) ? "bold" : "normal"};
            ">${value}</span>`;
        }

        // MR Visibility coloring
        if (column.fieldname === "mr_visibility") {
            if (is_hidden_from_mr) {
                return `<span style="
                    display:inline-block;
                    color:#9a4d00;
                    background-color:#fff3cd;
                    font-weight:bold;
                    padding:3px 6px;
                    border-radius:4px;
                ">${value}</span>`;
            }

            if (data.mr_visibility_code === "visible_in_mr_items") {
                return `<span style="
                    color:#0f7b0f;
                    font-weight:bold;
                ">${value}</span>`;
            }

            if (data.mr_visibility_code === "visible_ignore_projected_qty") {
                return `<span style="
                    color:#8e44ad;
                    font-weight:bold;
                ">${value}</span>`;
            }
        }

        // Decision coloring
        if (column.fieldname === "decision") {
            if (data.decision_code === "need_material_request") {
                return `<span style="
                    color:#c0392b;
                    font-weight:bold;
                ">${value}</span>`;
            }

            if (data.decision_code === "covered_by_open_mr") {
                return `<span style="
                    display:inline-block;
                    color:#d35400;
                    background-color:#fff3cd;
                    font-weight:bold;
                    padding:3px 6px;
                    border-radius:4px;
                ">${value}</span>`;
            }

            if (
                data.decision_code === "covered_by_stock" ||
                data.decision_code === "covered_by_projected_qty"
            ) {
                return `<span style="
                    color:#16a085;
                    font-weight:bold;
                ">${value}</span>`;
            }

            if (data.decision_code === "ignore_projected_qty") {
                return `<span style="
                    color:#8e44ad;
                    font-weight:bold;
                ">${value}</span>`;
            }
        }

        // Shortage Qty coloring
        if (column.fieldname === "shortage_qty" && flt(data.shortage_qty) > 0) {
            return `<span style="
                color:#c0392b;
                font-weight:bold;
            ">${value}</span>`;
        }

        // Indented Qty coloring
        if (column.fieldname === "indented_qty" && flt(data.indented_qty) > 0) {
            return `<span style="
                color:#d35400;
                font-weight:bold;
            ">${value}</span>`;
        }

        // Projected Qty coloring when it covers requirement
        if (
            column.fieldname === "projected_qty" &&
            flt(data.projected_qty) >= flt(data.required_bom_qty)
        ) {
            return `<span style="
                color:#16a085;
                font-weight:bold;
            ">${value}</span>`;
        }

        return value;
    },

    onload: function (report) {
        report.page.add_inner_button(__("Open Production Plan"), function () {
            const production_plan = report.get_filter_value("production_plan");

            if (!production_plan) {
                frappe.msgprint(__("Please select Production Plan first."));
                return;
            }

            frappe.set_route("Form", "Production Plan", production_plan);
        });

        setTimeout(function () {
            add_material_coverage_legend(report);
        }, 300);
    },

    after_datatable_render: function () {
        const report = frappe.query_report;

        if (report) {
            add_material_coverage_legend(report);
        }
    },
};