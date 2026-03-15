frappe.pages["test1"].on_page_load = function (wrapper) {
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
        this.current_tab = "my_new";

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Checklist User Screen"),
            single_column: true
        });

        this.render_layout();
        this.bind_events();
        this.load_initial_state();
    }

    render_layout() {
        $(this.page.body).html(`
            <div class="checklist-user-page">
                <!-- الهيدر -->
                <div class="user-header">
                    <div class="user-header-left">
                        <h1>${__("My Checklist Tasks")}</h1>
                        <p>${__("New tasks, open tasks, team tasks, and previous results")}</p>
                    </div>
                    <div class="user-header-right">
                        <div class="history-date-control" style="width:200px;"></div>
                        <button class="btn btn-primary btn-search-history">${__("Search")}</button>
                    </div>
                </div>

                <!-- بطاقات الملخص -->
                <div class="summary-cards">
                    <div class="summary-card">
                        <div class="card-icon new">📋</div>
                        <div class="card-content">
                            <div class="card-label">${__("My New")}</div>
                            <div class="card-value my-new-count">0</div>
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="card-icon open">⏳</div>
                        <div class="card-content">
                            <div class="card-label">${__("My Open")}</div>
                            <div class="card-value my-open-count">0</div>
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="card-icon team">👥</div>
                        <div class="card-content">
                            <div class="card-label">${__("Open / Incomplete")}</div>
                            <div class="card-value summary-danger team-open-count">0</div>
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="card-icon completed">✅</div>
                        <div class="card-content">
                            <div class="card-label">${__("Completed")}</div>
                            <div class="card-value summary-success completed-count">0</div>
                        </div>
                    </div>
                </div>

                <!-- تبويبات -->
                <div class="user-tabs">
                    <button class="tab-btn active" data-tab="my_new">${__("My New Tasks")}</button>
                    <button class="tab-btn" data-tab="my_open">${__("My Open Tasks")}</button>
                    <button class="tab-btn" data-tab="team_open">${__("Team Open Tasks")}</button>
                </div>

                <!-- المحتوى الرئيسي + لوحة جانبية -->
                <div class="user-main-layout">
                    <div class="user-content">
                        <!-- أقسام التبويبات -->
                        <div class="tab-pane active" data-pane="my_new">
                            <div class="my-new-list tasks-list"></div>
                        </div>
                        <div class="tab-pane" data-pane="my_open">
                            <div class="my-open-list tasks-list"></div>
                        </div>
                        <div class="tab-pane" data-pane="team_open">
                            <div class="team-open-list tasks-list"></div>
                        </div>
                    </div>

                    <!-- اللوحة الجانبية -->
                    <div class="side-panel" id="sidePanel">
                        <div class="panel-header">
                            <h3>${__("Task Details")}</h3>
                            <button class="close-panel">&times;</button>
                        </div>
                        <div class="selected-doc-meta"></div>
                        <div class="selected-doc-progress"></div>
                        <div class="selected-doc-body"></div>
                        <div class="selected-doc-actions"></div>
                    </div>
                </div>
            </div>
        `);

        // عناصر
        this.$myNewList = $(this.page.body).find(".my-new-list");
        this.$myOpenList = $(this.page.body).find(".my-open-list");
        this.$teamOpenList = $(this.page.body).find(".team-open-list");

        this.$myNewCount = $(this.page.body).find(".my-new-count");
        this.$myOpenCount = $(this.page.body).find(".my-open-count");
        this.$teamOpenCount = $(this.page.body).find(".team-open-count");
        this.$completedCount = $(this.page.body).find(".completed-count");

        this.$meta = $(this.page.body).find(".selected-doc-meta");
        this.$progress = $(this.page.body).find(".selected-doc-progress");
        this.$body = $(this.page.body).find(".selected-doc-body");
        this.$actions = $(this.page.body).find(".selected-doc-actions");
        this.$sidePanel = $(this.page.body).find("#sidePanel");
        this.$closePanel = $(this.page.body).find(".close-panel");

        // عنصر تحكم التاريخ
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
        this.history_date_control.set_value(frappe.datetime.get_today());
    }

    bind_events() {
        // بحث
        $(this.page.body).find(".btn-search-history").on("click", () => this.load_dashboard());

        // تبويبات
        $(this.page.body).find(".tab-btn").on("click", (e) => {
            const tab = $(e.currentTarget).data("tab");
            this.switch_tab(tab);
        });

        // إغلاق اللوحة الجانبية
        this.$closePanel.on("click", () => this.close_side_panel());
    }

    switch_tab(tab) {
        this.current_tab = tab;
        $(this.page.body).find(".tab-btn").removeClass("active");
        $(this.page.body).find(`.tab-btn[data-tab="${tab}"]`).addClass("active");
        $(this.page.body).find(".tab-pane").removeClass("active");
        $(this.page.body).find(`.tab-pane[data-pane="${tab}"]`).addClass("active");
    }

    close_side_panel() {
        this.$sidePanel.removeClass("open");
        this.doc = null;
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
        const summary = data.summary || {};

        this.$myNewCount.text(summary.my_new_count || 0);
        this.$myOpenCount.text(summary.my_open_count || 0);
        this.$teamOpenCount.text(summary.team_open_count || 0);
        this.$completedCount.text(summary.completed_count || 0);

        this.render_list(this.$myNewList, data.my_new || [], __("No new tasks."));
        this.render_list(this.$myOpenList, data.my_open || [], __("No open tasks."));
        this.render_list(this.$teamOpenList, data.team_open || [], __("No team open tasks."));
    }

    render_list($target, docs, emptyText) {
        $target.empty();

        if (!docs.length) {
            $target.html(`<div class="empty-state">${emptyText}</div>`);
            return;
        }

        docs.forEach(doc => {
            const statusClass = {
                "Open": "badge-open",
                "In Progress": "badge-in-progress",
                "Completed": "badge-completed"
            }[doc.status] || "";

            const $item = $(`
                <div class="task-card" data-docname="${doc.name}">
                    <div class="task-title">
                        <span>${frappe.utils.escape_html(doc.name)}</span>
                        <span class="task-badge ${statusClass}">${frappe.utils.escape_html(doc.status || "-")}</span>
                    </div>
                    <div class="task-meta">
                        <span>📋 ${frappe.utils.escape_html(doc.template || "-")}</span>
                        <span>🏢 ${frappe.utils.escape_html(doc.department || "-")}</span>
                        <span>👤 ${frappe.utils.escape_html(doc.assigned_user || "-")}</span>
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
        this.$sidePanel.addClass("open");
    }

    render_doc() {
        if (!this.doc) return;

        this.page.set_indicator(this.doc.status || "Draft", this.get_indicator_color(this.doc.status));

        // بيانات تعريفية
        this.$meta.html(`
            <div class="doc-meta-grid">
                <div><strong>${__("Document")}:</strong> ${this.doc.name}</div>
                <div><strong>${__("Template")}:</strong> ${this.doc.template || "-"}</div>
                <div><strong>${__("Posting Date")}:</strong> ${this.doc.posting_date || "-"}</div>
                <div><strong>${__("Department")}:</strong> ${this.doc.department || "-"}</div>
                <div><strong>${__("Assigned User")}:</strong> ${this.doc.assigned_user || "-"}</div>
                <div><strong>${__("Status")}:</strong> ${this.doc.status || "-"}</div>
            </div>
        `);

        this.render_progress();
        this.render_questions();
        this.render_actions();
    }

    render_progress() {
        const questions = this.doc?.questions || [];
        const answered = questions.filter(q => String(q.answer || "").trim()).length;
        const percent = questions.length ? Math.round((answered / questions.length) * 100) : 0;

        this.$progress.html(`
            <div class="progress-section">
                <div><strong>${__("Progress")}:</strong> ${answered} / ${questions.length} ${__("answered")}</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${percent}%;"></div>
                </div>
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
                this.$body.append(`
                    <div class="question-item readonly">
                        <div class="question-text">${index + 1}- ${frappe.utils.escape_html(row.question_text || row.question || "")}</div>
                        <div><strong>${__("Answer")}:</strong> ${frappe.utils.escape_html(row.answer || "-")}</div>
                    </div>
                `);
            });
            return;
        }

        questions.forEach((row, index) => {
            const $card = $(`
                <div class="question-item">
                    <div class="question-text">${index + 1}- ${frappe.utils.escape_html(row.question_text || row.question || "")}</div>
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
            <div class="actions">
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

        if (this.save_timer) clearTimeout(this.save_timer);
        this.save_timer = setTimeout(() => {
            this.last_save_promise = this.last_save_promise.then(() => this.flush_pending_saves());
        }, 300);
    }

    async flush_pending_saves() {
        if (!this.doc?.name || !this.doc.is_editable || this.is_saving) return;

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
            frappe.show_alert({ message: __("Saved"), indicator: "green" }, 2);
        } catch (e) {
            payload.forEach(item => this.pending_changes[item.row_name] = item.answer);
            frappe.show_alert({ message: __("Save failed"), indicator: "red" });
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

        frappe.show_alert({ message: __("Checklist submitted successfully."), indicator: "green" });
        await this.load_dashboard();
        await this.load_doc(r.message.name);
    }

    get_indicator_color(status) {
        const colors = { "Completed": "green", "In Progress": "orange", "Auto Closed": "gray", "Expired": "red" };
        return colors[status] || "blue";
    }
}