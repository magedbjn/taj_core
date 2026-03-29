// frappe.pages['checklist-admin'].on_page_load = function(wrapper) {
// 	var page = frappe.ui.make_app_page({
// 		parent: wrapper,
// 		title: 'Checklist Admin',
// 		single_column: true
// 	});
// }
function setup_checklist_fullscreen(wrapper) {
    $(wrapper).addClass("checklist-page-fullscreen");
    $("body").addClass("checklist-fullscreen-mode");

    if (!window.__checklist_fullscreen_route_guard_added) {
        window.__checklist_fullscreen_route_guard_added = true;

        frappe.router.on("change", () => {
            const route = frappe.get_route ? frappe.get_route() : [];
            const current_page = route && route.length ? route[0] : "";

            if (!["checklist-user", "checklist-manager"].includes(current_page)) {
                $("body").removeClass("checklist-fullscreen-mode");
            }
        });
    }
}

frappe.pages["checklist-admin"].on_page_load = function (wrapper) {
    new ChecklistAnswerManagerPage(wrapper);
};

class ChecklistAnswerManagerPage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.doc = null;
        this.lastData = null;
        this.activeQuickView = null;
        this.activeTab = "today-open";
        this.selectedDocname = null;

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Checklist Manager Dashboard"),
            single_column: true
        });

        $(this.page.wrapper).find(".page-head").remove();

        setup_checklist_fullscreen(this.page.wrapper);
        
        this.render_layout();
        this.bind_events();
        this.load_initial_state();
    }

    escape(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }

    render_layout() {
        $(this.page.body).html(`
            <div class="checklist-mgr-page">
                <div class="mgr-header">
                    <div class="mgr-header-left">
                        <div class="mgr-page-title">${__("Checklist Manager Dashboard")}</div>
                        <div class="mgr-page-subtitle">${__("Simple dashboard for manager with tabs, fast search, and quick daily monitoring")}</div>
                    </div>

                    <div class="mgr-filters">
                        <div class="filter-control filter-template"></div>
                        <div class="filter-control filter-department"></div>
                        <div class="filter-control filter-user"></div>
                        <div class="filter-control filter-date"></div>
                        <div class="filter-control filter-status"></div>
                        <div class="filter-control filter-issue"></div>
                        <button class="btn btn-primary btn-search">${__("Search")}</button>
                    </div>
                </div>

                <div class="mgr-summary-row">
                    <div class="summary-card summary-card-clickable is-blue" data-quick-view="today_all">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-blue">
                                <svg class="summary-icon-svg" viewBox="0 0 24 24" aria-hidden="true">
                                    <rect x="4" y="10" width="3" height="8" rx="1.2"></rect>
                                    <rect x="10.5" y="6" width="3" height="12" rx="1.2"></rect>
                                    <rect x="17" y="3" width="3" height="15" rx="1.2"></rect>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Today Total")}</div>
                                <div class="summary-value today-total">0</div>
                            </div>
                        </div>
                        <div class="summary-hint">${__("Show all today's records")}</div>
                    </div>

                    <div class="summary-card summary-card-clickable is-orange" data-quick-view="today_open">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-orange">
                                <svg class="summary-icon-svg" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 6V12L16 14"></path>
                                    <circle cx="12" cy="12" r="7.5"></circle>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Today Open")}</div>
                                <div class="summary-value today-open">0</div>
                            </div>
                        </div>
                        <div class="summary-hint">${__("Open records")}</div>
                    </div>

                    <div class="summary-card summary-card-clickable is-green" data-quick-view="today_completed">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-green">
                                <svg class="summary-icon-svg" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M7 12.5L10.2 15.7L17.5 8.5"></path>
                                    <circle cx="12" cy="12" r="8"></circle>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Today Completed")}</div>
                                <div class="summary-value today-completed">0</div>
                            </div>
                        </div>
                        <div class="summary-hint">${__("Completed records")}</div>
                    </div>

                    <div class="summary-card summary-card-clickable is-red" data-quick-view="today_remaining">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-red">
                                <svg class="summary-icon-svg" viewBox="0 0 24 24" aria-hidden="true">
                                    <circle cx="12" cy="13" r="7.5"></circle>
                                    <path d="M12 13V9.5"></path>
                                    <path d="M12 13L14.8 14.8"></path>
                                    <path d="M9 3.5H15"></path>
                                    <path d="M12 5.5V3.5"></path>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Today Remaining")}</div>
                                <div class="summary-value today-remaining">0</div>
                            </div>
                        </div>
                        <div class="summary-hint">${__("Remaining / incomplete")}</div>
                    </div>

                    <div class="summary-card summary-card-clickable is-purple" data-quick-view="today_has_issue">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-purple">
                                <svg class="summary-icon-svg" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 7.5V12.5"></path>
                                    <circle cx="12" cy="16.5" r="0.8" fill="#ffffff" stroke="none"></circle>
                                    <path d="M12 3.8L20 18H4L12 3.8Z"></path>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Today Has Issue")}</div>
                                <div class="summary-value today-has-issue">0</div>
                            </div>
                        </div>
                        <div class="summary-hint">${__("Show records with issues")}</div>
                    </div>
                </div>

                <div class="tab-strip">
                    <button class="tab-btn is-active" data-tab="today-open">${__("Today Open")}</button>
                    <button class="tab-btn" data-tab="today-completed">${__("Today Completed")}</button>
                    <button class="tab-btn" data-tab="search">${__("Search")}</button>
                    <button class="tab-btn" data-tab="template">${__("By Template")}</button>
                    <button class="tab-btn" data-tab="employee">${__("By Employee")}</button>
                </div>

                <div class="tab-panel is-active" data-tab="today-open">
                    <div class="mgr-section">
                        <div class="section-header">
                            <div>
                                <div class="section-title">${__("Today Open")}</div>
                                <div class="section-subtitle">${__("Tasks as mini cards")}</div>
                            </div>
                        </div>
                        <div class="task-mini-grid today-open-mini-grid"></div>
                    </div>
                </div>

                <div class="tab-panel" data-tab="today-completed">
                    <div class="mgr-section">
                        <div class="section-header">
                            <div>
                                <div class="section-title">${__("Today Completed")}</div>
                                <div class="section-subtitle">${__("Completed tasks as mini cards")}</div>
                            </div>
                        </div>
                        <div class="task-mini-grid today-completed-mini-grid"></div>
                    </div>
                </div>

                <div class="tab-panel" data-tab="search">
                    <div class="mgr-panel">
                        <div class="panel-header">
                            <div class="panel-title search-results-title">${__("Filtered Search Results")}</div>
                            <div class="panel-actions">
                                <button class="btn btn-default btn-xs btn-reset-quick-view" style="display:none;">
                                    ${__("Reset Quick View")}
                                </button>
                            </div>
                        </div>
                        <div class="search-results-list"></div>
                    </div>
                </div>

                <div class="tab-panel" data-tab="template">
                    <div class="mgr-panel">
                        <div class="panel-header">
                            <div class="panel-title">${__("By Template")}</div>
                        </div>
                        <div class="template-summary-list"></div>
                    </div>
                </div>

                <div class="tab-panel" data-tab="employee">
                    <div class="mgr-panel">
                        <div class="panel-header">
                            <div class="panel-title">${__("By Employee")}</div>
                        </div>
                        <div class="employee-summary-list"></div>
                    </div>
                </div>

                <div class="selected-doc-wrapper" style="display:none;">
                    <div class="selected-doc-meta"></div>
                    <div class="selected-doc-progress"></div>
                    <div class="selected-doc-body"></div>
                </div>
            </div>
        `);

        this.$todayTotal = $(this.page.body).find(".today-total");
        this.$todayOpen = $(this.page.body).find(".today-open");
        this.$todayCompleted = $(this.page.body).find(".today-completed");
        this.$todayRemaining = $(this.page.body).find(".today-remaining");
        this.$todayHasIssue = $(this.page.body).find(".today-has-issue");

        this.$todayOpenMiniGrid = $(this.page.body).find(".today-open-mini-grid");
        this.$todayCompletedMiniGrid = $(this.page.body).find(".today-completed-mini-grid");

        this.$searchResultsList = $(this.page.body).find(".search-results-list");
        this.$templateSummaryList = $(this.page.body).find(".template-summary-list");
        this.$employeeSummaryList = $(this.page.body).find(".employee-summary-list");
        this.$searchResultsTitle = $(this.page.body).find(".search-results-title");
        this.$resetQuickView = $(this.page.body).find(".btn-reset-quick-view");
        this.$summaryCards = $(this.page.body).find(".summary-card-clickable");
        this.$tabButtons = $(this.page.body).find(".tab-btn");
        this.$tabPanels = $(this.page.body).find(".tab-panel");

        this.$meta = $(this.page.body).find(".selected-doc-meta");
        this.$progress = $(this.page.body).find(".selected-doc-progress");
        this.$body = $(this.page.body).find(".selected-doc-body");
        this.$selectedWrapper = $(this.page.body).find(".selected-doc-wrapper");

        this.template_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-template").get(0),
            df: {
                label: __("Template"),
                fieldname: "template",
                fieldtype: "Link",
                options: "Checklist Question Template"
            },
            render_input: true
        });

        this.department_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-department").get(0),
            df: {
                label: __("Department"),
                fieldname: "department",
                fieldtype: "Link",
                options: "Department"
            },
            render_input: true
        });

        this.user_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-user").get(0),
            df: {
                label: __("User"),
                fieldname: "assigned_user",
                fieldtype: "Link",
                options: "User"
            },
            render_input: true
        });

        this.date_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-date").get(0),
            df: {
                label: __("Date"),
                fieldname: "search_date",
                fieldtype: "Date",
                default: frappe.datetime.get_today()
            },
            render_input: true
        });

        this.status_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-status").get(0),
            df: {
                label: __("Status"),
                fieldname: "status",
                fieldtype: "Select",
                options: "\nAll\nOpen\nDraft\nIn Progress\nCompleted\nAuto Closed"
            },
            render_input: true
        });

        this.issue_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-issue").get(0),
            df: {
                label: __("Issue Filter"),
                fieldname: "issue_filter",
                fieldtype: "Select",
                options: "\nAll\nHas Issue Only\nNo Issue Only"
            },
            render_input: true
        });

        this.template_control.refresh();
        this.department_control.refresh();
        this.user_control.refresh();
        this.date_control.refresh();
        this.status_control.refresh();
        this.issue_control.refresh();

        this.date_control.set_value(frappe.datetime.get_today());
        this.status_control.set_value("All");
        this.issue_control.set_value("All");
    }

    bind_events() {
        $(this.page.body).find(".btn-search").on("click", () => {
            this.set_active_tab("search");
            this.load_dashboard();
        });

        this.$summaryCards.on("click", (e) => {
            const quickView = $(e.currentTarget).attr("data-quick-view");
            this.apply_quick_view(quickView);
        });

        this.$resetQuickView.on("click", () => {
            this.reset_quick_view();
        });

        this.$tabButtons.on("click", (e) => {
            this.set_active_tab($(e.currentTarget).attr("data-tab"));
        });
    }

    set_active_tab(tabName) {
        this.activeTab = tabName;
        this.$tabButtons.removeClass("is-active");
        this.$tabPanels.removeClass("is-active");

        this.$tabButtons.filter(`[data-tab="${tabName}"]`).addClass("is-active");
        this.$tabPanels.filter(`[data-tab="${tabName}"]`).addClass("is-active");
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
            const r = await frappe.call({
                method: "taj_core.checklist.api.get_manager_dashboard_data",
                args: {
                    search_date: this.date_control.get_value(),
                    template: this.template_control.get_value(),
                    department: this.department_control.get_value(),
                    assigned_user: this.user_control.get_value(),
                    status: this.status_control.get_value(),
                    issue_filter: this.issue_control.get_value()
                }
            });

            const data = r.message || {};
            const summary = data.summary || {};

            this.lastData = data;
            this.activeQuickView = null;
            this.$summaryCards.removeClass("is-active");
            this.$resetQuickView.hide();

            this.$todayTotal.text(summary.today_total || 0);
            this.$todayOpen.text(summary.today_open || 0);
            this.$todayCompleted.text(summary.today_completed || 0);
            this.$todayRemaining.text(summary.today_remaining || 0);
            this.$todayHasIssue.text(summary.today_has_issue || 0);

            this.render_mini_cards(
                this.$todayOpenMiniGrid,
                data.today_open || [],
                __("No open tasks today."),
                "is-open"
            );

            this.render_mini_cards(
                this.$todayCompletedMiniGrid,
                data.today_completed || [],
                __("No completed tasks today."),
                "is-completed"
            );

            this.render_doc_list(
                this.$searchResultsList,
                data.search_results || [],
                __("No results found.")
            );

            this.render_summary_list(
                this.$templateSummaryList,
                data.template_summary || [],
                __("No template summary found.")
            );

            this.render_summary_list(
                this.$employeeSummaryList,
                data.employee_summary || [],
                __("No employee summary found.")
            );
        } catch (e) {
            frappe.msgprint({
                title: __("Error"),
                indicator: "red",
                message: __("Failed to load manager dashboard.")
            });
            console.error(e);
        }
    }

    render_mini_cards($target, docs, emptyText, toneClass) {
        $target.empty();

        if (!docs.length) {
            $target.html(`<div class="empty-state">${emptyText}</div>`);
            return;
        }

        docs.forEach((doc, index) => {
            const template = this.escape(doc.template || "-");
            const docname = this.escape(doc.name || "-");
            const user = this.escape(doc.assigned_user || "-");
            const department = this.escape(doc.department || "-");
            const hasIssueClass = doc.has_issue ? "has-issue" : "";
            const activeClass = this.selectedDocname === doc.name ? "is-active" : "";

            const $card = $(`
                <div class="task-mini-card ${toneClass} ${hasIssueClass} ${activeClass}" title="${template} | ${docname}">
                    <div class="task-mini-top">
                        <div class="task-mini-index">${index + 1}</div>
                        <div class="task-mini-status-dot"></div>
                    </div>

                    <div>
                        <div class="task-mini-template">${template}</div>
                        <div class="task-mini-docname">${docname}</div>
                    </div>

                    <div class="task-mini-meta">
                        <div>${user}</div>
                        <div>${department}</div>
                        <div>${doc.has_issue ? __("Has Issue") : __("Normal")}</div>
                    </div>
                </div>
            `);

            $card.on("click", () => this.load_doc(doc.name));
            $target.append($card);
        });
    }

    apply_quick_view(quickView) {
        if (!this.lastData) return;

        this.$summaryCards.removeClass("is-active");
        this.$summaryCards.filter(`[data-quick-view="${quickView}"]`).addClass("is-active");
        this.activeQuickView = quickView;

        if (quickView === "today_open") {
            this.set_active_tab("today-open");
            this.$resetQuickView.hide();
            return;
        }

        if (quickView === "today_completed") {
            this.set_active_tab("today-completed");
            this.$resetQuickView.hide();
            return;
        }

        let docs = [];
        let title = __("Filtered Search Results");
        let emptyText = __("No results found.");

        if (quickView === "today_all") {
            docs = this.lastData.today_all || [];
            title = __("Today Total");
            emptyText = __("No records found for today.");
        } else if (quickView === "today_remaining") {
            docs = this.lastData.today_remaining_docs || [];
            title = __("Today Remaining");
            emptyText = __("No remaining records found for today.");
        } else if (quickView === "today_has_issue") {
            docs = this.lastData.today_has_issue_docs || [];
            title = __("Today Has Issue");
            emptyText = __("No issue records found for today.");
        }

        this.$searchResultsTitle.text(title);
        this.render_doc_list(this.$searchResultsList, docs, emptyText);
        this.$resetQuickView.show();
        this.set_active_tab("search");
    }

    reset_quick_view() {
        if (!this.lastData) return;

        this.activeQuickView = null;
        this.$summaryCards.removeClass("is-active");
        this.$resetQuickView.hide();
        this.$searchResultsTitle.text(__("Filtered Search Results"));

        this.render_doc_list(
            this.$searchResultsList,
            this.lastData.search_results || [],
            __("No results found.")
        );
    }

    render_doc_list($target, docs, emptyText) {
        $target.empty();

        if (!docs.length) {
            $target.html(`<div class="empty-state">${emptyText}</div>`);
            return;
        }

        docs.forEach(doc => {
            const issueClass = doc.has_issue ? "has-issue" : "";
            const activeClass = this.selectedDocname === doc.name ? "is-active" : "";
            const issueBadge = doc.has_issue
                ? `<span class="issue-badge is-issue">${__("Has Issue")}</span>`
                : `<span class="issue-badge is-normal">${__("Normal")}</span>`;

            const $item = $(`
                <div class="checklist-list-item ${issueClass} ${activeClass}">
                    <div class="checklist-list-template">${this.escape(doc.template || "-")}</div>
                    <div class="checklist-list-docname">${this.escape(doc.name || "-")}</div>
                    <div style="margin-bottom:8px;">${issueBadge}</div>
                    <div class="checklist-list-meta">
                        <div><strong>${__("Status")}:</strong> ${this.escape(doc.status || "-")}</div>
                        <div><strong>${__("Department")}:</strong> ${this.escape(doc.department || "-")}</div>
                        <div><strong>${__("Assigned User")}:</strong> ${this.escape(doc.assigned_user || "-")}</div>
                        <div><strong>${__("Result")}:</strong> ${this.escape(doc.result_status || "Normal")}</div>
                    </div>
                </div>
            `);

            $item.on("click", () => this.load_doc(doc.name));
            $target.append($item);
        });
    }

    render_summary_list($target, rows, emptyText) {
        $target.empty();

        if (!rows.length) {
            $target.html(`<div class="empty-state">${emptyText}</div>`);
            return;
        }

        rows.forEach(row => {
            $target.append(`
                <div class="summary-list-item">
                    <div class="summary-list-title">${this.escape(row.label || "-")}</div>
                    <div class="summary-list-meta">
                        <div><strong>${__("Total")}:</strong> ${row.total || 0}</div>
                        <div><strong>${__("Completed")}:</strong> ${row.completed || 0}</div>
                        <div><strong>${__("Remaining")}:</strong> ${row.remaining || 0}</div>
                    </div>
                </div>
            `);
        });
    }

    async load_doc(docname) {
        try {
            const r = await frappe.call({
                method: "taj_core.checklist.api.get_checklist_answer",
                args: { docname }
            });

            this.doc = r.message;
            this.selectedDocname = docname;
            this.render_doc();

            this.render_mini_cards(
                this.$todayOpenMiniGrid,
                this.lastData?.today_open || [],
                __("No open tasks today."),
                "is-open"
            );

            this.render_mini_cards(
                this.$todayCompletedMiniGrid,
                this.lastData?.today_completed || [],
                __("No completed tasks today."),
                "is-completed"
            );

            this.render_doc_list(
                this.$searchResultsList,
                this.lastData?.search_results || [],
                __("No results found.")
            );
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

        this.$selectedWrapper.show();
        this.page.set_indicator(this.doc.status || "Draft", this.get_indicator_color(this.doc.status));

        const issueBadge = this.doc.has_issue
            ? `<span class="issue-badge is-issue">${__("Has Issue")}</span>`
            : `<span class="issue-badge is-normal">${__("Normal")}</span>`;

        this.$meta.html(`
            <div style="margin-bottom:12px;">${issueBadge}</div>
            <div class="selected-doc-meta-grid">
                <div class="meta-line"><strong>${__("Template")}:</strong> ${this.escape(this.doc.template || "-")}</div>
                <div class="meta-line"><strong>${__("Document")}:</strong> ${this.escape(this.doc.name || "-")}</div>
                <div class="meta-line"><strong>${__("Posting Date")}:</strong> ${this.escape(this.doc.posting_date || "-")}</div>
                <div class="meta-line"><strong>${__("Department")}:</strong> ${this.escape(this.doc.department || "-")}</div>
                <div class="meta-line"><strong>${__("Assigned User")}:</strong> ${this.escape(this.doc.assigned_user || "-")}</div>
                <div class="meta-line"><strong>${__("Status")}:</strong> ${this.escape(this.doc.status || "-")}</div>
                <div class="meta-line"><strong>${__("Result")}:</strong> ${this.escape(this.doc.result_status || "Normal")}</div>
            </div>
        `);

        const questions = this.doc?.questions || [];
        const answered = questions.filter(q => String(q.answer || "").trim()).length;

        this.$progress.html(`
            <div>
                <strong>${__("Progress")}:</strong>
                ${answered} / ${questions.length} ${__("answered")}
            </div>
        `);

        this.$body.empty();

        if (!questions.length) {
            this.$body.html(`<div class="empty-state">${__("No questions found.")}</div>`);
            return;
        }

        questions.forEach((row, index) => {
            const issueClass = row.has_issue ? "has-issue" : "";
            const issueLine = row.has_issue
                ? `<div style="margin-bottom:8px;"><span class="issue-badge is-issue">${__("Issue Answer")}</span></div>`
                : "";

            this.$body.append(`
                <div class="checklist-answer-readonly ${issueClass}">
                    ${issueLine}
                    <div class="checklist-question-title">
                        ${index + 1}- ${this.escape(row.question_text || row.question || "")}
                    </div>
                    <div class="readonly-answer-value">
                        <strong>${__("Answer")}:</strong> ${this.escape(row.answer || "-")}
                    </div>
                    ${row.issue_note ? `<div class="readonly-answer-value"><strong>${__("Issue Note")}:</strong> ${this.escape(row.issue_note)}</div>` : ""}
                </div>
            `);
        });

        this.$selectedWrapper.get(0).scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    }

    get_indicator_color(status) {
        if (status === "Completed") return "green";
        if (status === "In Progress") return "orange";
        if (status === "Auto Closed") return "darkgrey";
        if (status === "Expired") return "red";
        return "blue";
    }
}