frappe.pages["checklist-user"].on_page_load = function (wrapper) {
    wrapper.checklist_user_page = new ChecklistUserPage(wrapper);
};

frappe.pages["checklist-user"].on_page_show = function (wrapper) {
    if (wrapper.checklist_user_page) {
        return wrapper.checklist_user_page.on_page_show();
    }
};

function setup_checklist_fullwidth(wrapper) {
    $(wrapper).addClass("checklist-page-fullscreen");
    $("body").addClass("checklist-fullwidth-mode");

    if (!window.__checklist_fullwidth_route_guard_added) {
        window.__checklist_fullwidth_route_guard_added = true;

        frappe.router.on("change", () => {
            const route = frappe.get_route ? frappe.get_route() : [];
            const current_page = route && route.length ? route[0] : "";

            if (current_page !== "checklist-user") {
                $("body").removeClass("checklist-fullwidth-mode");
                $("body").removeClass("checklist-drawer-open");
                $("body").removeClass("checklist-direct-open-mode");
            }
        });
    }
}

class ChecklistUserPage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.doc = null;
        this.row_controls = {};
        this.pending_changes = {};
        this.save_timer = null;
        this.is_saving = false;
        this.is_submitting = false;
        this.last_save_promise = Promise.resolve();
        this.is_hydrating_controls = false;
        this.last_save_failed = false;
        this.last_save_error_key = "";

        this.dashboardData = null;
        this.selectedDocname = null;
        this.saveState = "";
        this.activeView = "my-new";
        this.directOpen = false;
        this.directOrigin = null;

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Checklist User"),
            single_column: true
        });

        $(this.page.wrapper).find(".page-head").remove();
        setup_checklist_fullwidth(this.page.wrapper);

        this.render_layout();
        this.bind_events();
    }

    escape(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }

    card_icon_svg(name) {
        const icons = {
            checklist: '<rect x="5" y="4" width="14" height="16" rx="2"></rect><path d="M9 9h6M9 13h6M9 17h4"></path>',
            questions: '<circle cx="12" cy="12" r="8"></circle><path d="M9.8 9.5a2.4 2.4 0 0 1 4.6 1c0 1.8-2.4 2-2.4 3.6M12 17h.01"></path>',
            department: '<path d="M4 20h16M6 20V8h12v12M9 11h2M13 11h2M9 15h2M13 15h2M9 8V5h6v3"></path>',
            user: '<circle cx="12" cy="8" r="3"></circle><path d="M5.5 20c.7-4 3-6 6.5-6s5.8 2 6.5 6"></path>',
            result: '<path d="M5 12l4 4L19 6"></path>',
            plant_floor: '<path d="M3 20h18M5 20V10l5 3V9l5 3V6l4 3v11"></path>',
            warehouse: '<path d="M3 10l9-6 9 6v10H3zM7 20v-6h10v6"></path>',
            calendar: '<rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M8 3v4M16 3v4M4 10h16"></path>'
        };
        const body = icons[name] || icons.checklist;
        return `<svg class="checklist-inline-icon" viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
    }

    card_meta_item(iconName, label, value) {
        return `
            <div class="checklist-list-meta-item">
                <span class="checklist-meta-icon">${this.card_icon_svg(iconName)}</span>
                <span class="checklist-meta-text"><strong>${this.escape(label)}:</strong> ${this.escape(value || "-")}</span>
            </div>
        `;
    }

    render_layout() {
        $(this.page.body).html(`
            <div class="checklist-entry-page container-fluid px-2 px-md-3">
                <div class="card shadow-sm border-0 mb-3">
                    <div class="card-body py-3">
                        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end">
                            <div class="mb-3 mb-lg-0">
                                <div class="checklist-page-title">${__("My Checklist Tasks")}</div>
                                <div class="checklist-page-subtitle">${__("Simple and stable screen for checklist tasks")}</div>
                            </div>

                            <div class="d-flex flex-column flex-sm-row align-items-stretch align-items-sm-end w-100 w-lg-auto">
                                <div class="history-date-control mb-2 mb-sm-0 mr-sm-2"></div>
                                <button class="btn btn-primary btn-search-history">${__("Search")}</button>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="d-flex flex-wrap mb-3 checklist-view-switcher">
                    <button class="view-switch-btn is-active" data-view="my-new" type="button">
                        <span class="view-switch-icon is-blue">
                            <svg class="view-switch-svg" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M12 5V19"></path>
                                <path d="M5 12H19"></path>
                            </svg>
                        </span>
                        <span class="view-switch-label">${__("My New")}</span>
                        <span class="view-switch-count" data-count-for="my-new">0</span>
                    </button>

                    <button class="view-switch-btn" data-view="my-open" type="button">
                        <span class="view-switch-icon is-orange">
                            <svg class="view-switch-svg" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M12 6V12L16 14"></path>
                                <circle cx="12" cy="12" r="7.5"></circle>
                            </svg>
                        </span>
                        <span class="view-switch-label">${__("My Open")}</span>
                        <span class="view-switch-count" data-count-for="my-open">0</span>
                    </button>

                    <button class="view-switch-btn" data-view="team" type="button">
                        <span class="view-switch-icon is-rose">
                            <svg class="view-switch-svg" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M7 12H17"></path>
                                <path d="M12 7V17"></path>
                                <circle cx="12" cy="12" r="8"></circle>
                            </svg>
                        </span>
                        <span class="view-switch-label">${__("Team Open")}</span>
                        <span class="view-switch-count" data-count-for="team">0</span>
                    </button>

                    <button class="view-switch-btn" data-view="search" type="button">
                        <span class="view-switch-icon is-green">
                            <svg class="view-switch-svg" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                                <circle cx="11" cy="11" r="6.5"></circle>
                                <path d="M20 20L16.65 16.65"></path>
                            </svg>
                        </span>
                        <span class="view-switch-label">${__("Search")}</span>
                        <span class="view-switch-count" data-count-for="search">0</span>
                    </button>
                </div>

                <div class="card shadow-sm border-0 checklist-panel">
                    <div class="card-body">
                        <div class="d-flex align-items-center justify-content-between flex-wrap mb-3">
                            <div class="panel-title mb-0">
                                <span class="active-view-title">${__("My New Tasks")}</span>
                            </div>
                            <span class="panel-count active-view-count">0</span>
                        </div>

                        <div class="active-cards-list"></div>
                    </div>
                </div>

                <div class="checklist-drawer-backdrop"></div>

                <aside class="checklist-drawer">
                    <div class="checklist-drawer-header">
                        <div>
                            <div class="checklist-drawer-title">${__("Checklist Details")}</div>
                            <div class="checklist-drawer-subtitle">${__("Questions and answers")}</div>
                        </div>
                        <button class="checklist-drawer-close" type="button" aria-label="${__("Close")}">×</button>
                    </div>

                    <div class="selected-doc-wrapper">
                        <div class="selected-doc-meta"></div>
                        <div class="selected-doc-progress"></div>
                        <div class="selected-doc-body"></div>
                    </div>
                    <div class="selected-doc-actions"></div>
                </aside>
            </div>
        `);

        this.$cardsList = $(this.page.body).find(".active-cards-list");
        this.$viewButtons = $(this.page.body).find(".view-switch-btn");
        this.$activeViewTitle = $(this.page.body).find(".active-view-title");
        this.$activeViewCount = $(this.page.body).find(".active-view-count");

        this.$meta = $(this.page.body).find(".selected-doc-meta");
        this.$progress = $(this.page.body).find(".selected-doc-progress");
        this.$body = $(this.page.body).find(".selected-doc-body");
        this.$actions = $(this.page.body).find(".selected-doc-actions");

        this.$drawer = $(this.page.body).find(".checklist-drawer");
        this.$drawerBackdrop = $(this.page.body).find(".checklist-drawer-backdrop");
        this.$drawerClose = $(this.page.body).find(".checklist-drawer-close");
        this.$drawerTitle = $(this.page.body).find(".checklist-drawer-title");
        this.$drawerSubtitle = $(this.page.body).find(".checklist-drawer-subtitle");

        this.history_date_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".history-date-control").get(0),
            df: {
                label: __("Search Date"),
                fieldname: "search_date",
                fieldtype: "Date",
                default: frappe.datetime.get_today()
            },
            render_input: true
        });

        this.history_date_control.refresh();
        this.history_date_control.set_value(frappe.datetime.get_today());
    }

    bind_events() {
        $(this.page.body).find(".btn-search-history").on("click", async () => {
            this.activeView = "search";
            await this.load_dashboard();
        });

        this.$viewButtons.on("click", (e) => {
            const view = $(e.currentTarget).attr("data-view");
            this.set_active_view(view);
        });

        this.$drawerClose.on("click", () => this.close_drawer());
        this.$drawerBackdrop.on("click", () => this.close_drawer());

        $(document)
            .off("keydown.checklist_user_drawer")
            .on("keydown.checklist_user_drawer", (e) => {
                if (e.key === "Escape") {
                    this.close_drawer();
                }
            });
    }

    open_drawer() {
        this.$drawer.addClass("is-open");
        this.$drawerBackdrop.addClass("is-open");
        $("body").addClass("checklist-drawer-open");
    }

    close_drawer() {
        if (this.directOpen && this.directOrigin === "checklist-today") {
            this.directOpen = false;
            this.directOrigin = null;
            $("body").removeClass("checklist-direct-open-mode");
            frappe.set_route("checklist-today");
            return;
        }

        this.$drawer.removeClass("is-open");
        this.$drawerBackdrop.removeClass("is-open");
        $("body").removeClass("checklist-drawer-open");
        $("body").removeClass("checklist-direct-open-mode");
    }

    set_save_state(stateText = "") {
        this.saveState = stateText;
        this.render_progress();
    }

    async on_page_show() {
        const opts = { ...(frappe.route_options || {}) };
        frappe.route_options = null;

        if (opts.checklist_answer) {
            this.directOpen = !!opts.direct_open;
            this.directOrigin = opts.origin || null;
            $("body").toggleClass("checklist-direct-open-mode", this.directOpen);
            await this.load_doc(opts.checklist_answer);
            return;
        }

        this.directOpen = false;
        this.directOrigin = null;
        this.$drawer.removeClass("is-open");
        this.$drawerBackdrop.removeClass("is-open");
        $("body").removeClass("checklist-drawer-open checklist-direct-open-mode");
        await this.load_dashboard();
    }

    async load_dashboard() {
        try {
            const search_date = this.history_date_control.get_value();

            const r = await frappe.call({
                method: "taj_core.checklist.api.get_user_dashboard_data",
                args: { search_date }
            });

            this.dashboardData = r.message || {};
            this.refresh_view_counts();
            this.set_active_view(this.activeView);
        } catch (e) {
            frappe.msgprint({
                title: __("Error"),
                indicator: "red",
                message: __("Failed to load dashboard data.")
            });
            console.error(e);
        }
    }

    refresh_view_counts() {
        const counts = {
            "my-new": (this.dashboardData?.my_new || []).length,
            "my-open": (this.dashboardData?.my_open || []).length,
            "team": (this.dashboardData?.team_open || []).length,
            "search": (this.dashboardData?.history_results || []).length
        };

        Object.keys(counts).forEach((key) => {
            $(this.page.body)
                .find(`.view-switch-count[data-count-for="${key}"]`)
                .text(counts[key]);
        });
    }

    get_view_docs(viewName) {
        if (viewName === "my-new") return this.dashboardData?.my_new || [];
        if (viewName === "my-open") return this.dashboardData?.my_open || [];
        if (viewName === "team") return this.dashboardData?.team_open || [];
        if (viewName === "search") return this.dashboardData?.history_results || [];
        return [];
    }

    get_view_title(viewName) {
        if (viewName === "my-new") return __("My New Tasks (Today)");
        if (viewName === "my-open") return __("My Open Tasks");
        if (viewName === "team") return __("Team Open Tasks");
        if (viewName === "search") return __("Search Results");
        return __("Checklist Tasks");
    }

    get_empty_text(viewName) {
        if (viewName === "my-new") return __("No new tasks for today.");
        if (viewName === "my-open") return __("No open tasks.");
        if (viewName === "team") return __("No team open tasks.");
        if (viewName === "search") return __("No results for selected date.");
        return __("No data found.");
    }

    set_active_view(viewName) {
        this.activeView = viewName;

        this.$viewButtons.removeClass("is-active");
        this.$viewButtons.filter(`[data-view="${viewName}"]`).addClass("is-active");

        const docs = this.get_view_docs(viewName);
        this.$activeViewTitle.text(this.get_view_title(viewName));
        this.$activeViewCount.text(docs.length);

        this.render_list(this.$cardsList, docs, this.get_empty_text(viewName));
    }

    get_doc_question_count(doc) {
        if (!doc) return 0;

        if (Array.isArray(doc.questions)) return doc.questions.length;
        if (doc.questions_count != null) return doc.questions_count;
        if (doc.question_count != null) return doc.question_count;
        if (doc.total_questions != null) return doc.total_questions;
        if (doc.total_question != null) return doc.total_question;
        if (doc.questions_total != null) return doc.questions_total;

        if (this.doc && this.doc.name === doc.name && Array.isArray(this.doc.questions)) {
            return this.doc.questions.length;
        }

        return 0;
    }

    get_status_slug(status) {
        const value = String(status || "").trim().toLowerCase();

        if (value === "completed") return "completed";
        if (value === "open") return "open";
        if (value === "in progress") return "in-progress";
        if (["auto closed", "auto closed - incomplete", "missed"].includes(value)) return "auto-closed";
        if (value === "expired") return "expired";
        if (value === "on hold") return "on-hold";
        return "default";
    }

    render_list($target, docs, emptyText) {
        $target.empty();

        if (!docs.length) {
            $target.html(`<div class="empty-state">${emptyText}</div>`);
            return;
        }

        docs.forEach(doc => {
            const activeClass = this.selectedDocname === doc.name ? "is-active" : "";
            const questionCount = this.get_doc_question_count(doc);
            const statusText = doc.status || __("Open");
            const statusSlug = this.get_status_slug(statusText);

            const questionBadge = `
                <span class="question-count-badge">
                    ${this.card_icon_svg("questions")}
                    <span>${__("Questions")}: ${this.escape(questionCount)}</span>
                </span>
            `;

            const statusBadge = `
                <span class="status-pill status-${statusSlug}">
                    <span class="status-pill-dot" aria-hidden="true"></span>
                    ${this.escape(statusText)}
                </span>
            `;

            const previousOpenBadge = doc.is_previous_cycle_open
                ? `<span class="status-pill status-expired">${__("Previous Open")}</span>`
                : "";

            const $item = $(`
                <div class="checklist-list-item status-card-${statusSlug} ${activeClass}">
                    <div class="checklist-list-top">
                        <div class="checklist-list-head">
                            <div class="checklist-list-template-row">
                                <span class="checklist-card-title-icon">${this.card_icon_svg("checklist")}</span>
                                <div class="checklist-list-template">${this.escape(doc.template || "-")}</div>
                            </div>
                            <div class="checklist-list-docname">${this.escape(doc.name || "-")}</div>
                        </div>

                        <div class="checklist-list-side">
                            ${questionBadge}
                            ${statusBadge}
                            ${previousOpenBadge}
                        </div>
                    </div>

                    <div class="checklist-list-meta">
                        ${this.card_meta_item("department", __("Department"), doc.department || "-")}
                        ${doc.plant_floor ? this.card_meta_item("plant_floor", __("Plant Floor"), doc.plant_floor) : ""}
                        ${doc.warehouse ? this.card_meta_item("warehouse", __("Warehouse"), doc.warehouse) : ""}
                        ${this.card_meta_item("user", __("Assigned User"), doc.assigned_user || "-")}
                        ${this.card_meta_item("result", __("Result"), doc.result_status || "Normal")}
                        ${doc.is_previous_cycle_open ? this.card_meta_item("calendar", __("Open From"), doc.open_from_date || doc.posting_date || "-") : ""}
                    </div>
                </div>
            `);

            $item.on("click", () => this.load_doc(doc.name));
            $target.append($item);
        });
    }

    async load_doc(docname) {
        try {
            if (this.save_timer) {
                clearTimeout(this.save_timer);
                this.save_timer = null;
            }
            this.pending_changes = {};
            this.last_save_failed = false;
            this.last_save_error_key = "";
            this.set_save_state("");

            const r = await frappe.call({
                method: "taj_core.checklist.api.get_checklist_answer",
                args: { docname }
            });

            this.doc = r.message;
            this.selectedDocname = docname;

            this.render_doc();
            this.set_active_view(this.activeView);
            this.open_drawer();
        } catch (e) {
            frappe.msgprint({
                title: __("Error"),
                indicator: "red",
                message: __("Failed to load checklist document.")
            });
            console.error(e);
        }
    }

    render_doc() {
        if (!this.doc) return;

        this.page.set_indicator(this.doc.status || "Draft", this.get_indicator_color(this.doc.status));
        this.set_save_state("");

        this.$drawerTitle.text(this.doc.template || __("Checklist Details"));
        this.$drawerSubtitle.text(this.doc.name || __("Questions and answers"));

        const statusSlug = this.get_status_slug(this.doc.status);
        const statusBadge = `
            <span class="status-pill status-${statusSlug}">
                ${this.escape(this.doc.status || __("Open"))}
            </span>
        `;

        this.$meta.html(`
            <div style="margin-bottom:12px;">${statusBadge}</div>

            <div class="meta-collapse-card">
                <button class="meta-collapse-toggle" type="button" aria-expanded="false">
                    <span>${__("Checklist Info")}</span>
                    <span class="meta-collapse-icon">+</span>
                </button>

                <div class="selected-doc-meta-panel">
                    <div class="selected-doc-meta-grid">
                        <div class="meta-line"><strong>${__("Template")}:</strong> ${this.escape(this.doc.template || "-")}</div>
                        <div class="meta-line"><strong>${__("Document")}:</strong> ${this.escape(this.doc.name || "-")}</div>
                        <div class="meta-line"><strong>${__("Posting Date")}:</strong> ${this.escape(this.doc.posting_date || "-")}</div>
                        <div class="meta-line"><strong>${__("Department")}:</strong> ${this.escape(this.doc.department || "-")}</div>
                        ${this.doc.plant_floor ? `<div class="meta-line"><strong>${__("Plant Floor")}:</strong> ${this.escape(this.doc.plant_floor)}</div>` : ""}
                        ${this.doc.warehouse ? `<div class="meta-line"><strong>${__("Warehouse")}:</strong> ${this.escape(this.doc.warehouse)}</div>` : ""}
                        <div class="meta-line"><strong>${__("Assigned User")}:</strong> ${this.escape(this.doc.assigned_user || "-")}</div>
                        <div class="meta-line"><strong>${__("Result")}:</strong> ${this.escape(this.doc.result_status || "Normal")}</div>
                        <div class="meta-line"><strong>${__("Questions")}:</strong> ${this.escape((this.doc.questions || []).length)}</div>

                        <div class="meta-line"><strong>${__("Asset")}:</strong> ${this.escape(this.doc.asset || "-")}</div>
                        <div class="meta-line"><strong>${__("Scheduled Start At")}:</strong> ${this.escape(this.doc.scheduled_start_at || "-")}</div>
                        <div class="meta-line"><strong>${__("Deadline At")}:</strong> ${this.escape(this.doc.deadline_at || "-")}</div>
                        <div class="meta-line"><strong>${__("Started At")}:</strong> ${this.escape(this.doc.started_at || "-")}</div>
                        <div class="meta-line"><strong>${__("Completed At")}:</strong> ${this.escape(this.doc.completed_at || "-")}</div>
                        <div class="meta-line"><strong>${__("Time Status")}:</strong> ${this.escape(this.doc.time_status || "-")}</div>
                        <div class="meta-line"><strong>${__("Delay Minutes")}:</strong> ${this.escape(this.doc.delay_minutes != null ? this.doc.delay_minutes : 0)}</div>
                    </div>
                </div>
            </div>
        `);
        
        const $toggle = this.$meta.find(".meta-collapse-toggle");
        const $panel = this.$meta.find(".selected-doc-meta-panel");
        const $icon = this.$meta.find(".meta-collapse-icon");

        $panel.hide();

        $toggle.off("click.checklist_user_meta").on("click.checklist_user_meta", function () {
            const isOpen = $(this).attr("aria-expanded") === "true";

            $panel.stop(true, true).slideToggle(180);
            $(this).attr("aria-expanded", String(!isOpen));
            $(this).toggleClass("is-open", !isOpen);
            $icon.text(isOpen ? "+" : "−");
        });

        this.render_progress();
        this.render_questions();
        this.render_worker_section();
        this.render_actions();
    }

    render_progress() {
        if (!this.$progress) return;

        const questions = this.doc?.questions || [];
        const answered = questions.filter(q => String(q.answer || "").trim()).length;
        const saveStateHtml = this.saveState
            ? `<div class="save-state">${this.escape(this.saveState)}</div>`
            : "";

        this.$progress.html(`
            <div class="progress-wrap">
                <div class="progress-line">
                    <strong>${__("Progress")}:</strong>
                    ${answered} / ${questions.length} ${__("answered")}
                </div>
                ${saveStateHtml}
            </div>
        `);
    }

    normalize_select_options(raw) {
        const lines = this.split_lines(raw);
        return "\n" + lines.join("\n");
    }

    split_lines(raw) {
        return String(raw || "")
            .split(/\r?\n/)
            .map(v => v.trim())
            .filter(Boolean);
    }

    is_binary_type(type) {
        return ["Yes/No", "Yes/No/NA", "Pass/Fail/NA"].includes(type);
    }

    can_quick_pass_row(row) {
        if (Number(row.quick_pass_allowed || 0) !== 1) return false;
        if (row.type === "Pass/Fail/NA") return true;
        if (["Yes/No", "Yes/No/NA"].includes(row.type)) {
            return Number(row.issue_if_no || 0) === 1;
        }
        return false;
    }

    get_choice_options(row) {
        if (row.type === "Pass/Fail/NA") {
            return ["Pass", "Fail", "N/A"];
        }
        if (row.type === "Yes/No/NA") {
            return ["Yes", "No", "N/A"];
        }
        if (row.type === "Yes/No") {
            return ["Yes", "No"];
        }
        return [];
    }

    is_failure_answer(row, answer) {
        const value = String(answer == null ? "" : answer).trim();
        if (!value || value === "N/A") return false;

        if (row.type === "Pass/Fail/NA") {
            return value === "Fail";
        }

        if (["Yes/No", "Yes/No/NA"].includes(row.type)) {
            return Boolean(Number(row.issue_if_no || 0)) && value === "No";
        }

        if (["Select", "Single Select"].includes(row.type)) {
            return this.split_lines(row.issue_values).includes(value);
        }

        if (row.type === "Multi Select") {
            const selected = new Set(this.split_lines(value));
            return this.split_lines(row.issue_values).some(v => selected.has(v));
        }

        if (row.type === "Int" || row.type === "Float") {
            const numeric = Number(value);
            if (!Number.isFinite(numeric)) return false;
            const minValue = row.type === "Int" ? row.answer_min_int : row.answer_min_float;
            const maxValue = row.type === "Int" ? row.answer_max_int : row.answer_max_float;
            if (minValue !== null && minValue !== undefined && minValue !== "" && numeric < Number(minValue)) return true;
            if (maxValue !== null && maxValue !== undefined && maxValue !== "" && numeric > Number(maxValue)) return true;
        }

        return false;
    }

    render_question_group_heading(row, previousGroup) {
        const group = String(row?.question_group || "").trim();
        if (!group || group === previousGroup) return previousGroup;

        this.$body.append(`
            <div class="checklist-question-group-heading">
                <span>${this.escape(group)}</span>
            </div>
        `);
        return group;
    }

    render_questions() {
        const questions = this.doc?.questions || [];
        this.$body.empty();
        this.row_controls = {};

        if (!questions.length) {
            this.$body.html(`<div class="empty-state">${__("No questions found.")}</div>`);
            return;
        }

        let currentGroup = "";
        if (!this.doc.is_editable) {
            questions.forEach((row, index) => {
                currentGroup = this.render_question_group_heading(row, currentGroup);
                this.render_readonly_question(row, index);
            });
            return;
        }

        this.is_hydrating_controls = true;
        questions.forEach((row, index) => {
            currentGroup = this.render_question_group_heading(row, currentGroup);
            this.render_editable_question(row, index);
        });
        this.is_hydrating_controls = false;
    }

    render_readonly_question(row, index) {
        const issueClass = row.has_issue ? "has-issue" : "";
        const issueLine = row.has_issue
            ? `<div class="question-status-row"><span class="status-pill status-expired">${__("Issue Answer")}</span>${row.issue_severity ? `<span class="question-rule-badge">${this.escape(row.issue_severity)}</span>` : ""}</div>`
            : "";
        const failureReason = row.failure_reason
            ? `<div class="readonly-answer-value"><strong>${__("Reason")}:</strong> ${this.escape(row.failure_reason)}</div>`
            : "";
        const affectedItems = row.affected_items
            ? `<div class="readonly-answer-value"><strong>${__("Affected Item")}:</strong> ${this.escape(this.split_lines(row.affected_items).join(", "))}</div>`
            : "";
        const issueType = row.issue_type
            ? `<div class="readonly-answer-value"><strong>${__("Issue Type")}:</strong> ${this.escape(row.issue_type)}</div>`
            : "";
        const userNote = row.user_note
            ? `<div class="readonly-answer-value"><strong>${__("Note")}:</strong> ${this.escape(row.user_note)}</div>`
            : "";
        const evidence = row.evidence_photo
            ? `<div class="readonly-answer-value"><strong>${__("Photo")}:</strong> <a href="${this.escape(row.evidence_photo)}" target="_blank" rel="noopener">${__("Open photo")}</a></div>`
            : "";
        const followUp = row.has_issue && row.require_follow_up
            ? `<div class="readonly-answer-value"><strong>${__("Follow-up")}:</strong> ${this.escape(row.responsible_department || row.responsible_user || __("Required"))}</div>`
            : "";
        const openActionWarning = row.open_action
            ? `<div class="open-action-warning"><strong>${Number(row.open_action_count || 0) > 1 ? `${__("Open Actions")}: ${this.escape(row.open_action_count)}` : `${__("Open Action")}: ${this.escape(row.open_action)}`}</strong><span>${__("This action is still open. A Pass in this checklist does not close it automatically.")}</span></div>`
            : "";

        this.$body.append(`
            <div class="checklist-answer-readonly ${issueClass}">
                ${issueLine}
                <div class="checklist-question-title">
                    <span class="question-number">${index + 1}</span>
                    <span>${this.escape(row.question_text || row.question || "")}</span>
                </div>
                                <div class="readonly-answer-value">
                    <strong>${__("Answer")}:</strong> ${this.escape(row.answer || "-")}
                </div>
                ${row.issue_note ? `<div class="readonly-answer-value"><strong>${__("System Result")}:</strong> ${this.escape(row.issue_note)}</div>` : ""}
                ${failureReason}${affectedItems}${issueType}${userNote}${evidence}${followUp}${openActionWarning}
            </div>
        `);
    }

    render_editable_question(row, index) {
        const requiredBadge = Number(row.is_required || 0)
            ? `<span class="question-rule-badge is-required">${__("Required")}</span>`
            : `<span class="question-rule-badge">${__("Optional")}</span>`;
        const qualityBadge = Number(row.quality_impact || 0)
            ? `<span class="question-rule-badge is-quality">${__("Quality")}</span>`
            : "";
        const openActionWarning = row.open_action
            ? `<div class="open-action-warning"><strong>${Number(row.open_action_count || 0) > 1 ? `${__("Open Actions")}: ${this.escape(row.open_action_count)}` : `${__("Open Action")}: ${this.escape(row.open_action)} (${this.escape(row.open_action_status || "")})`}</strong><span>${__("This action is unresolved. A Pass now records the current condition but does not close the previous action.")}</span></div>`
            : "";

        const $card = $(`
            <div class="checklist-question-card" data-row-name="${this.escape(row.row_name)}">
                <div class="checklist-question-title">
                    <span class="question-number">${index + 1}</span>
                    <span class="question-title-text">${this.escape(row.question_text || row.question || "")}</span>
                </div>
                <div class="question-badges">${requiredBadge}${qualityBadge}</div>
                ${openActionWarning}
                <div class="question-control"></div>
                <div class="failure-detail-panel-container"></div>
            </div>
        `);
        this.$body.append($card);

        if (this.is_binary_type(row.type)) {
            this.render_choice_control(row, $card);
        } else if (row.type === "Multi Select") {
            this.render_multi_select_control(row, $card);
        } else {
            this.render_generic_control(row, $card);
        }

        this.refresh_failure_panel(row, $card);
    }

    render_choice_control(row, $card) {
        const options = this.get_choice_options(row);
        const $wrap = $('<div class="answer-choice-grid"></div>');

        options.forEach(option => {
            const active = String(row.answer || "") === option ? "is-selected" : "";
            const semantic = option === "Pass" || option === "Yes"
                ? "is-positive"
                : (option === "Fail" || option === "No" ? "is-negative" : "is-na");
            const $button = $(`
                <button type="button" class="answer-choice-btn ${semantic} ${active}" data-value="${this.escape(option)}">
                    ${this.escape(option)}
                </button>
            `);
            $button.on("click", () => {
                $wrap.find(".answer-choice-btn").removeClass("is-selected");
                $button.addClass("is-selected");
                this.set_row_answer(row, option, $card);
            });
            $wrap.append($button);
        });

        $card.find(".question-control").append($wrap);
    }

    render_multi_select_control(row, $card) {
        const selected = new Set(this.split_lines(row.answer));
        const $wrap = $('<div class="answer-choice-grid is-multi"></div>');

        this.split_lines(row.answer_options).forEach(option => {
            const active = selected.has(option) ? "is-selected" : "";
            const $button = $(`
                <button type="button" class="answer-choice-btn multi-choice-btn ${active}" data-value="${this.escape(option)}">
                    ${this.escape(option)}
                </button>
            `);
            $button.on("click", () => {
                if (selected.has(option)) {
                    selected.delete(option);
                    $button.removeClass("is-selected");
                } else {
                    selected.add(option);
                    $button.addClass("is-selected");
                }
                this.set_row_answer(row, Array.from(selected).join("\n"), $card);
            });
            $wrap.append($button);
        });

        $card.find(".question-control").append($wrap);
    }

    render_generic_control(row, $card) {
        const control = frappe.ui.form.make_control({
            parent: $card.find(".question-control").get(0),
            df: this.get_df_for_row(row, $card),
            render_input: true
        });

        control.refresh();
        control.set_value(row.answer || "");
        this.row_controls[row.row_name] = control;
    }

    get_df_for_row(row, $card) {
        const base_df = {
            label: "",
            fieldname: `answer_${row.row_name}`,
            reqd: 0,
            change: () => {
                if (this.is_hydrating_controls) return;
                const control = this.row_controls[row.row_name];
                const value = control ? control.get_value() : "";
                this.set_row_answer(row, value, $card);
            }
        };

        if (row.type === "Int") return { ...base_df, fieldtype: "Int" };
        if (row.type === "Float") return { ...base_df, fieldtype: "Float" };
        if (["Select", "Single Select"].includes(row.type)) {
            return { ...base_df, fieldtype: "Select", options: this.normalize_select_options(row.answer_options) };
        }
        if (row.type === "Text") return { ...base_df, fieldtype: "Small Text" };
        if (row.type === "Photo") return { ...base_df, fieldtype: "Attach Image" };
        return { ...base_df, fieldtype: "Data" };
    }

    set_row_answer(row, value, $card) {
        const normalized = value == null ? "" : String(value);
        row.answer = normalized;
        this.schedule_save(row.row_name, { answer: normalized });
        this.refresh_failure_panel(row, $card);
        this.render_progress();
    }

    refresh_failure_panel(row, $card) {
        const $container = $card.find(".failure-detail-panel-container");
        $container.empty();
        $card.toggleClass("has-issue-live", this.is_failure_answer(row, row.answer));

        if (!this.is_failure_answer(row, row.answer)) {
            row.failure_reason = "";
            row.affected_items = "";
            row.issue_type = "";
            row.user_note = "";
            row.evidence_photo = "";
            row.photo_unavailable_reason = "";
            return;
        }

        const routingLabel = row.require_follow_up
            ? (row.responsible_department || row.responsible_user || __("Follow-up required"))
            : "";
        const $panel = $(`
            <div class="failure-detail-panel">
                <div class="failure-panel-head">
                    <strong>${__("Issue details")}</strong>
                    <div class="failure-panel-badges">
                        <span class="question-rule-badge is-severity">${this.escape(row.issue_severity || "Medium")}</span>
                        ${routingLabel ? `<span class="question-rule-badge">${this.escape(routingLabel)}</span>` : ""}
                    </div>
                </div>
                <div class="failure-reason"></div>
                <div class="failure-affected-items"></div>
                <div class="failure-issue-type"></div>
                <div class="failure-note"></div>
                <div class="failure-photo"></div>
            </div>
        `);
        $container.append($panel);

        this.render_failure_reason(row, $panel);
        this.render_failure_affected_items(row, $panel);
        this.render_failure_issue_type(row, $panel);
        this.render_failure_note(row, $panel);
        this.render_failure_photo(row, $panel);
    }

    render_failure_reason(row, $panel) {
        const options = this.split_lines(row.failure_reason_options);
        const needsReason = Number(row.require_failure_reason || 0) === 1;
        if (!needsReason && !options.length) return;

        const $host = $panel.find(".failure-reason");
        $host.append(`<div class="failure-field-label">${__("Reason")}${needsReason ? " *" : ""}</div>`);

        if (options.length) {
            const $choices = $('<div class="failure-reason-choices"></div>');
            options.forEach(option => {
                const active = row.failure_reason === option ? "is-selected" : "";
                const $button = $(`<button type="button" class="failure-reason-btn ${active}">${this.escape(option)}</button>`);
                $button.on("click", () => {
                    row.failure_reason = option;
                    $choices.find(".failure-reason-btn").removeClass("is-selected");
                    $button.addClass("is-selected");
                    this.schedule_save(row.row_name, { failure_reason: option });
                });
                $choices.append($button);
            });
            $host.append($choices);
            return;
        }

        const controlKey = `${row.row_name}:failure_reason`;
        const control = frappe.ui.form.make_control({
            parent: $host.get(0),
            df: {
                label: "",
                fieldname: `failure_reason_${row.row_name}`,
                fieldtype: "Data",
                reqd: 0,
                change: () => {
                    if (this.is_hydrating_controls) return;
                    row.failure_reason = control.get_value() || "";
                    this.schedule_save(row.row_name, { failure_reason: row.failure_reason });
                }
            },
            render_input: true
        });
        control.refresh();
        control.set_value(row.failure_reason || "");
        this.row_controls[controlKey] = control;
    }

    render_failure_affected_items(row, $panel) {
        const options = this.split_lines(row.affected_item_options);
        const required = Number(row.require_affected_item || 0) === 1;
        if (!required && !options.length) return;

        const $host = $panel.find(".failure-affected-items");
        $host.append(`<div class="failure-field-label">${__("Affected Item")}${required ? " *" : ""}</div>`);
        $host.append(`<div class="failure-field-help">${__("Select all items affected by this failure.")}</div>`);

        if (options.length) {
            const selected = new Set(this.split_lines(row.affected_items));
            const $choices = $('<div class="failure-reason-choices"></div>');
            options.forEach(option => {
                const active = selected.has(option) ? "is-selected" : "";
                const $button = $(`<button type="button" class="failure-reason-btn ${active}">${this.escape(option)}</button>`);
                $button.on("click", () => {
                    if (selected.has(option)) {
                        selected.delete(option);
                        $button.removeClass("is-selected");
                    } else {
                        selected.add(option);
                        $button.addClass("is-selected");
                    }
                    row.affected_items = options.filter(value => selected.has(value)).join("\n");
                    this.schedule_save(row.row_name, { affected_items: row.affected_items });
                });
                $choices.append($button);
            });
            $host.append($choices);
            return;
        }

        const controlKey = `${row.row_name}:affected_items`;
        const control = frappe.ui.form.make_control({
            parent: $host.get(0),
            df: {
                label: "",
                fieldname: `affected_items_${row.row_name}`,
                fieldtype: "Small Text",
                reqd: 0,
                change: () => {
                    if (this.is_hydrating_controls) return;
                    row.affected_items = control.get_value() || "";
                    this.schedule_save(row.row_name, { affected_items: row.affected_items });
                }
            },
            render_input: true
        });
        control.refresh();
        control.set_value(row.affected_items || "");
        this.row_controls[controlKey] = control;
    }

    render_failure_issue_type(row, $panel) {
        const options = this.split_lines(row.issue_type_options);
        const required = Number(row.require_issue_type || 0) === 1;
        if (!required && !options.length) return;

        const $host = $panel.find(".failure-issue-type");
        $host.append(`<div class="failure-field-label">${__("Issue Type")}${required ? " *" : ""}</div>`);

        if (options.length) {
            const $choices = $('<div class="failure-reason-choices"></div>');
            options.forEach(option => {
                const active = row.issue_type === option ? "is-selected" : "";
                const $button = $(`<button type="button" class="failure-reason-btn ${active}">${this.escape(option)}</button>`);
                $button.on("click", () => {
                    row.issue_type = option;
                    $choices.find(".failure-reason-btn").removeClass("is-selected");
                    $button.addClass("is-selected");
                    this.schedule_save(row.row_name, { issue_type: option });
                });
                $choices.append($button);
            });
            $host.append($choices);
            return;
        }

        const controlKey = `${row.row_name}:issue_type`;
        const control = frappe.ui.form.make_control({
            parent: $host.get(0),
            df: {
                label: "",
                fieldname: `issue_type_${row.row_name}`,
                fieldtype: "Data",
                reqd: 0,
                change: () => {
                    if (this.is_hydrating_controls) return;
                    row.issue_type = control.get_value() || "";
                    this.schedule_save(row.row_name, { issue_type: row.issue_type });
                }
            },
            render_input: true
        });
        control.refresh();
        control.set_value(row.issue_type || "");
        this.row_controls[controlKey] = control;
    }

    render_failure_note(row, $panel) {
        if (!Number(row.require_failure_note || 0)) return;

        const $host = $panel.find(".failure-note");
        $host.append(`<div class="failure-field-label">${__("Note")} *</div>`);
        const controlKey = `${row.row_name}:user_note`;
        const control = frappe.ui.form.make_control({
            parent: $host.get(0),
            df: {
                label: "",
                fieldname: `user_note_${row.row_name}`,
                fieldtype: "Small Text",
                reqd: 0,
                change: () => {
                    if (this.is_hydrating_controls) return;
                    row.user_note = control.get_value() || "";
                    this.schedule_save(row.row_name, { user_note: row.user_note });
                }
            },
            render_input: true
        });
        control.refresh();
        control.set_value(row.user_note || "");
        this.row_controls[controlKey] = control;
    }

    render_failure_photo(row, $panel) {
        const $host = $panel.find(".failure-photo");
        $host.append(`<div class="failure-field-label">${__("Photo (Optional)")}</div>`);

        const controlKey = `${row.row_name}:evidence_photo`;
        const control = frappe.ui.form.make_control({
            parent: $host.get(0),
            df: {
                label: "",
                fieldname: `evidence_photo_${row.row_name}`,
                fieldtype: "Attach Image",
                reqd: 0,
                change: () => {
                    if (this.is_hydrating_controls) return;
                    row.evidence_photo = control.get_value() || "";
                    this.schedule_save(row.row_name, { evidence_photo: row.evidence_photo });
                }
            },
            render_input: true
        });
        control.refresh();
        control.set_value(row.evidence_photo || "");
        this.row_controls[controlKey] = control;
    }

    render_worker_section() {
        if (!Number(this.doc?.enable_worker_check || 0)) return;

        const workers = this.doc.workers || [];
        const summary = this.doc.worker_summary || {};
        const statusClass = summary.status === "Short" ? "is-short" : (summary.status === "Met" ? "is-met" : "");
        const $section = $(`
            <section class="worker-roster-section">
                <div class="worker-roster-header">
                    <div>
                        <div class="worker-roster-title">${__("Workers Check")}</div>
                        <div class="worker-roster-subtitle">${__("Required staffing and worker compliance")}</div>
                    </div>
                    ${this.doc.is_editable ? `
                        <div class="worker-roster-actions">
                            <button class="btn btn-default btn-add-internal-worker" type="button">+ ${__("Employee")}</button>
                            <button class="btn btn-default btn-add-external-worker" type="button">+ ${__("Add External Worker")}</button>
                            <button class="btn btn-primary btn-all-workers-ok" type="button">✓ ${__("All Workers OK")}</button>
                        </div>
                    ` : ""}
                </div>
                ${this.doc.is_editable ? `
                    <div class="worker-requirement-control">
                        <label for="required-worker-count-${this.escape(this.doc.name)}">${__("Required Workers (Production)")}</label>
                        <div class="worker-requirement-input-row">
                            <input id="required-worker-count-${this.escape(this.doc.name)}" class="form-control required-worker-count-input" type="number" min="0" inputmode="numeric" value="${this.escape(this.doc.required_worker_count ?? 0)}">
                            <button class="btn btn-primary btn-save-required-worker-count" type="button">${__("Save")}</button>
                        </div>
                        <div class="text-muted small">${__("Set by Production for this checklist run.")}</div>
                    </div>
                ` : ""}
                <div class="worker-summary-grid ${statusClass}">
                    <div><span>${__("Required")}</span><strong>${this.escape(summary.required ?? this.doc.required_worker_count ?? 0)}</strong></div>
                    <div><span>${__("Present")}</span><strong>${this.escape(summary.present ?? 0)}</strong></div>
                    <div><span>${__("Absent")}</span><strong>${this.escape(summary.absent ?? 0)}</strong></div>
                    <div><span>${__("Replacements")}</span><strong>${this.escape(summary.replacements ?? 0)}</strong></div>
                    <div><span>${__("Shortage")}</span><strong>${this.escape(summary.shortage ?? 0)}</strong></div>
                    <div><span>${__("Status")}</span><strong>${this.escape(summary.status || "Not Set")}</strong></div>
                </div>
                <div class="worker-roster-list"></div>
            </section>
        `);

        this.$body.append($section);
        const $list = $section.find(".worker-roster-list");

        if (!workers.length) {
            $list.html(`<div class="empty-state">${__("No workers added yet.")}</div>`);
        } else {
            workers.forEach((worker, index) => this.render_worker_card($list, worker, index));
        }

        if (!this.doc.is_editable) return;
        $section.find(".btn-save-required-worker-count").on("click", async () => {
            const raw = $section.find(".required-worker-count-input").val();
            const count = Number.parseInt(raw || "0", 10);
            if (!Number.isFinite(count) || count < 0) {
                frappe.msgprint(__("Required Worker Count must be zero or greater."));
                return;
            }
            await this.update_required_worker_count(count);
        });
        $section.find(".btn-add-internal-worker").on("click", () => this.open_add_internal_worker_dialog());
        $section.find(".btn-add-external-worker").on("click", () => this.open_add_external_worker_dialog());
        $section.find(".btn-all-workers-ok").on("click", async () => {
            (this.doc.workers || []).forEach(worker => {
                if ((worker.presence_status || "Present") === "Present") worker.inspection_status = "Pass";
            });
            await this.save_worker_roster();
        });
    }

    render_worker_card($list, worker, index) {
        const reasons = this.split_lines(this.doc.worker_failure_reason_options || "");
        const isFail = worker.inspection_status === "Fail";
        const sourceLabel = worker.worker_type === "Internal Employee" ? __("Employee") : __("External");
        const $card = $(`
            <div class="worker-roster-card" data-worker-index="${index}">
                <div class="worker-card-head">
                    <div>
                        <div class="worker-card-name">${this.escape(worker.worker_name || worker.employee || worker.external_worker || "-")}</div>
                        <div class="worker-card-meta">${this.escape(sourceLabel)}${worker.company_name ? ` · ${this.escape(worker.company_name)}` : ""}${worker.badge_no ? ` · ${__("No.")} ${this.escape(worker.badge_no)}` : ""}${Number(worker.is_replacement || 0) ? ` · ${__("Replacement")}` : ""}</div>
                    </div>
                    ${this.doc.is_editable ? `<button type="button" class="btn btn-xs btn-default btn-remove-worker">${__("Remove")}</button>` : ""}
                </div>
                <div class="worker-choice-row">
                    <button type="button" class="worker-choice-btn ${worker.presence_status === "Present" ? "is-selected is-pass" : ""}" data-presence="Present">${__("Present")}</button>
                    <button type="button" class="worker-choice-btn ${worker.presence_status === "Absent" ? "is-selected is-fail" : ""}" data-presence="Absent">${__("Absent")}</button>
                    <button type="button" class="worker-choice-btn ${Number(worker.is_replacement || 0) ? "is-selected" : ""}" data-replacement="1">${__("Replacement")}</button>
                </div>
                <div class="worker-choice-row">
                    ${["Pass", "Fail", "N/A"].map(value => `<button type="button" class="worker-choice-btn ${worker.inspection_status === value ? `is-selected ${value === "Pass" ? "is-pass" : value === "Fail" ? "is-fail" : ""}` : ""}" data-inspection="${value}">${this.escape(value)}</button>`).join("")}
                </div>
                ${isFail ? `
                    <div class="worker-failure-box">
                        ${reasons.length ? `<div class="worker-reason-grid">${reasons.map(reason => {
                            const selected = this.split_lines(worker.failure_reasons).includes(reason) ? "is-selected" : "";
                            return `<button type="button" class="worker-reason-btn ${selected}" data-reason="${this.escape(reason)}">${this.escape(reason)}</button>`;
                        }).join("")}</div>` : ""}
                        <button type="button" class="btn btn-sm btn-default btn-worker-details">${__("Note / Photo / Correction")}</button>
                    </div>
                ` : ""}
            </div>
        `);
        $list.append($card);
        if (!this.doc.is_editable) return;

        $card.find("[data-presence]").on("click", async e => {
            worker.presence_status = $(e.currentTarget).attr("data-presence");
            await this.save_worker_roster();
        });
        $card.find("[data-replacement]").on("click", async () => {
            worker.is_replacement = Number(worker.is_replacement || 0) ? 0 : 1;
            await this.save_worker_roster();
        });
        $card.find("[data-inspection]").on("click", async e => {
            worker.inspection_status = $(e.currentTarget).attr("data-inspection");
            if (worker.inspection_status !== "Fail") {
                worker.failure_reasons = "";
                worker.corrected_immediately = 0;
            }
            await this.save_worker_roster();
        });
        $card.find(".worker-reason-btn").on("click", async e => {
            const reason = $(e.currentTarget).attr("data-reason");
            const selected = new Set(this.split_lines(worker.failure_reasons));
            if (selected.has(reason)) selected.delete(reason); else selected.add(reason);
            worker.failure_reasons = Array.from(selected).join("\n");
            await this.save_worker_roster();
        });
        $card.find(".btn-worker-details").on("click", () => this.open_worker_details_dialog(worker));
        $card.find(".btn-remove-worker").on("click", async () => {
            this.doc.workers.splice(index, 1);
            await this.save_worker_roster();
        });
    }

    worker_payload() {
        return (this.doc?.workers || []).map(worker => ({
            worker_type: worker.worker_type,
            employee: worker.employee || "",
            external_worker: worker.external_worker || "",
            presence_status: worker.presence_status || "Present",
            is_replacement: Number(worker.is_replacement || 0),
            inspection_status: worker.inspection_status || "",
            failure_reasons: worker.failure_reasons || "",
            note: worker.note || "",
            evidence_photo: worker.evidence_photo || "",
            corrected_immediately: Number(worker.corrected_immediately || 0)
        }));
    }

    async update_required_worker_count(count) {
        if (!this.doc?.name || !this.doc.is_editable) return;
        const r = await frappe.call({
            method: "taj_core.checklist.api.update_required_worker_count",
            args: { docname: this.doc.name, required_worker_count: count },
            freeze: false
        });
        this.doc = r.message;
        this.render_doc();
        frappe.show_alert({ message: __("Required worker count updated."), indicator: "green" });
    }

    async save_worker_roster() {
        if (!this.doc?.name || !this.doc.is_editable) return;
        const r = await frappe.call({
            method: "taj_core.checklist.api.save_workers",
            args: { docname: this.doc.name, workers: JSON.stringify(this.worker_payload()) },
            freeze: false
        });
        this.doc = r.message;
        this.render_doc();
    }

    open_add_internal_worker_dialog() {
        const dialog = new frappe.ui.Dialog({
            title: __("Add Employee"),
            fields: [
                { fieldname: "employee", fieldtype: "Link", options: "Employee", label: __("Employee"), reqd: 1, get_query: () => ({ filters: { status: "Active" } }) },
                { fieldname: "presence_status", fieldtype: "Select", options: "Present\nAbsent", label: __("Presence"), default: "Present", reqd: 1 },
                { fieldname: "is_replacement", fieldtype: "Check", label: __("Replacement") }
            ],
            primary_action_label: __("Add"),
            primary_action: async values => {
                this.doc.workers = this.doc.workers || [];
                this.doc.workers.push({
                    worker_type: "Internal Employee",
                    employee: values.employee,
                    presence_status: values.presence_status || "Present",
                    is_replacement: Number(values.is_replacement || 0),
                    inspection_status: ""
                });
                dialog.hide();
                await this.save_worker_roster();
            }
        });
        dialog.show();
    }

    open_add_external_worker_dialog() {
        const dialog = new frappe.ui.Dialog({
            title: __("Add External Worker"),
            fields: [
                { fieldname: "existing_worker", fieldtype: "Link", options: "Checklist External Worker", label: __("Existing Worker"), get_query: () => ({ filters: { active: 1 } }) },
                { fieldtype: "Section Break", label: __("Or Create New") },
                { fieldname: "worker_name", fieldtype: "Data", label: __("Worker Name") },
                { fieldname: "company_name", fieldtype: "Data", label: __("Company Name"), default: this.doc.default_worker_company || "" },
                { fieldname: "supplier", fieldtype: "Link", options: "Supplier", label: __("Supplier"), default: this.doc.default_worker_supplier || "" },
                { fieldname: "badge_no", fieldtype: "Data", label: __("Badge / Worker No.") },
                { fieldname: "is_replacement", fieldtype: "Check", label: __("Replacement") }
            ],
            primary_action_label: __("Add"),
            primary_action: async values => {
                let workerName = values.existing_worker;
                if (!workerName) {
                    if (!values.worker_name) {
                        frappe.msgprint(__("Choose an existing external worker or enter a new worker name."));
                        return;
                    }
                    const r = await frappe.call({
                        method: "taj_core.checklist.api.quick_create_external_worker",
                        args: {
                            docname: this.doc.name,
                            worker_name: values.worker_name,
                            company_name: values.company_name,
                            supplier: values.supplier,
                            badge_no: values.badge_no
                        }
                    });
                    workerName = r.message.name;
                }
                this.doc.workers = this.doc.workers || [];
                this.doc.workers.push({
                    worker_type: "External Worker",
                    external_worker: workerName,
                    presence_status: "Present",
                    is_replacement: Number(values.is_replacement || 0),
                    inspection_status: ""
                });
                dialog.hide();
                await this.save_worker_roster();
            }
        });
        dialog.show();
    }

    open_worker_details_dialog(worker) {
        const dialog = new frappe.ui.Dialog({
            title: worker.worker_name || __("Worker Details"),
            fields: [
                { fieldname: "note", fieldtype: "Small Text", label: __("Note"), default: worker.note || "" },
                { fieldname: "evidence_photo", fieldtype: "Attach Image", label: __("Evidence Photo"), default: worker.evidence_photo || "" },
                { fieldname: "corrected_immediately", fieldtype: "Check", label: __("Corrected Immediately"), default: Number(worker.corrected_immediately || 0) }
            ],
            primary_action_label: __("Save"),
            primary_action: async values => {
                worker.note = values.note || "";
                worker.evidence_photo = values.evidence_photo || "";
                worker.corrected_immediately = Number(values.corrected_immediately || 0);
                dialog.hide();
                await this.save_worker_roster();
            }
        });
        dialog.show();
    }

    render_actions() {
        this.$actions.empty();
        if (Number(this.doc?.is_time_locked || 0) === 1) {
            this.$actions.html(`
                <div class="alert alert-warning mb-0">
                    <strong>${__("Scheduled start")}:</strong>
                    ${this.escape(this.doc.scheduled_start_at || "-")}
                    <div>${__("This checklist is view-only until its scheduled start time.")}</div>
                </div>
            `);
            return;
        }
        if (!this.doc?.is_editable) return;

        const hasQuickPassRows = Boolean(this.doc.can_quick_pass) && (this.doc.questions || []).some(row =>
            !String(row.answer || "").trim()
            && this.can_quick_pass_row(row)
        );

        this.$actions.html(`
            <div class="submit-area checklist-action-row">
                ${hasQuickPassRows ? `<button class="btn btn-default btn-quick-pass" type="button">✓ ${__("All OK")}</button>` : ""}
                <button class="btn btn-primary btn-submit-doc" type="button">${__("Submit")}</button>
            </div>
        `);

        this.$actions.find(".btn-quick-pass").on("click", () => this.apply_quick_pass());
        this.$actions.find(".btn-submit-doc").on("click", () => this.submit_doc());

        if (this.is_submitting) {
            this.$actions.find("button").prop("disabled", true);
            this.$actions.find(".btn-submit-doc").text(__("Submitting..."));
        }
    }

    async apply_quick_pass() {
        if (!this.doc?.name || !this.doc.is_editable || this.is_saving || this.is_submitting) return;

        if (this.save_timer) {
            clearTimeout(this.save_timer);
            this.save_timer = null;
        }
        await this.last_save_promise;
        await this.flush_pending_saves();
        if (this.last_save_failed) return;

        try {
            const r = await frappe.call({
                method: "taj_core.checklist.api.quick_pass_checklist",
                args: { docname: this.doc.name },
                freeze: true,
                freeze_message: __("Applying All OK...")
            });
            this.doc = r.message;
            this.render_doc();
            frappe.show_alert({ message: __("Eligible checks marked OK."), indicator: "green" });
        } catch (e) {
            frappe.msgprint({ title: __("Error"), indicator: "red", message: __("Could not apply All OK.") });
            console.error(e);
        }
    }

    schedule_save(row_name, patch) {
        if (!this.doc?.name || !this.doc.is_editable) return;

        const normalizedPatch = (patch && typeof patch === "object" && !Array.isArray(patch))
            ? patch
            : { answer: patch };

        this.last_save_failed = false;
        this.pending_changes[row_name] = {
            ...(this.pending_changes[row_name] || {}),
            ...normalizedPatch
        };
        this.set_save_state(__("Pending changes..."));

        if (this.save_timer) clearTimeout(this.save_timer);
        this.save_timer = setTimeout(() => {
            this.last_save_promise = this.last_save_promise.then(() => this.flush_pending_saves());
        }, 400);
    }

    async flush_pending_saves() {
        if (!this.doc?.name || !this.doc.is_editable) return;
        if (this.is_saving) return;

        const entries = Object.entries(this.pending_changes);
        if (!entries.length) {
            if (!this.is_submitting && !this.last_save_failed) this.set_save_state(__("All changes saved."));
            return;
        }

        this.is_saving = true;
        this.last_save_failed = false;
        this.set_save_state(__("Saving..."));

        const payload = entries.map(([row_name, patch]) => ({ row_name, ...patch }));
        this.pending_changes = {};

        try {
            const r = await frappe.call({
                method: "taj_core.checklist.api.save_answers",
                args: { docname: this.doc.name, answers: JSON.stringify(payload) }
            });
            this.doc = r.message;
            this.last_save_error_key = "";
            this.set_save_state(__("All changes saved."));
        } catch (e) {
            payload.forEach(item => {
                const { row_name, ...patch } = item;
                this.pending_changes[row_name] = {
                    ...(this.pending_changes[row_name] || {}),
                    ...patch
                };
            });
            this.last_save_failed = true;
            this.set_save_state(__("Save failed."));

            const error_key = String((e && (e.message || e.exc_type || e.statusText)) || "save_failed");
            if (this.last_save_error_key !== error_key) {
                this.last_save_error_key = error_key;
                frappe.show_alert({ message: __("Auto save failed. Please try again."), indicator: "red" });
            }
            console.error(e);
        } finally {
            this.is_saving = false;
            this.render_progress();
            this.render_actions();
        }

        if (!this.last_save_failed && Object.keys(this.pending_changes).length) {
            await this.flush_pending_saves();
        }
    }

    validate_before_submit() {
        const problems = [];

        (this.doc?.questions || []).forEach(row => {
            const label = row.question_text || row.question || row.row_name;
            const answer = String(row.answer == null ? "" : row.answer).trim();

            if (Number(row.is_required || 0) === 1 && !answer) {
                problems.push(`${label}: ${__("answer is required")}`);
                return;
            }

            if (!answer || !this.is_failure_answer(row, answer)) return;

            if (Number(row.require_affected_item || 0) === 1 && !this.split_lines(row.affected_items).length) {
                problems.push(`${label}: ${__("affected item is required")}`);
            }
            if (Number(row.require_issue_type || 0) === 1 && !String(row.issue_type || "").trim()) {
                problems.push(`${label}: ${__("issue type is required")}`);
            }
            if (Number(row.require_failure_reason || 0) === 1 && !String(row.failure_reason || "").trim()) {
                problems.push(`${label}: ${__("failure reason is required")}`);
            }
            if (Number(row.require_failure_note || 0) === 1 && !String(row.user_note || "").trim()) {
                problems.push(`${label}: ${__("note is required")}`);
            }
        });

        return problems;
    }

    async submit_doc() {
        if (!this.doc?.name || !this.doc.is_editable || this.is_submitting) {
            return;
        }

        const missing = this.validate_before_submit();
        if (missing.length) {
            const items = missing.map(item => `<li>${this.escape(item)}</li>`).join("");
            frappe.msgprint({
                title: __("Missing Required Information"),
                indicator: "orange",
                message: `<ul class="mb-0 pl-3">${items}</ul>`
            });
            return;
        }

        this.is_submitting = true;
        this.render_actions();

        try {
            if (this.save_timer) {
                clearTimeout(this.save_timer);
                this.save_timer = null;
            }

            await this.last_save_promise;
            await this.flush_pending_saves();

            if (this.last_save_failed) {
                frappe.throw(__("Please fix save errors before submit."));
            }

            const r = await frappe.call({
                method: "taj_core.checklist.api.submit_checklist_answer",
                args: { docname: this.doc.name }
            });

            frappe.show_alert({
                message: __("Checklist submitted successfully."),
                indicator: "green"
            });

            this.set_save_state("");
            await this.load_dashboard();
            await this.load_doc(r.message.name);
        } catch (e) {
            frappe.msgprint({
                title: __("Error"),
                indicator: "red",
                message: __("Failed to submit checklist.")
            });
            console.error(e);
        } finally {
            this.is_submitting = false;
            this.render_actions();
        }
    }

    get_indicator_color(status) {
        if (status === "Completed") return "green";
        if (status === "In Progress") return "orange";
        if (["Auto Closed", "Auto Closed - Incomplete", "Missed"].includes(status)) return "darkgrey";
        if (status === "Expired") return "red";
        return "blue";
    }
}
