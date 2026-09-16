frappe.pages["chef-dashboard"].on_page_load = function (wrapper) {
    wrapper.chef_dashboard = new ChefDashboard(wrapper);
};

frappe.pages["chef-dashboard"].on_page_show = function (wrapper) {
    if (wrapper.chef_dashboard) {
        wrapper.chef_dashboard.refresh();
    }
};

class ChefDashboard {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.controls = {};
        this.data = null;
        this.loading = false;

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Chef Dashboard"),
            single_column: true,
        });

        this.render_layout();
        this.make_filters();
        this.bind_events();
    }

    render_layout() {
        this.$root = $(
            `<div class="chef-dashboard">
                <section class="chef-dashboard-toolbar">
                    <div class="chef-dashboard-filters">
                        <div class="chef-filter" data-filter="from_date"></div>
                        <div class="chef-filter" data-filter="to_date"></div>
                        <div class="chef-filter" data-filter="trial_user"></div>
                        <div class="chef-filter" data-filter="product_proposal"></div>
                        <div class="chef-filter" data-filter="status"></div>
                        <button class="btn btn-primary chef-apply-filters">${__("Apply Filters")}</button>
                        <button class="btn btn-default chef-reset-filters">${__("Current Month")}</button>
                    </div>
                </section>

                <section class="chef-kpis" aria-label="${__("Chef Dashboard KPIs")}">
                    ${this.kpi_card("products_worked_on", __("Products Worked On"))}
                    ${this.kpi_card("trials", __("Trials"))}
                    ${this.kpi_card("cooking_runs", __("Cooking Runs"))}
                    ${this.kpi_card("final_approved", __("Final Approved"))}
                    ${this.kpi_card("under_development", __("Under Development"))}
                    ${this.kpi_card("avg_trials_to_approval", __("Avg Trials to Approval"))}
                    ${this.kpi_card("avg_days_to_approval", __("Avg Days to Approval"))}
                </section>

                <section class="chef-chart-grid">
                    ${this.chart_card("trials-by-developer", __("Trials by Developer"))}
                    ${this.chart_card("approved-by-developer", __("Approved Trials by Developer"))}
                    ${this.chart_card("development-activity", __("Development Activity"), true)}
                    ${this.chart_card("product-status", __("Product Status"))}
                    ${this.chart_card("trials-by-product", __("Trials by Product"))}
                    ${this.chart_card("runs-by-developer", __("Cooking Runs by Developer"))}
                    ${this.chart_card("approved-over-time", __("Approved Products Over Time"))}
                    ${this.chart_card("trials-to-approval", __("Trials to Approval"))}
                </section>

                <section class="chef-detail-card" id="activity-details">
                    <div class="chef-detail-heading">
                        <div>
                            <h3>${__("Activity Details")}</h3>
                            <p>${__("Trials created, approved, or cooked during the selected period")}</p>
                        </div>
                        <div class="chef-detail-count"></div>
                    </div>
                    <div class="chef-detail-table-wrap">
                        <table class="table table-bordered chef-detail-table">
                            <thead>
                                <tr>
                                    <th>${__("Product Proposal")}</th>
                                    <th>${__("Trial")}</th>
                                    <th>${__("Trial Title")}</th>
                                    <th>${__("Developer")}</th>
                                    <th>${__("Trial Date")}</th>
                                    <th>${__("Status")}</th>
                                    <th>${__("Approval Date")}</th>
                                    <th>${__("Final")}</th>
                                    <th>${__("Cooking Runs")}</th>
                                    <th>${__("Latest Run")}</th>
                                </tr>
                            </thead>
                            <tbody></tbody>
                        </table>
                    </div>
                </section>
            </div>`
        ).appendTo(this.page.body);
    }

    kpi_card(key, label) {
        return `<button type="button" class="chef-kpi-card" data-kpi="${key}">
            <span class="chef-kpi-label">${label}</span>
            <span class="chef-kpi-value" data-kpi-value="${key}">0</span>
        </button>`;
    }

    chart_card(id, title, wide = false) {
        return `<article class="chef-chart-card${wide ? " chef-chart-wide" : ""}" data-chart-card="${id}">
            <div class="chef-chart-title">${title}</div>
            <div class="chef-chart-body" id="${id}"></div>
        </article>`;
    }

    make_filters() {
        const filter_defs = [
            {
                fieldname: "from_date",
                fieldtype: "Date",
                label: __("From Date"),
                reqd: 1,
                default: frappe.datetime.month_start(),
            },
            {
                fieldname: "to_date",
                fieldtype: "Date",
                label: __("To Date"),
                reqd: 1,
                default: frappe.datetime.get_today(),
            },
            {
                fieldname: "trial_user",
                fieldtype: "Link",
                label: __("Developer"),
                options: "User",
            },
            {
                fieldname: "product_proposal",
                fieldtype: "Link",
                label: __("Product Proposal"),
                options: "Product Proposal",
            },
            {
                fieldname: "status",
                fieldtype: "Select",
                label: __("Trial Status"),
                options: "\nDraft\nCompleted\nApproved\nRejected",
            },
        ];

        filter_defs.forEach((df) => {
            const parent = this.$root.find(`[data-filter="${df.fieldname}"]`);
            const control = frappe.ui.form.make_control({
                parent,
                df,
                render_input: true,
            });
            if (df.default) {
                control.set_value(df.default);
            }
            this.controls[df.fieldname] = control;
        });
    }

    bind_events() {
        this.$root.on("click", ".chef-apply-filters", () => this.refresh());
        this.$root.on("click", ".chef-reset-filters", async () => {
            await this.controls.from_date.set_value(frappe.datetime.month_start());
            await this.controls.to_date.set_value(frappe.datetime.get_today());
            await this.controls.trial_user.set_value("");
            await this.controls.product_proposal.set_value("");
            await this.controls.status.set_value("");
            this.refresh();
        });

        this.$root.on("click", ".chef-kpi-card, .chef-chart-card", (event) => {
            if ($(event.target).closest("a").length) return;
            const target = this.$root.find("#activity-details")[0];
            if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        });

        this.$root.on("click", ".js-open-trial", (event) => {
            event.preventDefault();
            const name = $(event.currentTarget).data("name");
            if (name) frappe.set_route("Form", "Product Proposal Trial", name);
        });

        this.$root.on("click", ".js-open-proposal", (event) => {
            event.preventDefault();
            const name = $(event.currentTarget).data("name");
            if (name) frappe.set_route("Form", "Product Proposal", name);
        });
    }

    get_filters() {
        const values = {};
        Object.entries(this.controls).forEach(([fieldname, control]) => {
            values[fieldname] = control.get_value() || "";
        });
        return values;
    }

    async refresh() {
        if (this.loading) return;
        this.loading = true;
        this.$root.addClass("is-loading");

        try {
            const response = await frappe.call({
                method: "taj_core.rnd.page.chef_dashboard.chef_dashboard.get_dashboard_data",
                args: this.get_filters(),
            });
            this.data = response.message || {};
            this.render();
        } catch (error) {
            console.error("Chef Dashboard refresh failed", error);
        } finally {
            this.loading = false;
            this.$root.removeClass("is-loading");
        }
    }

    render() {
        this.render_kpis(this.data.kpis || {});
        this.render_charts(this.data.charts || {});
        this.render_details(this.data.details || []);
    }

    render_kpis(kpis) {
        const values = {
            products_worked_on: kpis.products_worked_on || 0,
            trials: kpis.trials || 0,
            cooking_runs: kpis.cooking_runs || 0,
            final_approved: kpis.final_approved || 0,
            under_development: kpis.under_development || 0,
            avg_trials_to_approval: this.format_decimal(kpis.avg_trials_to_approval),
            avg_days_to_approval: this.format_decimal(kpis.avg_days_to_approval),
        };

        Object.entries(values).forEach(([key, value]) => {
            this.$root.find(`[data-kpi-value="${key}"]`).text(value);
        });
    }

    render_charts(charts) {
        this.render_value_chart("trials-by-developer", charts.trials_by_developer, "bar", __("Trials"));
        this.render_value_chart("approved-by-developer", charts.approved_trials_by_developer, "bar", __("Approved Trials"));
        this.render_activity_chart(charts.development_activity || [], charts.activity_granularity || "day");
        this.render_value_chart("product-status", charts.product_status, "pie", __("Products"));
        this.render_value_chart("trials-by-product", charts.trials_by_product, "bar", __("Trials"));
        this.render_value_chart("runs-by-developer", charts.cooking_runs_by_developer, "bar", __("Cooking Runs"));
        this.render_time_value_chart("approved-over-time", charts.approved_products_over_time || [], charts.activity_granularity || "day");
        this.render_value_chart("trials-to-approval", charts.trials_to_approval, "bar", __("Trials"));
    }

    render_value_chart(id, rows = [], type = "bar", dataset_name = __("Count")) {
        const target = this.$root.find(`#${id}`)[0];
        if (!target) return;
        target.innerHTML = "";
        if (!rows.length || rows.every((row) => !Number(row.value || 0))) {
            this.render_no_data(target);
            return;
        }

        new frappe.Chart(target, {
            data: {
                labels: rows.map((row) => row.label),
                datasets: [{ name: dataset_name, values: rows.map((row) => Number(row.value || 0)) }],
            },
            type,
            height: 260,
            animate: 1,
            truncateLegends: 1,
            valuesOverPoints: type === "bar" ? 1 : 0,
        });
    }

    render_activity_chart(rows, granularity) {
        const target = this.$root.find("#development-activity")[0];
        if (!target) return;
        target.innerHTML = "";
        if (!rows.length) {
            this.render_no_data(target);
            return;
        }

        new frappe.Chart(target, {
            data: {
                labels: rows.map((row) => this.format_period(row.period, granularity)),
                datasets: [
                    { name: __("Trials"), values: rows.map((row) => Number(row.trials || 0)) },
                    { name: __("Final Approved"), values: rows.map((row) => Number(row.final_approved || 0)) },
                ],
            },
            type: "line",
            height: 280,
            animate: 1,
            valuesOverPoints: 1,
            lineOptions: { hideDots: 0, regionFill: 0 },
        });
    }

    render_time_value_chart(id, rows, granularity) {
        const normalized = rows.map((row) => ({
            label: this.format_period(row.period, granularity),
            value: row.value,
        }));
        this.render_value_chart(id, normalized, "bar", __("Final Approved"));
    }

    render_no_data(target) {
        target.innerHTML = `<div class="chef-no-data">${__("No data for the selected filters")}</div>`;
    }

    render_details(rows) {
        const $tbody = this.$root.find(".chef-detail-table tbody");
        this.$root.find(".chef-detail-count").text(
            __("{0} records", [rows.length])
        );

        if (!rows.length) {
            $tbody.html(`<tr><td colspan="10" class="text-center text-muted">${__("No activity found")}</td></tr>`);
            return;
        }

        const html = rows.map((row) => {
            const proposal = this.escape(row.product_proposal);
            const product_name = this.escape(row.product_name || row.product_proposal);
            const trial = this.escape(row.trial);
            return `<tr>
                <td><a href="#" class="js-open-proposal" data-name="${proposal}">${product_name}</a></td>
                <td><a href="#" class="js-open-trial" data-name="${trial}">${trial}</a></td>
                <td>${this.escape(row.trial_title)}</td>
                <td>${this.escape(row.trial_user)}</td>
                <td>${this.format_date(row.posting_date)}</td>
                <td>${this.escape(row.status)}</td>
                <td>${row.approved_on ? this.format_date(row.approved_on) : ""}</td>
                <td>${row.is_final_trial ? __("Yes") : __("No")}</td>
                <td class="text-right">${Number(row.cooking_runs_in_period || 0)}</td>
                <td>${row.latest_run_date ? this.format_date(row.latest_run_date) : ""}</td>
            </tr>`;
        }).join("");
        $tbody.html(html);
    }

    format_period(value, granularity) {
        if (!value) return "";
        if (granularity === "month") {
            return moment(`${value}-01`).format("MMM YYYY");
        }
        return this.format_date(value);
    }

    format_date(value) {
        return value ? frappe.datetime.str_to_user(value) : "";
    }

    format_decimal(value) {
        const number = Number(value || 0);
        return Number.isInteger(number) ? number : number.toFixed(1);
    }

    escape(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }
}
