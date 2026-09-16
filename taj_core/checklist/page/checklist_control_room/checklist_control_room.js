frappe.pages["checklist-control-room"].on_page_load = function (wrapper) {
    new ChecklistControlRoomPage(wrapper);
};

class ChecklistControlRoomPage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.data = null;

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Checklist Control Room"),
            single_column: true,
        });

        this.render_layout();
        this.bind_events();
        this.load_data();
    }

    escape(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }

    render_layout() {
        $(this.page.body).html(`
            <div class="ccr-page">
                <section class="ccr-hero">
                    <div>
                        <div class="ccr-eyebrow">${__("Checklist Management")}</div>
                        <h2>${__("Control Room")}</h2>
                        <div class="ccr-subtitle">${__("Live operational view for managers, QC, and checklist owners.")}</div>
                    </div>
                    <div class="ccr-hero-actions">
                        <button class="btn btn-default ccr-today" type="button">${__("Checklist Today")}</button>
                        <button class="btn btn-default ccr-classic" type="button">${__("Classic Manager Dashboard")}</button>
                        <button class="btn btn-primary ccr-refresh" type="button">${__("Refresh")}</button>
                    </div>
                </section>

                <section class="ccr-filter-bar">
                    <div class="ccr-date-control"></div>
                    <div class="ccr-department-control"></div>
                    <button class="btn btn-sm btn-default ccr-apply" type="button">${__("Apply")}</button>
                    <button class="btn btn-sm btn-default ccr-reset" type="button">${__("Reset")}</button>
                </section>

                <section class="ccr-kpis">
                    ${this.kpi("completion_percent", __("Completion"), "%", "success")}
                    ${this.kpi("not_started", __("Not Started"), "○", "neutral")}
                    ${this.kpi("in_progress", __("In Progress"), "◔", "progress")}
                    ${this.kpi("overdue", __("Overdue"), "!", "danger")}
                    ${this.kpi("issues", __("Issues"), "!", "warning")}
                    ${this.kpi("critical", __("Critical"), "!!", "critical")}
                </section>

                <section class="ccr-action-kpis">
                    ${this.action_kpi("open", __("Open Actions"), "○", "neutral")}
                    ${this.action_kpi("overdue", __("Action Overdue"), "!", "danger")}
                    ${this.action_kpi("critical", __("Action Critical"), "!!", "critical")}
                    ${this.action_kpi("pending_verification", __("Pending Verification"), "✓?", "warning")}
                </section>

                <section class="ccr-grid">
                    <div class="ccr-panel ccr-health-panel">
                        <div class="ccr-panel-head">
                            <div>
                                <h3>${__("Department Health")}</h3>
                                <span>${__("Completion, overdue work, and open issues by department")}</span>
                            </div>
                        </div>
                        <div class="ccr-health-list"></div>
                    </div>

                    <div class="ccr-panel ccr-attention-panel">
                        <div class="ccr-panel-head">
                            <div>
                                <h3>${__("Needs Attention")}</h3>
                                <span>${__("Critical, overdue, issue, or production-start exceptions")}</span>
                            </div>
                            <span class="ccr-attention-count">0</span>
                        </div>
                        <div class="ccr-attention-list"></div>
                    </div>
                </section>

                <section class="ccr-grid ccr-lower-grid">
                    <div class="ccr-panel">
                        <div class="ccr-panel-head">
                            <div>
                                <h3>${__("Team Workload")}</h3>
                                <span>${__("Who currently owns work and where delays exist")}</span>
                            </div>
                        </div>
                        <div class="ccr-team-list"></div>
                    </div>

                    <div class="ccr-panel">
                        <div class="ccr-panel-head">
                            <div>
                                <h3>${__("Operational Buckets")}</h3>
                                <span>${__("Open the work behind each state")}</span>
                            </div>
                        </div>
                        <div class="ccr-buckets"></div>
                    </div>
                </section>

                <section class="ccr-panel ccr-actions-panel">
                    <div class="ccr-panel-head">
                        <div>
                            <h3>${__("Open Checklist Actions")}</h3>
                            <span>${__("Follow-up remains open even when a later inspection observes Pass")}</span>
                        </div>
                        <span class="ccr-open-action-count">0</span>
                    </div>
                    <div class="ccr-action-list"></div>
                </section>
            </div>
        `);

        this.dateControl = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".ccr-date-control").get(0),
            df: { fieldtype: "Date", fieldname: "date", label: __("Date"), default: frappe.datetime.get_today() },
            render_input: true,
        });
        this.dateControl.set_value(frappe.datetime.get_today());

        this.departmentControl = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".ccr-department-control").get(0),
            df: { fieldtype: "Link", fieldname: "department", label: __("Department"), options: "Department" },
            render_input: true,
        });
    }

    kpi(key, label, symbol, tone) {
        return `
            <div class="ccr-kpi ccr-kpi-${tone}">
                <div class="ccr-kpi-symbol">${symbol}</div>
                <div>
                    <div class="ccr-kpi-label">${this.escape(label)}</div>
                    <strong class="ccr-kpi-value" data-kpi="${key}">0</strong>
                </div>
            </div>
        `;
    }

    action_kpi(key, label, symbol, tone) {
        return `
            <div class="ccr-kpi ccr-kpi-${tone}">
                <div class="ccr-kpi-symbol">${symbol}</div>
                <div>
                    <div class="ccr-kpi-label">${this.escape(label)}</div>
                    <strong class="ccr-kpi-value" data-action-kpi="${key}">0</strong>
                </div>
            </div>
        `;
    }

    bind_events() {
        $(this.page.body).on("click", ".ccr-refresh", () => this.load_data());
        $(this.page.body).on("click", ".ccr-apply", () => this.load_data(this.dateControl.get_value(), this.departmentControl.get_value()));
        $(this.page.body).on("click", ".ccr-reset", () => {
            this.dateControl.set_value(frappe.datetime.get_today());
            this.departmentControl.set_value("");
            this.load_data();
        });
        $(this.page.body).on("click", ".ccr-today", () => frappe.set_route("checklist-today"));
        $(this.page.body).on("click", ".ccr-classic", () => frappe.set_route("checklist-admin"));
        $(this.page.body).on("click", "[data-checklist-name]", (event) => {
            const name = $(event.currentTarget).data("checklist-name");
            if (name) frappe.set_route("Form", "Checklist Answer", name);
        });
        $(this.page.body).on("click", "[data-action-name]", (event) => {
            const name = $(event.currentTarget).data("action-name");
            if (name) frappe.set_route("Form", "Checklist Action", name);
        });
    }

    async load_data(searchDate = null, department = null) {
        const $refresh = $(this.page.body).find(".ccr-refresh");
        $refresh.prop("disabled", true).text(__("Loading..."));
        try {
            const response = await frappe.call({
                method: "taj_core.checklist.api.get_checklist_control_room_data",
                args: {
                    search_date: searchDate || undefined,
                    department: department || undefined,
                },
            });
            this.data = response.message || {};
            if (this.data.selected_date) this.dateControl.set_value(this.data.selected_date);
            if (typeof this.data.department === "string") this.departmentControl.set_value(this.data.department);
            this.render();
        } finally {
            $refresh.prop("disabled", false).text(__("Refresh"));
        }
    }

    render() {
        this.render_kpis();
        this.render_department_health();
        this.render_attention();
        this.render_team();
        this.render_buckets();
        this.render_actions();
    }

    render_kpis() {
        const summary = this.data.summary || {};
        ["completion_percent", "not_started", "in_progress", "overdue", "issues", "critical"].forEach((key) => {
            let value = summary[key] || 0;
            if (key === "completion_percent") value = `${value}%`;
            $(this.page.body).find(`[data-kpi="${key}"]`).text(value);
        });

        const actionSummary = this.data.action_summary || {};
        ["open", "overdue", "critical", "pending_verification"].forEach((key) => {
            $(this.page.body).find(`[data-action-kpi="${key}"]`).text(actionSummary[key] || 0);
        });
    }

    render_department_health() {
        const rows = this.data.department_health || [];
        const $target = $(this.page.body).find(".ccr-health-list");
        if (!rows.length) {
            $target.html(this.empty_state(__("No department activity for this view.")));
            return;
        }

        $target.html(rows.map((row) => `
            <div class="ccr-health-row ccr-health-${this.escape(row.health || "good")}">
                <div class="ccr-health-main">
                    <div class="ccr-health-name">${this.escape(row.department)}</div>
                    <div class="ccr-health-meta">${__("Overdue")}: ${row.overdue || 0} · ${__("Issues")}: ${row.issues || 0} · ${__("Critical")}: ${row.critical || 0}</div>
                </div>
                <div class="ccr-health-score">
                    <strong>${this.escape(row.completion_percent)}%</strong>
                    <div class="ccr-progress"><span style="width:${Math.max(0, Math.min(100, Number(row.completion_percent || 0)))}%"></span></div>
                </div>
            </div>
        `).join(""));
    }

    render_attention() {
        const rows = this.data.attention || [];
        const $target = $(this.page.body).find(".ccr-attention-list");
        $(this.page.body).find(".ccr-attention-count").text(rows.length);
        if (!rows.length) {
            $target.html(this.empty_state(__("No critical or overdue items right now.")));
            return;
        }

        $target.html(rows.slice(0, 20).map((row) => `
            <button class="ccr-attention-row ccr-attention-${this.escape(row.attention_level || "warning")}" data-checklist-name="${this.escape(row.name)}" type="button">
                <span class="ccr-attention-dot"></span>
                <span class="ccr-attention-copy">
                    <strong>${this.escape(row.template || row.name)}</strong>
                    <small>${this.escape(row.department || "-")} · ${this.escape(row.attention_reason || "")}</small>
                </span>
                <span class="ccr-attention-side">${row.delay_minutes ? `${this.escape(row.delay_minutes)} ${__("min")}` : this.escape(row.result_status || "")}</span>
            </button>
        `).join(""));
    }

    render_team() {
        const rows = this.data.team_summary || [];
        const $target = $(this.page.body).find(".ccr-team-list");
        if (!rows.length) {
            $target.html(this.empty_state(__("No team workload to display.")));
            return;
        }
        $target.html(rows.slice(0, 16).map((row) => `
            <div class="ccr-team-row">
                <div>
                    <strong>${this.escape(row.user)}</strong>
                    <small>${__("Open")}: ${(row.not_started || 0) + (row.in_progress || 0) + (row.overdue || 0)} · ${__("Completed")}: ${row.completed || 0}</small>
                </div>
                <div class="ccr-team-badges">
                    ${row.in_progress ? `<span class="is-progress">${row.in_progress} ${__("active")}</span>` : ""}
                    ${row.overdue ? `<span class="is-danger">${row.overdue} ${__("overdue")}</span>` : ""}
                    ${row.issues ? `<span class="is-warning">${row.issues} ${__("issues")}</span>` : ""}
                </div>
            </div>
        `).join(""));
    }

    render_buckets() {
        const buckets = this.data.buckets || {};
        const configs = [
            ["not_started", __("Not Started"), "neutral"],
            ["in_progress", __("In Progress"), "progress"],
            ["overdue", __("Overdue"), "danger"],
            ["completed", __("Completed"), "success"],
        ];
        const $target = $(this.page.body).find(".ccr-buckets");
        $target.html(configs.map(([key, label, tone]) => {
            const rows = buckets[key] || [];
            const examples = rows.slice(0, 3).map((row) => `
                <button data-checklist-name="${this.escape(row.name)}" type="button">${this.escape(row.template || row.name)}</button>
            `).join("");
            return `
                <div class="ccr-bucket ccr-bucket-${tone}">
                    <div class="ccr-bucket-head"><strong>${this.escape(label)}</strong><span>${rows.length}</span></div>
                    <div class="ccr-bucket-items">${examples || `<small>${__("None")}</small>`}</div>
                </div>
            `;
        }).join(""));
    }

    render_actions() {
        const rows = this.data.actions || [];
        const $target = $(this.page.body).find(".ccr-action-list");
        $(this.page.body).find(".ccr-open-action-count").text(rows.length);
        if (!rows.length) {
            $target.html(this.empty_state(__("No open Checklist Actions.")));
            return;
        }

        $target.html(rows.slice(0, 30).map((row) => {
            const latest = row.latest_observation === "Pass Observation" ? __("Pass observed; closure still pending") : __("Issue observed");
            const due = row.due_at ? frappe.datetime.str_to_user(row.due_at) : "-";
            const owner = row.responsible_user || row.responsible_department || "-";
            return `
                <button class="ccr-action-row" data-action-name="${this.escape(row.name)}" type="button">
                    <span class="ccr-action-copy">
                        <strong>${this.escape(row.question_text || row.name)}</strong>
                        <small>${this.escape(owner)} · ${this.escape(latest)}</small>
                    </span>
                    <span class="ccr-action-meta">${this.escape(row.status || "")} · ${this.escape(row.severity || "Medium")}</span>
                    <span class="ccr-action-due">${row.is_overdue ? __("Overdue") : this.escape(due)}</span>
                </button>
            `;
        }).join(""));
    }

    empty_state(message) {
        return `<div class="ccr-empty">${this.escape(message)}</div>`;
    }
}
