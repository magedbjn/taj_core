function setup_checklist_fullscreen(wrapper) {
    $(wrapper).addClass("checklist-page-fullscreen");
    $("body").addClass("checklist-fullscreen-mode");

    if (!window.__checklist_fullscreen_route_guard_added) {
        window.__checklist_fullscreen_route_guard_added = true;

        const routeChangeHandler = () => {
            const route = frappe.get_route ? frappe.get_route() : [];
            const current_page = route && route.length ? route[0] : "";

            if (!["checklist-user", "checklist-admin"].includes(current_page)) {
                $("body").removeClass("checklist-fullscreen-mode");
                $("body").removeClass("checklist-drawer-open");
            }
        };

        window.__checklist_route_handler = routeChangeHandler;
        if (frappe.router && frappe.router.on) {
            frappe.router.on("change", routeChangeHandler);
        }
    }
}

frappe.pages["checklist-admin"].on_page_load = function (wrapper) {
    const page = new ChecklistAnswerManagerPage(wrapper);
    wrapper.page_instance = page;
};

frappe.pages["checklist-admin"].on_page_unload = function (wrapper) {
    if (wrapper.page_instance && wrapper.page_instance.destroy) {
        wrapper.page_instance.destroy();
    }
};

class ChecklistAnswerManagerPage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.doc = null;
        this.lastData = null;
        this.selectedDocname = null;
        this.activeGroup = "today_open";

        this.autoRefreshTimer = null;
        this.autoRefreshMinutes = 10;
        this.isLoading = false;
        this.lastFocusedElement = null;

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

    destroy() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }

        $(document).off(".checklist_admin_drawer");
        $(this.page.body).off(".checklist_mgr");

        $("body").removeClass("checklist-drawer-open");
        $("body").removeClass("checklist-fullscreen-mode");

        if (this.wrapper.page_instance === this) {
            this.wrapper.page_instance = null;
        }
    }

    escape(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }

    get_refresh_interval_ms() {
        const minutes = parseInt(this.autoRefreshMinutes, 10);
        return (Number.isFinite(minutes) && minutes > 0 ? minutes : 10) * 60 * 1000;
    }

    show_loading($target, show = true) {
        if (!$target || !$target.length) return;

        if (show) {
            $target.addClass("btn-loading").prop("disabled", true);
            if (!$target.find(".loading-spinner").length) {
                $target.append('<span class="loading-spinner" aria-hidden="true"></span>');
            }
        } else {
            $target.removeClass("btn-loading").prop("disabled", false);
            $target.find(".loading-spinner").remove();
        }
    }

    log_client_error(title, error) {
        console.error(title, error);
        try {
            if (typeof frappe.log_error === "function") {
                frappe.log_error({
                    title,
                    message: error && error.stack ? error.stack : String(error || "")
                });
            }
        } catch (logErr) {
            console.error("log_client_error failed", logErr);
        }
    }

    render_layout() {
        $(this.page.body).html(`
            <div class="checklist-mgr-page container-fluid px-2 px-md-3">
                <div class="card shadow-sm border-0 mb-3">
                    <div class="card-body py-3">
                        <div class="d-flex flex-column">
                            <div class="d-flex flex-column flex-xl-row justify-content-between align-items-xl-start mb-3">
                                <div class="mgr-header-left flex-grow-1 mb-3 mb-xl-0">
                                    <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-start">
                                        <div class="mb-3 mb-md-0">
                                            <div class="mgr-page-title">${__("Checklist Manager Dashboard")}</div>
                                            <div class="mgr-page-subtitle">${__("Select a group, then open any card to view answers in the right drawer")}</div>
                                        </div>

                                        <div class="auto-refresh-control auto-refresh-control-header ml-md-3">
                                            <label class="auto-refresh-label mb-0 mr-2" for="auto-refresh-select">${__("Auto Refresh")}</label>
                                            <select id="auto-refresh-select" class="form-control form-control-sm auto-refresh-select" aria-label="${__("Auto Refresh Interval")}">
                                                <option value="5">5 Minutes</option>
                                                <option value="10" selected>10 Minutes</option>
                                                <option value="20">20 Minutes</option>
                                                <option value="30">30 Minutes</option>
                                                <option value="60">1 Hour</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>

                                <button class="btn btn-light btn-mobile-filters" type="button" aria-label="${__("Toggle Filters")}">
                                    <span class="mobile-filter-icon">☰</span>
                                    <span>${__("Filters")}</span>
                                </button>
                            </div>

                            <div class="mgr-filters" role="region" aria-label="${__("Search Filters")}">
                                <div class="filter-control filter-template"></div>
                                <div class="filter-control filter-department"></div>
                                <div class="filter-control filter-user"></div>
                                <div class="filter-control filter-date"></div>
                                <div class="filter-control filter-status"></div>
                                <div class="filter-control filter-issue"></div>
                                <button class="btn btn-primary btn-search">${__("Search")}</button>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="mgr-summary-row mb-3" role="group" aria-label="${__("Summary Statistics")}">
                    <div class="summary-card summary-card-clickable is-blue" data-group="today_all" role="button" tabindex="0" aria-label="${__("Today Total")}">
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
                    </div>

                    <div class="summary-card summary-card-clickable is-orange" data-group="today_open" role="button" tabindex="0" aria-label="${__("Today Open")}">
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
                    </div>

                    <div class="summary-card summary-card-clickable is-green" data-group="today_completed" role="button" tabindex="0" aria-label="${__("Today Completed")}">
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
                    </div>

                    <div class="summary-card summary-card-clickable is-red" data-group="today_remaining" role="button" tabindex="0" aria-label="${__("Today Remaining")}">
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
                    </div>

                    <div class="summary-card summary-card-clickable is-purple" data-group="today_has_issue" role="button" tabindex="0" aria-label="${__("Today Has Issue")}">
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
                    </div>

                    <div class="summary-card summary-card-clickable is-secondary prev-open-card d-none" data-group="prev_open" role="button" tabindex="0" aria-label="${__("Prev Open")}">
                        <div class="summary-card-inner">
                            <div class="summary-icon-wrap is-secondary">
                                <svg class="summary-icon-svg" viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 6V12L16 14"></path>
                                    <circle cx="12" cy="12" r="7.5"></circle>
                                </svg>
                            </div>
                            <div class="summary-content">
                                <div class="summary-label">${__("Prev Open")}</div>
                                <div class="summary-value prev-open">0</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card shadow-sm border-0 mgr-panel">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-center flex-wrap mb-3">
                            <div class="panel-title active-group-title mb-0">${__("Today Open Cards")}</div>
                            <span class="active-group-count badge badge-secondary">0</span>
                        </div>

                        <div class="cards-list-panel"></div>
                    </div>
                </div>

                <div class="checklist-drawer-backdrop" role="presentation"></div>

                <aside class="checklist-drawer" role="dialog" aria-label="${__("Checklist Answers Drawer")}">
                    <div class="checklist-drawer-header">
                        <div>
                            <div class="checklist-drawer-title">${__("Checklist Answers")}</div>
                            <div class="checklist-drawer-subtitle">${__("Details and answers")}</div>
                        </div>
                        <button class="checklist-drawer-close" type="button" aria-label="${__("Close Drawer")}">×</button>
                    </div>

                    <div class="selected-doc-wrapper">
                        <div class="selected-doc-meta"></div>
                        <div class="selected-doc-progress"></div>
                        <div class="selected-doc-body"></div>
                    </div>
                </aside>
            </div>
        `);

        this.$todayTotal = $(this.page.body).find(".today-total");
        this.$todayOpen = $(this.page.body).find(".today-open");
        this.$todayCompleted = $(this.page.body).find(".today-completed");
        this.$todayRemaining = $(this.page.body).find(".today-remaining");
        this.$todayHasIssue = $(this.page.body).find(".today-has-issue");
        this.$prevOpen = $(this.page.body).find(".prev-open");
        this.$prevOpenCard = $(this.page.body).find(".prev-open-card");

        this.$summaryCards = $(this.page.body).find(".summary-card-clickable");
        this.$cardsListPanel = $(this.page.body).find(".cards-list-panel");
        this.$activeGroupTitle = $(this.page.body).find(".active-group-title");
        this.$activeGroupCount = $(this.page.body).find(".active-group-count");

        this.$drawer = $(this.page.body).find(".checklist-drawer");
        this.$drawerBackdrop = $(this.page.body).find(".checklist-drawer-backdrop");
        this.$drawerClose = $(this.page.body).find(".checklist-drawer-close");

        this.$meta = $(this.page.body).find(".selected-doc-meta");
        this.$progress = $(this.page.body).find(".selected-doc-progress");
        this.$body = $(this.page.body).find(".selected-doc-body");

        this.$mobileFiltersBtn = $(this.page.body).find(".btn-mobile-filters");
        this.$filters = $(this.page.body).find(".mgr-filters");
        this.$btnSearch = $(this.page.body).find(".btn-search");
        this.$autoRefreshSelect = $(this.page.body).find(".auto-refresh-select");

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
                options: "\nAll\nOpen\nDraft\nIn Progress\nCompleted\nExpired\nAuto Closed"
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
        this.$autoRefreshSelect.val(String(this.autoRefreshMinutes));
    }

    bind_events() {
        this.$btnSearch.on("click.checklist_mgr", async () => {
            this.activeGroup = "search";
            await this.load_dashboard(true);
        });

        this.$summaryCards.on("click.checklist_mgr", (e) => {
            const group = $(e.currentTarget).attr("data-group");
            this.set_active_group(group);
        });

        this.$summaryCards.on("keypress.checklist_mgr", (e) => {
            if (e.which === 13 || e.which === 32) {
                e.preventDefault();
                $(e.currentTarget).click();
            }
        });

        this.$drawerClose.on("click.checklist_mgr", () => this.close_drawer());
        this.$drawerBackdrop.on("click.checklist_mgr", () => this.close_drawer());

        this.$mobileFiltersBtn.on("click.checklist_mgr", () => {
            const isOpen = this.$mobileFiltersBtn.hasClass("is-open");
            this.$mobileFiltersBtn.toggleClass("is-open", !isOpen);
            this.$mobileFiltersBtn.attr("aria-expanded", !isOpen);
            this.$filters.stop(true, true).slideToggle(180).toggleClass("is-open");
        });

        this.$autoRefreshSelect.on("change.checklist_mgr", (e) => {
            const value = parseInt($(e.currentTarget).val(), 10);
            this.autoRefreshMinutes = Number.isFinite(value) && value > 0 ? value : 10;
            this.start_auto_refresh();
        });

        $(document)
            .off("keydown.checklist_admin_drawer")
            .on("keydown.checklist_admin_drawer", (e) => {
                if (e.key === "Escape") {
                    this.close_drawer();
                }
            });
    }

    start_auto_refresh() {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }

        this.autoRefreshTimer = setInterval(async () => {
            if (!this.isLoading) {
                await this.load_dashboard(false);
                if (this.selectedDocname) {
                    await this.load_doc(this.selectedDocname, false);
                }
            }
        }, this.get_refresh_interval_ms());
    }

    open_drawer() {
        this.$drawer.addClass("is-open");
        this.$drawerBackdrop.addClass("is-open");
        $("body").addClass("checklist-drawer-open");
        this.$drawerClose.focus();
    }

    close_drawer() {
        this.$drawer.removeClass("is-open");
        this.$drawerBackdrop.removeClass("is-open");
        $("body").removeClass("checklist-drawer-open");

        if (this.lastFocusedElement) {
            $(this.lastFocusedElement).focus();
        }
    }

    async load_initial_state() {
        await this.load_dashboard(true);
        this.start_auto_refresh();

        const opts = frappe.route_options || {};
        if (opts.checklist_answer) {
            await this.load_doc(opts.checklist_answer);
        }
    }

    async load_dashboard(showLoading = true) {
        if (this.isLoading) return;
        this.isLoading = true;

        if (showLoading) {
            this.show_loading(this.$btnSearch, true);
        }

        try {
            const searchDate = this.date_control.get_value() || frappe.datetime.get_today();

            const r = await frappe.call({
                method: "taj_core.checklist.api.get_manager_dashboard_data",
                args: {
                    search_date: searchDate,
                    template: this.template_control.get_value(),
                    department: this.department_control.get_value(),
                    assigned_user: this.user_control.get_value(),
                    status: this.status_control.get_value(),
                    issue_filter: this.issue_control.get_value()
                }
            });

            this.lastData = r.message || {};
            const summary = this.lastData.summary || {};

            this.$todayTotal.text(summary.today_total || 0);
            this.$todayOpen.text(summary.today_open || 0);
            this.$todayCompleted.text(summary.today_completed || 0);
            this.$todayRemaining.text(summary.today_remaining || 0);
            this.$todayHasIssue.text(summary.today_has_issue || 0);

            const prevOpenCount = summary.prev_open || 0;
            this.$prevOpen.text(prevOpenCount);

            if (prevOpenCount > 0) {
                this.$prevOpenCard.removeClass("d-none");
            } else {
                this.$prevOpenCard.addClass("d-none");
                if (this.activeGroup === "prev_open") {
                    this.activeGroup = "today_open";
                }
            }

            this.render_active_group();
        } catch (e) {
            frappe.msgprint({
                title: __("Error"),
                indicator: "red",
                message: __("Failed to load manager dashboard. Please check network and try again.")
            });
            this.log_client_error("Checklist Admin Dashboard Error", e);
        } finally {
            this.isLoading = false;
            if (showLoading) {
                this.show_loading(this.$btnSearch, false);
            }
        }
    }

    set_active_group(groupName) {
        this.activeGroup = groupName;
        this.$summaryCards.removeClass("is-active");
        this.$summaryCards.filter(`[data-group="${groupName}"]`).addClass("is-active");
        this.render_active_group();
    }

    get_group_data_map() {
        return {
            today_all: () => this.lastData?.today_all || [],
            today_open: () => this.lastData?.today_open || [],
            today_completed: () => this.lastData?.today_completed || [],
            today_remaining: () => this.lastData?.today_remaining_docs || [],
            today_has_issue: () => this.lastData?.today_has_issue_docs || [],
            prev_open: () => this.lastData?.prev_open_docs || [],
            search: () => this.lastData?.search_results || []
        };
    }

    get_active_docs() {
        const map = this.get_group_data_map();
        const getter = map[this.activeGroup];
        return getter ? getter() : [];
    }

    get_active_group_title() {
        const titles = {
            today_all: __("Today Total Cards"),
            today_open: __("Today Open Cards"),
            today_completed: __("Today Completed Cards"),
            today_remaining: __("Today Remaining Cards"),
            today_has_issue: __("Today Has Issue Cards"),
            prev_open: __("Prev Open Cards"),
            search: __("Search Result Cards")
        };
        return titles[this.activeGroup] || __("Checklist Cards");
    }

    get_empty_text() {
        const emptyMap = {
            today_all: __("No records found for today."),
            today_open: __("No open tasks today."),
            today_completed: __("No completed tasks today."),
            today_remaining: __("No remaining tasks today."),
            today_has_issue: __("No issue tasks today."),
            prev_open: __("No previous open tasks."),
            search: __("No search results found.")
        };
        return emptyMap[this.activeGroup] || __("No records found.");
    }

    render_active_group() {
        const docs = this.get_active_docs();

        this.$activeGroupTitle.text(this.get_active_group_title());
        this.$activeGroupCount.text(docs.length);

        this.$summaryCards.removeClass("is-active");
        this.$summaryCards.filter(`[data-group="${this.activeGroup}"]`).addClass("is-active");

        this.render_cards_list(this.$cardsListPanel, docs, this.get_empty_text());
    }

    render_cards_list($target, docs, emptyText) {
        $target.empty();

        if (!docs.length) {
            $target.html(`<div class="empty-state">${emptyText}</div>`);
            return;
        }

        const fragment = document.createDocumentFragment();

        docs.forEach((doc, index) => {
            const activeClass = this.selectedDocname === doc.name ? "is-active" : "";
            const issueClass = doc.has_issue ? "has-issue" : "";
            const overdueClass = doc.time_status === "Overdue" ? "is-overdue" : "";
            const timeStatus = this.escape(doc.time_status || "-");
            const delayMinutes = doc.delay_minutes != null ? doc.delay_minutes : 0;

            const card = document.createElement("div");
            card.className = `checklist-list-item ${activeClass} ${issueClass} ${overdueClass}`;
            card.setAttribute("role", "button");
            card.setAttribute("tabindex", "0");
            card.setAttribute("aria-label", `Checklist ${this.escape(doc.template || "")}`);

            card.innerHTML = `
                <div class="checklist-list-top">
                    <div class="checklist-list-head">
                        <div class="checklist-list-template">${this.escape(doc.template || "-")}</div>
                        <div class="checklist-list-docname">${this.escape(doc.name || "-")}</div>
                    </div>
                    <div class="checklist-list-side">
                        <span class="issue-badge ${doc.has_issue ? "is-issue" : "is-normal"}">
                            ${doc.has_issue ? __("Has Issue") : __("Normal")}
                        </span>
                    </div>
                </div>

                <div class="checklist-list-meta">
                    <div><strong>${__("No.")}:</strong> ${index + 1}</div>
                    <div><strong>${__("Status")}:</strong> ${this.escape(doc.status || "-")}</div>
                    <div><strong>${__("Department")}:</strong> ${this.escape(doc.department || "-")}</div>
                    <div><strong>${__("Assigned User")}:</strong> ${this.escape(doc.assigned_user || "-")}</div>
                    <div><strong>${__("Result")}:</strong> ${this.escape(doc.result_status || "Normal")}</div>
                    <div><strong>${__("Time Status")}:</strong> ${timeStatus}</div>
                    <div><strong>${__("Delay")}:</strong> ${delayMinutes} ${__("min")}</div>
                </div>
            `;

            card.addEventListener("click", (e) => {
                this.lastFocusedElement = e.currentTarget;
                this.load_doc(doc.name, true);
            });

            card.addEventListener("keypress", (e) => {
                if (e.which === 13 || e.which === 32) {
                    e.preventDefault();
                    this.lastFocusedElement = e.currentTarget;
                    this.load_doc(doc.name, true);
                }
            });

            fragment.appendChild(card);
        });

        $target.append(fragment);
    }

    async load_doc(docname, rerenderCards = true) {
        try {
            const r = await frappe.call({
                method: "taj_core.checklist.api.get_checklist_answer",
                args: { docname }
            });

            this.doc = r.message;
            this.selectedDocname = docname;
            this.render_doc();
            this.open_drawer();

            if (rerenderCards) {
                this.render_active_group();
            }
        } catch (e) {
            frappe.msgprint({
                title: __("Error"),
                indicator: "red",
                message: __("Failed to load checklist document.")
            });
            this.log_client_error("Checklist Admin Load Doc Error", e);
        }
    }

    render_doc() {
        if (!this.doc) return;

        this.page.set_indicator(this.doc.status || "Draft", this.get_indicator_color(this.doc.status));

        const issueBadge = this.doc.has_issue
            ? `<span class="issue-badge is-issue">${__("Has Issue")}</span>`
            : `<span class="issue-badge is-normal">${__("Normal")}</span>`;

        this.$meta.html(`
            <div style="margin-bottom:8px;">${issueBadge}</div>

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

        $toggle.off("click.checklist_mgr").on("click.checklist_mgr", function () {
            const isOpen = $(this).attr("aria-expanded") === "true";
            $panel.stop(true, true).slideToggle(180);
            $(this).attr("aria-expanded", String(!isOpen));
            $icon.text(isOpen ? "+" : "−");
            $(this).toggleClass("is-open", !isOpen);
        });

        const questions = this.doc?.questions || [];
        const answered = questions.filter(q => String(q.answer || "").trim()).length;

        this.$progress.html(`
            <div class="progress-wrap">
                <div class="progress-line">
                    <strong>${__("Progress")}:</strong>
                    ${answered} / ${questions.length} ${__("answered")}
                </div>
            </div>
        `);

        this.$body.empty();

        if (!questions.length) {
            this.$body.html(`<div class="empty-state">${__("No questions found.")}</div>`);
            return;
        }

        const fragment = document.createDocumentFragment();

        questions.forEach((row, index) => {
            const issueClass = row.has_issue ? "has-issue" : "";
            const issueLine = row.has_issue
                ? `<div style="margin-bottom:6px;"><span class="issue-badge is-issue">${__("Issue Answer")}</span></div>`
                : "";

            const answerCard = document.createElement("div");
            answerCard.className = `checklist-answer-readonly ${issueClass}`;
            answerCard.innerHTML = `
                ${issueLine}
                <div class="checklist-question-title">
                    <span class="question-number">${index + 1}</span>
                    <span>${this.escape(row.question_text || row.question || "")}</span>
                </div>
                <div class="readonly-answer-value">
                    <strong>${__("Answer")}:</strong> ${this.escape(row.answer || "-")}
                </div>
                ${row.issue_note ? `<div class="readonly-answer-value"><strong>${__("Issue Note")}:</strong> ${this.escape(row.issue_note)}</div>` : ""}
            `;
            fragment.appendChild(answerCard);
        });

        this.$body.append(fragment);
    }

    get_indicator_color(status) {
        const colorMap = {
            "Completed": "green",
            "In Progress": "orange",
            "Auto Closed": "darkgrey",
            "Expired": "red"
        };
        return colorMap[status] || "blue";
    }
}