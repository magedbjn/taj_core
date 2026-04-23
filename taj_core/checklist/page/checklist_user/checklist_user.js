frappe.pages["checklist-user"].on_page_load = function (wrapper) {
    new ChecklistUserPage(wrapper);
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

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Checklist User"),
            single_column: true
        });

        $(this.page.wrapper).find(".page-head").remove();
        setup_checklist_fullwidth(this.page.wrapper);

        this.render_layout();
        this.bind_events();
        this.load_initial_state();
    }

    escape(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
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
                        <div class="selected-doc-actions"></div>
                    </div>
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
        this.$drawer.removeClass("is-open");
        this.$drawerBackdrop.removeClass("is-open");
        $("body").removeClass("checklist-drawer-open");
    }

    set_save_state(stateText = "") {
        this.saveState = stateText;
        this.render_progress();
    }

    async load_initial_state() {
        await this.load_dashboard();

        const opts = frappe.route_options || {};
        if (opts.checklist_answer) {
            await this.load_doc(opts.checklist_answer);
        }
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
        if (value === "auto closed") return "auto-closed";
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
                    ${__("Questions")}: ${this.escape(questionCount)}
                </span>
            `;

            const statusBadge = `
                <span class="status-pill status-${statusSlug}">
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
                            <div class="checklist-list-template">${this.escape(doc.template || "-")}</div>
                            <div class="checklist-list-docname">${this.escape(doc.name || "-")}</div>
                        </div>

                        <div class="checklist-list-side">
                            ${questionBadge}
                            ${statusBadge}
                            ${previousOpenBadge}
                        </div>
                    </div>

                    <div class="checklist-list-meta">
                        <div class="checklist-list-meta-item"><strong>${__("Status")}:</strong> ${this.escape(doc.status || "-")}</div>
                        <div class="checklist-list-meta-item"><strong>${__("Department")}:</strong> ${this.escape(doc.department || "-")}</div>
                        <div class="checklist-list-meta-item"><strong>${__("Assigned User")}:</strong> ${this.escape(doc.assigned_user || "-")}</div>
                        <div class="checklist-list-meta-item"><strong>${__("Result")}:</strong> ${this.escape(doc.result_status || "Normal")}</div>
                        ${doc.is_previous_cycle_open ? `<div class="checklist-list-meta-item"><strong>${__("Open From")}:</strong> ${this.escape(doc.open_from_date || doc.posting_date || "-")}</div>` : ""}
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
                        <div class="meta-line"><strong>${__("Assigned User")}:</strong> ${this.escape(this.doc.assigned_user || "-")}</div>
                        <div class="meta-line"><strong>${__("Status")}:</strong> ${this.escape(this.doc.status || "-")}</div>
                        <div class="meta-line"><strong>${__("Result")}:</strong> ${this.escape(this.doc.result_status || "Normal")}</div>
                        <div class="meta-line"><strong>${__("Questions")}:</strong> ${this.escape((this.doc.questions || []).length)}</div>

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
        const lines = String(raw || "")
            .split(/\r?\n/)
            .map(v => v.trim())
            .filter(Boolean);

        return "\n" + lines.join("\n");
    }

    render_questions() {
        const questions = this.doc?.questions || [];
        this.$body.empty();
        this.row_controls = {};

        if (!questions.length) {
            this.$body.html(`<div class="empty-state">${__("No questions found.")}</div>`);
            return;
        }

        if (!this.doc.is_editable) {
            questions.forEach((row, index) => {
                const issueClass = row.has_issue ? "has-issue" : "";
                const issueLine = row.has_issue
                    ? `<div style="margin-bottom:8px;"><span class="status-pill status-expired">${__("Issue Answer")}</span></div>`
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
                        ${row.issue_note ? `<div class="readonly-answer-value"><strong>${__("Issue Note")}:</strong> ${this.escape(row.issue_note)}</div>` : ""}
                    </div>
                `);
            });
            return;
        }

        this.is_hydrating_controls = true;

        questions.forEach((row, index) => {
            const $card = $(`
                <div class="checklist-question-card">
                    <div class="checklist-question-title">
                        <span class="question-number">${index + 1}</span>
                        <span>${this.escape(row.question_text || row.question || "")}</span>
                    </div>
                    <div class="question-control"></div>
                </div>
            `);

            this.$body.append($card);

            const control = frappe.ui.form.make_control({
                parent: $card.find(".question-control").get(0),
                df: this.get_df_for_row(row),
                render_input: true
            });

            control.refresh();
            control.set_value(row.answer || "");
            this.row_controls[row.row_name] = control;
        });

        this.is_hydrating_controls = false;
    }

    render_actions() {
        this.$actions.empty();

        if (!this.doc?.is_editable) {
            return;
        }

        this.$actions.html(`
            <div class="submit-area">
                <button class="btn btn-primary btn-submit-doc">${__("Submit")}</button>
            </div>
        `);

        this.$actions.find(".btn-submit-doc").on("click", () => this.submit_doc());

        if (this.is_submitting) {
            this.$actions.find(".btn-submit-doc").prop("disabled", true).text(__("Submitting..."));
        }
    }

    get_df_for_row(row) {
        const base_df = {
            label: "",
            fieldname: `answer_${row.row_name}`,
            reqd: 1,
            change: () => {
                if (this.is_hydrating_controls) {
                    return;
                }

                const control = this.row_controls[row.row_name];
                const value = control ? control.get_value() : "";
                this.schedule_save(row.row_name, value);
            }
        };

        if (row.type === "Yes/No") {
            return { ...base_df, fieldtype: "Select", options: "\nYes\nNo" };
        }

        if (row.type === "Int") {
            return { ...base_df, fieldtype: "Int" };
        }

        if (row.type === "Float") {
            return { ...base_df, fieldtype: "Float" };
        }

        if (row.type === "Select") {
            return {
                ...base_df,
                fieldtype: "Select",
                options: this.normalize_select_options(row.answer_options)
            };
        }

        return { ...base_df, fieldtype: "Data" };
    }

    schedule_save(row_name, answer) {
        if (!this.doc?.name || !this.doc.is_editable) return;

        this.last_save_failed = false;
        this.pending_changes[row_name] = answer;
        this.set_save_state(__("Pending changes..."));

        if (this.save_timer) {
            clearTimeout(this.save_timer);
        }

        this.save_timer = setTimeout(() => {
            this.last_save_promise = this.last_save_promise.then(() => this.flush_pending_saves());
        }, 400);
    }

    async flush_pending_saves() {
        if (!this.doc?.name || !this.doc.is_editable) return;
        if (this.is_saving) return;

        const entries = Object.entries(this.pending_changes);
        if (!entries.length) {
            if (!this.is_submitting && !this.last_save_failed) {
                this.set_save_state(__("All changes saved."));
            }
            return;
        }

        this.is_saving = true;
        this.last_save_failed = false;
        this.set_save_state(__("Saving..."));

        const payload = entries.map(([row_name, answer]) => ({ row_name, answer }));
        this.pending_changes = {};

        try {
            const r = await frappe.call({
                method: "taj_core.checklist.api.save_answers",
                args: {
                    docname: this.doc.name,
                    answers: JSON.stringify(payload)
                }
            });

            this.doc = r.message;
            this.last_save_error_key = "";
            this.set_save_state(__("All changes saved."));
        } catch (e) {
            payload.forEach(item => {
                this.pending_changes[item.row_name] = item.answer;
            });

            this.last_save_failed = true;
            this.set_save_state(__("Save failed."));

            const error_key = String((e && (e.message || e.exc_type || e.statusText)) || "save_failed");
            if (this.last_save_error_key !== error_key) {
                this.last_save_error_key = error_key;
                frappe.show_alert({
                    message: __("Auto save failed. Please try again."),
                    indicator: "red"
                });
            }

            console.error(e);
        } finally {
            this.is_saving = false;
            this.render_progress();
        }

        if (!this.last_save_failed && Object.keys(this.pending_changes).length) {
            await this.flush_pending_saves();
        }
    }

    validate_before_submit() {
        const missing = [];

        (this.doc?.questions || []).forEach(row => {
            const control = this.row_controls[row.row_name];
            const liveValue = control ? control.get_value() : row.answer;
            if (!String(liveValue || "").trim()) {
                missing.push(row.question_text || row.question || row.row_name);
            }
        });

        return missing;
    }

    async submit_doc() {
        if (!this.doc?.name || !this.doc.is_editable || this.is_submitting) {
            return;
        }

        const missing = this.validate_before_submit();
        if (missing.length) {
            frappe.msgprint({
                title: __("Missing Answers"),
                indicator: "orange",
                message: __("Please answer all questions before submit.")
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
        if (status === "Auto Closed") return "darkgrey";
        if (status === "Expired") return "red";
        return "blue";
    }
}
