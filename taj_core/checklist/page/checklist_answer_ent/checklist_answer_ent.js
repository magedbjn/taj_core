frappe.pages["checklist-answer-ent"].on_page_load = function (wrapper) {
    new ChecklistAnswerEntryPage(wrapper);
};

class ChecklistAnswerEntryPage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.doc = null;
        this.row_controls = {};
        this.pending_changes = {};
        this.save_timer = null;
        this.is_saving = false;
        this.last_save_promise = Promise.resolve();
        this.activeTab = "my-new";
        this.dashboardData = null;
        this.activeSummaryView = null;

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Checklist User Screen"),
            single_column: true
        });

        $(this.page.wrapper).find(".page-head").remove();

        this.render_layout();
        this.bind_events();
        this.load_initial_state();
    }

    render_layout() {
        $(this.page.body).html(`
            <div class="checklist-entry-page">
                <div class="checklist-header">
                    <div class="checklist-header-left">
                        <div class="checklist-page-title">${__("My Checklist Tasks")}</div>
                        <div class="checklist-page-subtitle">${__("Simple screen for my tasks, team view, and search results")}</div>
                    </div>

                    <div class="checklist-header-right">
                        <div class="history-date-control"></div>
                        <button class="btn btn-primary btn-search-history">${__("Search")}</button>
                    </div>
                </div>

                <div class="checklist-summary-row">
                    <div class="summary-card summary-card-clickable is-blue" data-summary-view="my-new">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-blue">
                                <svg class="summary-icon-svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 5V19"></path>
                                    <path d="M5 12H19"></path>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("My New")}</div>
                                <div class="summary-value my-new-count">0</div>
                            </div>
                        </div>
                    </div>

                    <div class="summary-card summary-card-clickable is-orange" data-summary-view="my-open">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-orange">
                                <svg class="summary-icon-svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 6V12L16 14"></path>
                                    <circle cx="12" cy="12" r="7.5"></circle>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("My Open")}</div>
                                <div class="summary-value my-open-count">0</div>
                            </div>
                        </div>
                    </div>

                    <div class="summary-card summary-card-clickable is-rose" data-summary-view="team">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-rose">
                                <svg class="summary-icon-svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M7 12H17"></path>
                                    <path d="M12 7V17"></path>
                                    <circle cx="12" cy="12" r="8"></circle>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Team Open")}</div>
                                <div class="summary-value team-open-count">0</div>
                            </div>
                        </div>
                    </div>

                    <div class="summary-card summary-card-clickable is-green" data-summary-view="completed">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-green">
                                <svg class="summary-icon-svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M7 12.5L10.2 15.7L17.5 8.5"></path>
                                    <circle cx="12" cy="12" r="8"></circle>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Completed")}</div>
                                <div class="summary-value completed-count">0</div>
                            </div>
                        </div>
                    </div>

                    <div class="summary-card summary-card-clickable is-purple" data-summary-view="today-has-issue">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-purple">
                                <svg class="summary-icon-svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 8V12.5"></path>
                                    <path d="M12 16.5H12.01"></path>
                                    <path d="M10.29 3.86L1.82 18A2 2 0 0 0 3.53 21H20.47A2 2 0 0 0 22.18 18L13.71 3.86A2 2 0 0 0 10.29 3.86Z"></path>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Today Has Issue")}</div>
                                <div class="summary-value today-has-issue-count">0</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="tab-strip">
                    <button class="tab-btn is-active" data-tab="my-new">${__("My New")}</button>
                    <button class="tab-btn" data-tab="my-open">${__("My Open")}</button>
                    <button class="tab-btn" data-tab="team">${__("Team Open")}</button>
                    <button class="tab-btn" data-tab="search">${__("Search")}</button>
                </div>

                <div class="tab-panel is-active" data-tab="my-new">
                    <div class="checklist-panel">
                        <div class="panel-title">${__("My New Tasks")}</div>
                        <div class="my-new-list"></div>
                    </div>
                </div>

                <div class="tab-panel" data-tab="my-open">
                    <div class="checklist-panel">
                        <div class="panel-title">${__("My Open Tasks")}</div>
                        <div class="my-open-list"></div>
                    </div>
                </div>

                <div class="tab-panel" data-tab="team">
                    <div class="checklist-panel">
                        <div class="panel-title">${__("Team Open Tasks")}</div>
                        <div class="team-open-list"></div>
                    </div>
                </div>

                <div class="tab-panel" data-tab="search">
                    <div class="checklist-panel">
                        <div class="panel-title search-results-title">${__("Search Results")}</div>
                        <div class="history-results-list"></div>
                    </div>
                </div>

                <div class="selected-doc-wrapper" style="display:none;">
                    <div class="selected-doc-meta"></div>
                    <div class="selected-doc-progress"></div>
                    <div class="selected-doc-body"></div>
                    <div class="selected-doc-actions"></div>
                </div>
            </div>
        `);

        this.$myNewList = $(this.page.body).find(".my-new-list");
        this.$myOpenList = $(this.page.body).find(".my-open-list");
        this.$teamOpenList = $(this.page.body).find(".team-open-list");
        this.$historyList = $(this.page.body).find(".history-results-list");

        this.$myNewCount = $(this.page.body).find(".my-new-count");
        this.$myOpenCount = $(this.page.body).find(".my-open-count");
        this.$teamOpenCount = $(this.page.body).find(".team-open-count");
        this.$completedCount = $(this.page.body).find(".completed-count");
        this.$todayHasIssueCount = $(this.page.body).find(".today-has-issue-count");

        this.$tabButtons = $(this.page.body).find(".tab-btn");
        this.$tabPanels = $(this.page.body).find(".tab-panel");
        this.$summaryCards = $(this.page.body).find(".summary-card-clickable");
        this.$searchResultsTitle = $(this.page.body).find(".search-results-title");

        this.$meta = $(this.page.body).find(".selected-doc-meta");
        this.$progress = $(this.page.body).find(".selected-doc-progress");
        this.$body = $(this.page.body).find(".selected-doc-body");
        this.$actions = $(this.page.body).find(".selected-doc-actions");
        this.$selectedWrapper = $(this.page.body).find(".selected-doc-wrapper");

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
        $(this.page.body).find(".btn-search-history").on("click", () => {
            this.activeSummaryView = null;
            this.$summaryCards.removeClass("is-active");
            this.set_active_tab("search");
            this.load_dashboard();
        });

        this.$tabButtons.on("click", (e) => {
            this.set_active_tab($(e.currentTarget).attr("data-tab"));
        });

        this.$summaryCards.on("click", (e) => {
            const view = $(e.currentTarget).attr("data-summary-view");
            this.apply_summary_view(view);
        });
    }

    set_active_tab(tabName) {
        this.activeTab = tabName;
        this.$tabButtons.removeClass("is-active");
        this.$tabPanels.removeClass("is-active");

        this.$tabButtons.filter(`[data-tab="${tabName}"]`).addClass("is-active");
        this.$tabPanels.filter(`[data-tab="${tabName}"]`).addClass("is-active");
    }

    apply_summary_view(viewName) {
        this.activeSummaryView = viewName;
        this.$summaryCards.removeClass("is-active");
        this.$summaryCards.filter(`[data-summary-view="${viewName}"]`).addClass("is-active");

        if (viewName === "my-new") {
            this.set_active_tab("my-new");
            return;
        }

        if (viewName === "my-open") {
            this.set_active_tab("my-open");
            return;
        }

        if (viewName === "team") {
            this.set_active_tab("team");
            return;
        }

        if (viewName === "completed") {
            this.set_active_tab("search");
            this.render_completed_only_results();
            return;
        }

        if (viewName === "today-has-issue") {
            this.set_active_tab("search");
            this.render_today_issue_results();
        }
    }

    render_completed_only_results() {
        if (!this.dashboardData) return;

        const docs = (this.dashboardData.history_results || []).filter(
            d => d.docstatus === 1 && d.status === "Completed"
        );

        this.$searchResultsTitle.text(__("Completed Results"));
        this.render_list(this.$historyList, docs, __("No completed results for selected date."));
    }

    render_today_issue_results() {
        if (!this.dashboardData) return;

        const docs = this.dashboardData.today_has_issue || [];
        this.$searchResultsTitle.text(__("Today Has Issue"));
        this.render_list(this.$historyList, docs, __("No issue results for today."));
    }

    async load_initial_state() {
        await this.load_dashboard();

        const opts = frappe.route_options || {};
        if (opts.checklist_answer) {
            await this.load_doc(opts.checklist_answer);
        }
    }

    async load_dashboard() {
        const search_date = this.history_date_control.get_value();

        const r = await frappe.call({
            method: "taj_core.checklist.api.get_user_dashboard_data",
            args: { search_date }
        });

        const data = r.message || {};
        this.dashboardData = data;

        const summary = data.summary || {};

        this.$myNewCount.text(summary.my_new_count || 0);
        this.$myOpenCount.text(summary.my_open_count || 0);
        this.$teamOpenCount.text(summary.team_open_count || 0);
        this.$completedCount.text(summary.completed_count || 0);
        this.$todayHasIssueCount.text(summary.today_has_issue_count || 0);

        this.render_list(this.$myNewList, data.my_new || [], __("No new tasks."));
        this.render_list(this.$myOpenList, data.my_open || [], __("No open tasks."));
        this.render_list(this.$teamOpenList, data.team_open || [], __("No team open tasks."));

        this.$searchResultsTitle.text(__("Search Results"));
        this.render_list(this.$historyList, data.history_results || [], __("No results for selected date."));

        if (this.activeSummaryView === "completed") {
            this.render_completed_only_results();
        } else if (this.activeSummaryView === "today-has-issue") {
            this.render_today_issue_results();
        }
    }

    render_list($target, docs, emptyText) {
        $target.empty();

        if (!docs.length) {
            $target.html(`<div class="empty-state">${emptyText}</div>`);
            return;
        }

        docs.forEach(doc => {
            const issueClass = doc.has_issue ? "has-issue" : "";
            const issueBadge = doc.has_issue
                ? `<span class="issue-badge is-issue">${__("Has Issue")}</span>`
                : `<span class="issue-badge is-normal">${__("Normal")}</span>`;

            const $item = $(`
                <div class="checklist-list-item ${issueClass}">
                    <div class="checklist-list-template">${frappe.utils.escape_html(doc.template || "-")}</div>
                    <div class="checklist-list-docname">${frappe.utils.escape_html(doc.name || "-")}</div>
                    <div>${issueBadge}</div>
                    <div class="checklist-list-meta">
                        <div><strong>${__("Status")}:</strong> ${frappe.utils.escape_html(doc.status || "-")}</div>
                        <div><strong>${__("Department")}:</strong> ${frappe.utils.escape_html(doc.department || "-")}</div>
                        <div><strong>${__("Assigned User")}:</strong> ${frappe.utils.escape_html(doc.assigned_user || "-")}</div>
                    </div>
                </div>
            `);

            $item.on("click", () => this.load_doc(doc.name));
            $target.append($item);
        });
    }

    async load_doc(docname) {
        const r = await frappe.call({
            method: "taj_core.checklist.api.get_checklist_answer",
            args: { docname }
        });

        this.doc = r.message;
        this.render_doc();
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
                <div class="meta-line"><strong>${__("Template")}:</strong> ${this.doc.template || "-"}</div>
                <div class="meta-line"><strong>${__("Document")}:</strong> ${this.doc.name}</div>
                <div class="meta-line"><strong>${__("Posting Date")}:</strong> ${this.doc.posting_date || "-"}</div>
                <div class="meta-line"><strong>${__("Department")}:</strong> ${this.doc.department || "-"}</div>
                <div class="meta-line"><strong>${__("Assigned User")}:</strong> ${this.doc.assigned_user || "-"}</div>
                <div class="meta-line"><strong>${__("Status")}:</strong> ${this.doc.status || "-"}</div>
                <div class="meta-line"><strong>${__("Result")}:</strong> ${this.doc.result_status || "Normal"}</div>
            </div>
        `);

        this.render_progress();
        this.render_questions();
        this.render_actions();

        this.$selectedWrapper.get(0).scrollIntoView({ behavior: "smooth", block: "start" });
    }

    render_progress() {
        const questions = this.doc?.questions || [];
        const answered = questions.filter(q => String(q.answer || "").trim()).length;

        this.$progress.html(`
            <div>
                <strong>${__("Progress")}:</strong>
                ${answered} / ${questions.length} ${__("answered")}
            </div>
        `);
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
                    ? `<div style="margin-bottom:8px;"><span class="issue-badge is-issue">${__("Issue Answer")}</span></div>`
                    : "";

                this.$body.append(`
                    <div class="checklist-answer-readonly ${issueClass}">
                        ${issueLine}
                        <div class="checklist-question-title">
                            ${index + 1}- ${frappe.utils.escape_html(row.question_text || row.question || "")}
                        </div>
                        <div class="readonly-answer-value">
                            <strong>${__("Answer")}:</strong> ${frappe.utils.escape_html(row.answer || "-")}
                        </div>
                        ${row.issue_note ? `<div class="readonly-answer-value"><strong>${__("Issue Note")}:</strong> ${frappe.utils.escape_html(row.issue_note)}</div>` : ""}
                    </div>
                `);
            });
            return;
        }

        questions.forEach((row, index) => {
            const $card = $(`
                <div class="checklist-question-card">
                    <div class="checklist-question-title">
                        ${index + 1}- ${frappe.utils.escape_html(row.question_text || row.question || "")}
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
    }

    get_df_for_row(row) {
        const base_df = {
            label: __("Answer"),
            fieldname: `answer_${row.row_name}`,
            reqd: 1,
            change: () => {
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
            return { ...base_df, fieldtype: "Select", options: "\n" + (row.answer_options || "") };
        }

        return { ...base_df, fieldtype: "Data" };
    }

    schedule_save(row_name, answer) {
        if (!this.doc?.name || !this.doc.is_editable) return;

        this.pending_changes[row_name] = answer;

        if (this.save_timer) {
            clearTimeout(this.save_timer);
        }

        this.save_timer = setTimeout(() => {
            this.last_save_promise = this.last_save_promise.then(() => this.flush_pending_saves());
        }, 300);
    }

    async flush_pending_saves() {
        if (!this.doc?.name || !this.doc.is_editable) return;
        if (this.is_saving) return;

        const entries = Object.entries(this.pending_changes);
        if (!entries.length) return;

        this.is_saving = true;

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
            this.render_progress();
        } catch (e) {
            payload.forEach(item => {
                this.pending_changes[item.row_name] = item.answer;
            });
            throw e;
        } finally {
            this.is_saving = false;
        }

        if (Object.keys(this.pending_changes).length) {
            await this.flush_pending_saves();
        }
    }

    async submit_doc() {
        if (!this.doc?.name || !this.doc.is_editable) {
            frappe.msgprint(__("This checklist cannot be submitted from here."));
            return;
        }

        if (this.save_timer) {
            clearTimeout(this.save_timer);
            this.save_timer = null;
        }

        await this.last_save_promise;
        await this.flush_pending_saves();

        const r = await frappe.call({
            method: "taj_core.checklist.api.submit_checklist_answer",
            args: { docname: this.doc.name }
        });

        frappe.show_alert({
            message: __("Checklist submitted successfully."),
            indicator: "green"
        });

        await this.load_dashboard();
        await this.load_doc(r.message.name);
    }

    get_indicator_color(status) {
        if (status === "Completed") return "green";
        if (status === "In Progress") return "orange";
        if (status === "Auto Closed") return "gray";
        if (status === "Expired") return "red";
        return "blue";
    }
}