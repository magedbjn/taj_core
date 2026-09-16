function format_checklist_delay(minutes) {
    const total = Math.max(0, Math.floor(Number(minutes) || 0));
    if (total < 60) return `${total} min`;

    const days = Math.floor(total / 1440);
    const remainder = total % 1440;
    const hours = Math.floor(remainder / 60);
    const mins = remainder % 60;
    const parts = [];

    if (days) parts.push(`${days}d`);
    if (hours) parts.push(`${hours}h`);
    if (mins) parts.push(`${mins}m`);

    return parts.join(" ");
}

function checklist_scope_label(row) {
    if (row && row.plant_floor) return String(row.plant_floor);
    if (row && row.warehouse) return String(row.warehouse);

    const department = String((row && row.department) || "").trim();
    if (!department) return "-";

    return department.replace(/\s+-\s+[^-]+$/, "").trim() || department;
}

frappe.pages["checklist-today"].on_page_load = function (wrapper) {
    new ChecklistTodayPage(wrapper);
};

class ChecklistTodayPage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.data = null;
        this.activeTab = "today";

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Checklist Today"),
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
            <div class="ct-page">
                <section class="ct-hero">
                    <div class="ct-hero-copy">
                        <div class="ct-eyebrow">${__("Daily Operations")}</div>
                        <h2 class="ct-title">${__("Checklist Today")}</h2>
                        <div class="ct-subtitle">${__("What needs attention now, without dashboard clutter.")}</div>
                        <div class="ct-identity mt-2"></div>
                    </div>
                    <div class="ct-hero-actions">
                        <button class="btn btn-default ct-open-classic" type="button">${__("My Checklist Tasks")}</button>
                        <button class="btn btn-default ct-control-room d-none" type="button">${__("Control Room")}</button>
                        <button class="btn btn-primary ct-refresh" type="button">${__("Refresh")}</button>
                    </div>
                </section>

                <section class="ct-kpis" aria-label="${__("Today summary")}">
                    ${this.kpi_card("not_started", __("Not Started"), "○", "neutral")}
                    ${this.kpi_card("in_progress", __("In Progress"), "◔", "progress")}
                    ${this.kpi_card("overdue", __("Overdue"), "!", "danger")}
                    ${this.kpi_card("completed", __("Completed"), "✓", "success")}
                </section>

                <section class="ct-manager-strip d-none">
                    <div class="ct-strip-title">${__("Department Health")}</div>
                    <div class="ct-department-health"></div>
                </section>

                <section class="ct-main-card">
                    <div class="ct-toolbar">
                        <div class="ct-tabs" role="tablist">
                            <button class="ct-tab is-active" data-tab="today" type="button">${__("Today")} <span class="ct-tab-count" data-count="today">0</span></button>
                            <button class="ct-tab ct-team-tab" data-tab="team" type="button">${__("Team")} <span class="ct-tab-count" data-count="team">0</span></button>
                            <button class="ct-tab" data-tab="issues" type="button">${__("Issues")} <span class="ct-tab-count" data-count="issues">0</span></button>
                            <button class="ct-tab" data-tab="actions" type="button">${__("My Actions")} <span class="ct-tab-count" data-count="actions">0</span></button>
                            <button class="ct-tab" data-tab="history" type="button">${__("History")} <span class="ct-tab-count" data-count="history">0</span></button>
                        </div>
                        <div class="ct-history-filter d-none">
                            <div class="ct-date-control"></div>
                            <button class="btn btn-sm btn-default ct-date-search" type="button">${__("Go")}</button>
                        </div>
                    </div>

                    <div class="ct-section-heading">
                        <div>
                            <div class="ct-section-title">${__("Today")}</div>
                            <div class="ct-section-hint"></div>
                        </div>
                        <span class="ct-section-count">0</span>
                    </div>

                    <div class="ct-list"></div>
                </section>
            </div>
        `);

        this.$identity = $(this.page.body).find(".ct-identity");
        this.$list = $(this.page.body).find(".ct-list");
        this.$sectionTitle = $(this.page.body).find(".ct-section-title");
        this.$sectionHint = $(this.page.body).find(".ct-section-hint");
        this.$sectionCount = $(this.page.body).find(".ct-section-count");
        this.$managerStrip = $(this.page.body).find(".ct-manager-strip");
        this.$departmentHealth = $(this.page.body).find(".ct-department-health");

        this.dateControl = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".ct-date-control").get(0),
            df: { fieldtype: "Date", fieldname: "history_date", label: __("Date"), default: frappe.datetime.get_today() },
            render_input: true,
        });
        this.dateControl.set_value(frappe.datetime.get_today());
    }

    kpi_card(key, label, symbol, tone) {
        return `
            <button class="ct-kpi ct-kpi-${tone}" data-kpi="${key}" type="button">
                <span class="ct-kpi-symbol">${symbol}</span>
                <span class="ct-kpi-copy">
                    <span class="ct-kpi-label">${this.escape(label)}</span>
                    <strong class="ct-kpi-value" data-kpi-value="${key}">0</strong>
                </span>
            </button>
        `;
    }

    bind_events() {
        $(this.page.body).on("click", ".ct-refresh", () => this.load_data());
        $(this.page.body).on("click", ".ct-open-classic", () => frappe.set_route("checklist-user"));
        $(this.page.body).on("click", ".ct-control-room", () => frappe.set_route("checklist-control-room"));

        $(this.page.body).on("click", ".ct-tab", (event) => {
            this.activeTab = $(event.currentTarget).data("tab");
            $(this.page.body).find(".ct-tab").removeClass("is-active");
            $(event.currentTarget).addClass("is-active");
            $(this.page.body).find(".ct-history-filter").toggleClass("d-none", this.activeTab !== "history");
            this.render_active_tab();
        });

        $(this.page.body).on("click", ".ct-date-search", () => this.load_data(this.dateControl.get_value()));
        $(this.page.body).on("click", ".ct-task-card", (event) => {
            const name = $(event.currentTarget).data("name");
            this.open_task_direct(name);
        });

        $(this.page.body).on("click", ".ct-open-task", (event) => {
            event.preventDefault();
            event.stopPropagation();
            const name = $(event.currentTarget).closest(".ct-task-card").data("name");
            this.open_task_direct(name);
        });

        $(this.page.body).on("click", ".ct-action-card", (event) => {
            const name = $(event.currentTarget).data("action-name");
            if (name) frappe.set_route("Form", "Checklist Action", name);
        });

        $(this.page.body).on("click", ".ct-kpi", (event) => {
            const bucket = $(event.currentTarget).data("kpi");
            this.activeTab = "today";
            $(this.page.body).find(".ct-tab").removeClass("is-active");
            $(this.page.body).find('.ct-tab[data-tab="today"]').addClass("is-active");
            $(this.page.body).find(".ct-history-filter").addClass("d-none");
            this.render_active_tab(bucket);
        });
    }

    open_task_direct(name) {
        if (!name) return;
        frappe.route_options = {
            checklist_answer: name,
            direct_open: 1,
            origin: "checklist-today",
        };
        frappe.set_route("checklist-user");
    }

    async load_data(searchDate = null) {
        const $refresh = $(this.page.body).find(".ct-refresh");
        $refresh.prop("disabled", true).text(__("Loading..."));
        try {
            const response = await frappe.call({
                method: "taj_core.checklist.api.get_checklist_today_data",
                args: { search_date: searchDate || undefined },
            });
            this.data = response.message || {};
            if (this.data.selected_date) this.dateControl.set_value(this.data.selected_date);
            this.render_header();
            this.render_summary();
            this.render_manager_strip();
            this.render_active_tab();
        } finally {
            $refresh.prop("disabled", false).text(__("Refresh"));
        }
    }

    render_header() {
        const identity = this.data.identity || {};
        const parts = [identity.employee_name, identity.department].filter(Boolean);
        this.$identity.html(parts.map((part) => `<span>${this.escape(part)}</span>`).join("<span class=\"ct-dot\">•</span>"));

        const isManager = !!this.data.is_manager;
        $(this.page.body).find(".ct-control-room").toggleClass("d-none", !isManager);
        $(this.page.body).find(".ct-team-tab").toggleClass("d-none", !isManager);
        if (!isManager && this.activeTab === "team") this.activeTab = "today";
    }

    render_summary() {
        const summary = this.data.summary || {};
        ["not_started", "in_progress", "overdue", "completed"].forEach((key) => {
            $(this.page.body).find(`[data-kpi-value="${key}"]`).text(summary[key] || 0);
        });
        $(this.page.body).find('[data-count="today"]').text((this.data.today || []).length);
        $(this.page.body).find('[data-count="team"]').text((this.data.team || []).length);
        $(this.page.body).find('[data-count="issues"]').text((this.data.issues || []).length);
        $(this.page.body).find('[data-count="actions"]').text((this.data.my_actions || []).length);
        $(this.page.body).find('[data-count="history"]').text((this.data.history || []).length);
    }

    render_manager_strip() {
        if (!this.data.is_manager) {
            this.$managerStrip.addClass("d-none");
            return;
        }
        this.$managerStrip.removeClass("d-none");
        const rows = this.data.department_health || [];
        if (!rows.length) {
            this.$departmentHealth.html(`<div class="ct-empty-inline">${__("No department activity yet.")}</div>`);
            return;
        }
        this.$departmentHealth.html(rows.slice(0, 6).map((row) => `
            <div class="ct-health ct-health-${this.escape(row.health || "good")}">
                <div class="ct-health-top"><strong>${this.escape(row.department)}</strong><span>${this.escape(row.completion_percent)}%</span></div>
                <div class="ct-health-meta">${__("Overdue")}: ${row.overdue || 0} · ${__("Issues")}: ${row.issues || 0}</div>
            </div>
        `).join(""));
    }

    get_tab_rows() {
        if (!this.data) return [];
        if (this.activeTab === "team") return this.data.team || [];
        if (this.activeTab === "issues") return this.data.issues || [];
        if (this.activeTab === "actions") return this.data.my_actions || [];
        if (this.activeTab === "history") return this.data.history || [];
        return this.data.today || [];
    }

    render_active_tab(bucketFilter = null) {
        const labels = {
            today: [__("Today"), this.data && this.data.is_manager ? __("Factory activity that needs action now") : __("Your current checklist work")],
            team: [__("Team"), __("Open work across the team")],
            issues: [__("Issues"), __("Critical, overdue, and open issue items")],
            actions: [__("My Actions"), __("Follow-up work that remains open until resolution is documented")],
            history: [__("History"), __("Checklist activity for the selected date")],
        };
        const [title, hint] = labels[this.activeTab] || labels.today;
        this.$sectionTitle.text(title);
        this.$sectionHint.text(hint);

        let rows = this.get_tab_rows();
        if (bucketFilter) rows = rows.filter((row) => this.operational_bucket(row) === bucketFilter);
        this.$sectionCount.text(rows.length);
        if (this.activeTab === "team" && this.data && this.data.is_manager) {
            this.render_team_view(rows);
        } else if (this.activeTab === "actions") {
            this.render_action_rows(rows);
        } else {
            this.render_rows(rows);
        }
    }

    render_action_rows(rows) {
        if (!rows.length) {
            this.$list.html(`
                <div class="ct-empty">
                    <div class="ct-empty-icon">✓</div>
                    <strong>${__("No open actions assigned to you.")}</strong>
                    <span>${__("A Pass observation does not close an action until the resolution workflow is completed.")}</span>
                </div>
            `);
            return;
        }

        this.$list.html(rows.map((row) => {
            const due = row.due_at ? frappe.datetime.str_to_user(row.due_at) : "-";
            const owner = row.responsible_user || row.responsible_department || "-";
            const latest = row.latest_observation === "Pass Observation" ? __("Pass Observed") : __("Issue Still Open");
            return `
                <article class="ct-action-card" data-action-name="${this.escape(row.name)}" tabindex="0">
                    <div class="ct-task-status-line">
                        <span class="ct-status-pill ct-status-in_progress">${this.escape(row.status || "")}</span>
                        <span class="ct-mini-badge ct-mini-issue">${this.escape(row.severity || "Medium")}</span>
                        ${row.is_overdue ? `<span class="ct-mini-badge ct-mini-critical">${__("Overdue")}</span>` : ""}
                    </div>
                    <div class="ct-task-main">
                        <div>
                            <h3>${this.escape(row.question_text || row.name)}</h3>
                            <div class="ct-task-name">${this.escape(row.name)} · ${this.escape(latest)}</div>
                        </div>
                        <button class="btn btn-sm btn-primary" type="button">${__("Open Action")}</button>
                    </div>
                    <div class="ct-task-meta">
                        <span><small>${__("Responsible")}</small>${this.escape(owner)}</span>
                        <span><small>${__("Due")}</small>${this.escape(due)}</span>
                        <span><small>${__("Occurrences")}</small>${Number(row.occurrence_count || 0)}</span>
                    </div>
                </article>
            `;
        }).join(""));
    }

    render_team_view(rows) {
        const team = this.data.team_summary || [];
        const summaryHtml = team.length ? `
            <div class="ct-team-summary-grid">
                ${team.slice(0, 12).map((item) => `
                    <div class="ct-team-summary-card">
                        <strong>${this.escape(item.user)}</strong>
                        <span>${__("Open")}: ${(item.not_started || 0) + (item.in_progress || 0) + (item.overdue || 0)}</span>
                        <span>${__("Completed")}: ${item.completed || 0}</span>
                        ${item.overdue ? `<em>${item.overdue} ${__("overdue")}</em>` : ""}
                    </div>
                `).join("")}
            </div>
        ` : "";

        const cardsHtml = rows.length
            ? `<div class="ct-team-task-grid">${rows.map((row) => this.task_card(row)).join("")}</div>`
            : `<div class="ct-empty"><div class="ct-empty-icon">✓</div><strong>${__("No open team tasks.")}</strong></div>`;
        this.$list.html(summaryHtml + cardsHtml);
    }

    operational_bucket(row) {
        if (row.docstatus === 1 && row.status === "Completed") return "completed";
        if (row.status === "Expired" || String(row.time_status || "").toLowerCase() === "overdue" || Number(row.delay_minutes || 0) > 0) return "overdue";
        if (row.status === "In Progress" || row.started_at || row.taken_by) return "in_progress";
        return "not_started";
    }

    render_rows(rows) {
        if (!rows.length) {
            this.$list.html(`
                <div class="ct-empty">
                    <div class="ct-empty-icon">✓</div>
                    <strong>${__("Nothing needs your attention here.")}</strong>
                    <span>${__("Use another tab or refresh when new work is scheduled.")}</span>
                </div>
            `);
            return;
        }

        this.$list.html(rows.map((row) => this.task_card(row)).join(""));
    }

    task_card(row) {
        const bucket = this.operational_bucket(row);
        const labelMap = {
            not_started: __("Not Started"),
            in_progress: __("In Progress"),
            overdue: __("Overdue"),
            completed: __("Completed"),
        };
        const owner = row.taken_by || row.assigned_user || "";
        const scope = checklist_scope_label(row);
        const delay = Number(row.delay_minutes || 0);
        const delayLabel = delay > 0 ? format_checklist_delay(delay) : "";
        const ownerMeta = owner
            ? `<span><small>${__("Assigned")}</small>${this.escape(owner)}</span>`
            : "";
        const attentionReason = row.attention_reason ? `<span class="ct-alert-text">${this.escape(row.attention_reason)}</span>` : "";
        const issue = row.has_issue ? `<span class="ct-mini-badge ct-mini-issue">${this.escape(row.result_status || __("Issue"))}</span>` : "";
        const due = row.deadline_at ? frappe.datetime.str_to_user(row.deadline_at) : (row.scheduled_start_at ? frappe.datetime.str_to_user(row.scheduled_start_at) : "-");

        return `
            <article class="ct-task-card ct-task-${bucket}" data-name="${this.escape(row.name)}" tabindex="0">
                <div class="ct-task-status-line">
                    <span class="ct-status-pill ct-status-${bucket}">${this.escape(labelMap[bucket] || row.status || "")}</span>
                    ${issue}
                    ${row.production_started_before_completion ? `<span class="ct-mini-badge ct-mini-critical">${__("Production Started Early")}</span>` : ""}
                </div>
                <div class="ct-task-main">
                    <div>
                        <h3>${this.escape(row.template || row.name)}</h3>
                        <div class="ct-task-name">${this.escape(row.name)}</div>
                    </div>
                    <button class="btn btn-sm btn-primary ct-open-task" type="button">${bucket === "completed" ? __("View") : __("Open")}</button>
                </div>
                <div class="ct-task-meta">
                    <span><small>${__("Scope")}</small>${this.escape(scope)}</span>
                    ${ownerMeta}
                    <span><small>${__("Due")}</small>${this.escape(due)}</span>
                    ${delayLabel ? `<span class="ct-delay"><small>${__("Delay")}</small>${this.escape(delayLabel)}</span>` : ""}
                </div>
                ${attentionReason}
            </article>
        `;
    }
}
