frappe.pages["test2"].on_page_load = function (wrapper) {
    new ChecklistAnswerManagerPage(wrapper);
};

class ChecklistAnswerManagerPage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.doc = null;
        this.wall_mode = false;

        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Checklist Manager Dashboard"),
            single_column: true
        });

        this.render_layout();
        this.bind_events();
        this.load_initial_state();
    }

    render_layout() {
        $(this.page.body).html(`
            <div class="checklist-mgr-page">
                <!-- الهيدر مع الفلاتر -->
                <div class="mgr-header">
                    <div class="mgr-header-left">
                        <h1>${__("Checklist Manager Dashboard")}</h1>
                        <p>${__("Track daily progress, filter by template/date/user, and review results")}</p>
                    </div>
                    <div class="mgr-filters">
                        <div class="filter-control filter-template"></div>
                        <div class="filter-control filter-user"></div>
                        <div class="filter-control filter-date"></div>
                        <div class="filter-control filter-status"></div>
                        <button class="btn btn-primary btn-search">${__("Search")}</button>
                        <button class="btn btn-default wall-toggle">🖥️ ${__("Wall Mode")}</button>
                    </div>
                </div>

                <!-- بطاقات الملخص -->
                <div class="summary-cards">
                    <div class="summary-card">
                        <div class="card-icon new">📊</div>
                        <div class="card-content">
                            <div class="card-label">${__("Today Total")}</div>
                            <div class="card-value today-total">0</div>
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="card-icon open">⏳</div>
                        <div class="card-content">
                            <div class="card-label">${__("Today Open")}</div>
                            <div class="card-value today-open">0</div>
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="card-icon completed">✅</div>
                        <div class="card-content">
                            <div class="card-label">${__("Today Completed")}</div>
                            <div class="card-value today-completed">0</div>
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="card-icon team">⏱️</div>
                        <div class="card-content">
                            <div class="card-label">${__("Today Remaining")}</div>
                            <div class="card-value today-remaining">0</div>
                        </div>
                    </div>
                </div>

                <!-- لوحة المعلومات مع الرسم البياني -->
                <div class="dashboard-grid">
                    <div class="chart-card">
                        <div class="panel-title">${__("Completion Rate")}</div>
                        <div class="chart-container" id="completionChart"></div>
                    </div>
                    <div class="chart-card">
                        <div class="panel-title">${__("Quick Stats")}</div>
                        <div style="padding:20px; text-align:center;" id="quickStats"></div>
                    </div>
                </div>

                <!-- جداول البيانات -->
                <div class="tables-grid">
                    <div class="data-panel">
                        <div class="panel-title">${__("Today Open")}</div>
                        <div class="table-responsive">
                            <table class="data-table today-open-table">
                                <thead><tr><th>${__("Document")}</th><th>${__("Template")}</th><th>${__("User")}</th><th>${__("Status")}</th></tr></thead>
                                <tbody class="today-open-list"></tbody>
                            </table>
                        </div>
                    </div>
                    <div class="data-panel">
                        <div class="panel-title">${__("Today Completed")}</div>
                        <div class="table-responsive">
                            <table class="data-table today-completed-table">
                                <thead><tr><th>${__("Document")}</th><th>${__("Template")}</th><th>${__("User")}</th><th>${__("Status")}</th></tr></thead>
                                <tbody class="today-completed-list"></tbody>
                            </table>
                        </div>
                    </div>
                    <div class="data-panel">
                        <div class="panel-title">${__("Search Results")}</div>
                        <div class="table-responsive">
                            <table class="data-table search-results-table">
                                <thead><tr><th>${__("Document")}</th><th>${__("Template")}</th><th>${__("User")}</th><th>${__("Status")}</th></tr></thead>
                                <tbody class="search-results-list"></tbody>
                            </table>
                        </div>
                    </div>
                    <div class="data-panel">
                        <div class="panel-title">${__("By Template")}</div>
                        <div class="template-summary-list"></div>
                    </div>
                </div>

                <!-- ملخص الموظفين -->
                <div class="employee-summary">
                    <div class="panel-title">${__("By Employee")}</div>
                    <div class="employee-summary-list"></div>
                </div>

                <!-- تفاصيل المستند (تظهر عند النقر) -->
                <div class="selected-doc-wrapper" style="display:none;">
                    <div class="selected-doc-meta"></div>
                    <div class="selected-doc-progress"></div>
                    <div class="selected-doc-body"></div>
                </div>
            </div>
        `);

        // عناصر
        this.$todayTotal = $(this.page.body).find(".today-total");
        this.$todayOpen = $(this.page.body).find(".today-open");
        this.$todayCompleted = $(this.page.body).find(".today-completed");
        this.$todayRemaining = $(this.page.body).find(".today-remaining");

        this.$todayOpenList = $(this.page.body).find(".today-open-list");
        this.$todayCompletedList = $(this.page.body).find(".today-completed-list");
        this.$searchResultsList = $(this.page.body).find(".search-results-list");
        this.$templateSummaryList = $(this.page.body).find(".template-summary-list");
        this.$employeeSummaryList = $(this.page.body).find(".employee-summary-list");

        this.$meta = $(this.page.body).find(".selected-doc-meta");
        this.$progress = $(this.page.body).find(".selected-doc-progress");
        this.$body = $(this.page.body).find(".selected-doc-body");
        this.$selectedWrapper = $(this.page.body).find(".selected-doc-wrapper");
        this.$wallToggle = $(this.page.body).find(".wall-toggle");

        // عناصر تحكم الفلاتر
        this.template_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-template").get(0),
            df: { label: __("Template"), fieldname: "template", fieldtype: "Link", options: "Checklist Question Template" },
            render_input: true
        });
        this.user_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-user").get(0),
            df: { label: __("User"), fieldname: "assigned_user", fieldtype: "Link", options: "User" },
            render_input: true
        });
        this.date_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-date").get(0),
            df: { label: __("Date"), fieldname: "search_date", fieldtype: "Date", default: frappe.datetime.get_today() },
            render_input: true
        });
        this.status_control = frappe.ui.form.make_control({
            parent: $(this.page.body).find(".filter-status").get(0),
            df: { label: __("Status"), fieldname: "status", fieldtype: "Select", options: "\nAll\nOpen\nDraft\nIn Progress\nCompleted\nAuto Closed" },
            render_input: true
        });

        this.date_control.set_value(frappe.datetime.get_today());
        this.status_control.set_value("All");
    }

    bind_events() {
        $(this.page.body).find(".btn-search").on("click", () => this.load_dashboard());
        this.$wallToggle.on("click", () => this.toggle_wall_mode());
    }

    toggle_wall_mode() {
        this.wall_mode = !this.wall_mode;
        $(this.page.body).find(".checklist-mgr-page").toggleClass("wall-mode", this.wall_mode);
        this.$wallToggle.text(this.wall_mode ? `📋 ${__('Normal Mode')}` : `🖥️ ${__('Wall Mode')}`);
    }

    async load_initial_state() {
        await this.load_dashboard();
    }

    async load_dashboard() {
        const r = await frappe.call({
            method: "taj_core.checklist.api.get_manager_dashboard_data",
            args: {
                search_date: this.date_control.get_value(),
                template: this.template_control.get_value(),
                assigned_user: this.user_control.get_value(),
                status: this.status_control.get_value()
            }
        });

        const data = r.message || {};
        const summary = data.summary || {};

        this.$todayTotal.text(summary.today_total || 0);
        this.$todayOpen.text(summary.today_open || 0);
        this.$todayCompleted.text(summary.today_completed || 0);
        this.$todayRemaining.text(summary.today_remaining || 0);

        this.render_table_rows(this.$todayOpenList, data.today_open || []);
        this.render_table_rows(this.$todayCompletedList, data.today_completed || []);
        this.render_table_rows(this.$searchResultsList, data.search_results || []);
        this.render_template_summary(data.template_summary || []);
        this.render_employee_summary(data.employee_summary || []);

        this.render_chart(summary);
        this.render_quick_stats(summary);
    }

    render_table_rows($tbody, docs) {
        $tbody.empty();
        docs.forEach(doc => {
            const row = $(`
                <tr data-docname="${doc.name}">
                    <td>${frappe.utils.escape_html(doc.name)}</td>
                    <td>${frappe.utils.escape_html(doc.template || "-")}</td>
                    <td>${frappe.utils.escape_html(doc.assigned_user || "-")}</td>
                    <td>${frappe.utils.escape_html(doc.status || "-")}</td>
                </tr>
            `);
            row.on("click", () => this.load_doc(doc.name));
            $tbody.append(row);
        });
    }

    render_template_summary(templates) {
        this.$templateSummaryList.empty();
        if (!templates.length) {
            this.$templateSummaryList.html(`<div class="empty-state">${__("No data")}</div>`);
            return;
        }
        templates.forEach(t => {
            this.$templateSummaryList.append(`
                <div class="employee-item">
                    <div class="employee-name">${frappe.utils.escape_html(t.label)}</div>
                    <div class="employee-stats">
                        <span>${__("Total")}: ${t.total}</span>
                        <span>${__("Completed")}: ${t.completed}</span>
                        <span>${__("Remaining")}: ${t.remaining}</span>
                    </div>
                </div>
            `);
        });
    }

    render_employee_summary(employees) {
        this.$employeeSummaryList.empty();
        if (!employees.length) {
            this.$employeeSummaryList.html(`<div class="empty-state">${__("No data")}</div>`);
            return;
        }
        employees.forEach(e => {
            const percent = e.total ? Math.round((e.completed / e.total) * 100) : 0;
            this.$employeeSummaryList.append(`
                <div class="employee-item">
                    <div class="employee-name">${frappe.utils.escape_html(e.label)}</div>
                    <div class="employee-stats">
                        <div class="progress-micro">
                            <div class="progress-micro-fill" style="width: ${percent}%;"></div>
                        </div>
                        <div class="employee-counts">
                            <span>${e.completed}/${e.total}</span>
                            <span>${__("Remaining")}: ${e.remaining}</span>
                        </div>
                    </div>
                </div>
            `);
        });
    }

    render_chart(summary) {
        const total = summary.today_total || 0;
        const completed = summary.today_completed || 0;
        const remaining = summary.today_remaining || 0;

        if (total === 0) {
            $(this.page.body).find("#completionChart").html(`<div class="empty-state">${__("No data for chart")}</div>`);
            return;
        }

        const chart = new frappe.Chart("#completionChart", {
            type: "percentage",
            data: {
                labels: [__("Completed"), __("Remaining")],
                datasets: [
                    { values: [completed, remaining] }
                ]
            },
            colors: ["#16a34a", "#dc2626"],
            height: 180,
            axisMode: "none"
        });
    }

    render_quick_stats(summary) {
        const total = summary.today_total || 0;
        const open = summary.today_open || 0;
        const completed = summary.today_completed || 0;
        const remaining = summary.today_remaining || 0;
        const completionRate = total ? Math.round((completed / total) * 100) : 0;

        const html = `
            <div style="font-size: 48px; font-weight:700; color:var(--primary-color);">${completionRate}%</div>
            <div style="margin-top:8px;">${__("Completion Rate")}</div>
            <hr style="margin:16px 0;">
            <div style="display:flex; justify-content:space-around;">
                <div><span style="font-weight:600;">${open}</span> ${__("Open")}</div>
                <div><span style="font-weight:600;">${remaining}</span> ${__("Remaining")}</div>
            </div>
        `;
        $(this.page.body).find("#quickStats").html(html);
    }

    async load_doc(docname) {
        const r = await frappe.call({
            method: "taj_core.checklist.api.get_checklist_answer",
            args: { docname }
        });

        this.doc = r.message;
        this.render_doc_details();
    }

    render_doc_details() {
        if (!this.doc) return;

        this.$selectedWrapper.show();
        this.page.set_indicator(this.doc.status || "Draft", this.get_indicator_color(this.doc.status));

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

        const questions = this.doc?.questions || [];
        const answered = questions.filter(q => String(q.answer || "").trim()).length;
        this.$progress.html(`
            <div><strong>${__("Progress")}:</strong> ${answered} / ${questions.length} ${__("answered")}</div>
        `);

        this.$body.empty();
        if (!questions.length) {
            this.$body.html(`<div class="empty-state">${__("No questions found.")}</div>`);
        } else {
            questions.forEach((row, index) => {
                this.$body.append(`
                    <div class="question-item readonly">
                        <div class="question-text">${index + 1}- ${frappe.utils.escape_html(row.question_text || row.question || "")}</div>
                        <div><strong>${__("Answer")}:</strong> ${frappe.utils.escape_html(row.answer || "-")}</div>
                    </div>
                `);
            });
        }
    }

    get_indicator_color(status) {
        const colors = { "Completed": "green", "In Progress": "orange", "Auto Closed": "gray", "Expired": "red" };
        return colors[status] || "blue";
    }
}