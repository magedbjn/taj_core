/* Pick List Receiving v0.8: one QR = one Pick List, mobile-first. */
/* Transfer endpoint, warehouse checks, inventory validation and settings remain v0.7. */
frappe.pages["pick-list-receiving"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Pick List Receiving"),
    single_column: true,
  });
  frappe.require("/assets/taj_core/js/pick_list_receiving_helpers.js", () => {
    const $root = $('<div class="pick-list-receiving plr-v08"></div>').appendTo(page.body);
    const helpers = window.TAJ_PICK_LIST_RECEIVING_HELPERS;
    const t = (value) => __(value);
    const tx = (value, args) => __(value, args);
    const esc = (value) => frappe.utils.escape_html(String(value == null ? "" : value));
    const state = {
      id: null, mode: "EMPTY", review: null, rows: [], checks: {},
      stockEntry: "", justTransferred: false, message: "", requestSerial: 0,
    };
    const renderQty = (qty) => {
      const n = Number(qty);
      return Number.isFinite(n) ? n.toLocaleString("en-US", { maximumFractionDigits: 9 }) : "—";
    };
    const isOpen = () => state.mode === "OPEN" && !!state.review;
    const count = () => state.rows.filter((row) => state.checks[row.row_id] === true).length;
    const verified = () => isOpen() && state.rows.length > 0 && count() === state.rows.length;
    const statusText = () => state.mode === "TRANSFERRED" ? t(state.justTransferred ? "Transferred Successfully" : "Already Transferred") :
      state.mode === "COMPLETED_REVIEW" ? t("Completed") :
      state.mode === "CANCELLED" ? t("Cancelled") :
      state.mode === "UNCERTAIN" ? t("Check status") :
      isOpen() ? tx("{0}/{1} confirmed", [count(), state.rows.length]) : "";

    function qrPickList() {
      const params = new URLSearchParams(window.location.search || "");
      if (params.getAll("pl").length !== 1 || [...params.keys()].some((key) => key !== "pl")) return null;
      try { return helpers.code(params.get("pl"), window.location.origin); }
      catch (_) { return null; }
    }

    function renderItem(row) {
      const done = state.mode === "TRANSFERRED";
      const canCheck = isOpen();
      const checked = state.checks[row.row_id] === true;
      const note = [
        row.batch_no ? `${esc(t("Batch"))}: ${esc(row.batch_no)}` : "",
        row.required_brand ? `${esc(t("Brand"))}: ${esc(row.required_brand)}` : "",
      ].filter(Boolean).join(" · ");
      return `<section class="plr-item" data-row-id="${esc(row.row_id)}">
        <div class="plr-item-heading"><strong>${esc(row.item_name || row.item_code)}</strong>
          <span>${esc(row.item_code)}</span></div>
        <div class="plr-qty-grid" aria-label="${esc(t("Quantities"))}">
          <div class="plr-qty plr-required"><span class="plr-label">${esc(t("Required Qty"))}</span>
            <div class="plr-value"><strong>${esc(renderQty(row.requested_qty))}</strong>
              <span>${esc(row.requested_uom)}</span></div></div>
          <div class="plr-qty plr-picked"><span class="plr-label">${esc(t("Picked Qty"))}</span>
            <div class="plr-value"><strong>${esc(renderQty(row.picked_qty))}</strong>
              <span>${esc(row.stock_uom)}</span></div></div>
        </div>
        <div class="plr-route">
          <div class="plr-warehouse"><span class="plr-label">${esc(t("From"))}</span>
            <strong>${esc(row.source || "—")}</strong></div>
          <span class="plr-route-arrow" aria-hidden="true"><i class="fa fa-long-arrow-right"></i></span>
          <div class="plr-warehouse"><span class="plr-label">${esc(t("To"))}</span>
            <strong>${esc(row.target || "—")}</strong></div>
        </div>
        ${note ? `<div class="plr-item-note">${note}</div>` : ""}
        ${canCheck ? `<label class="plr-check-label"><input type="checkbox" class="plr-check"
          data-check="${esc(row.row_id)}" ${checked ? "checked" : ""} />
          <span>${esc(t("Confirmed"))}</span></label>` :
          done ? `<div class="plr-row-done"><i class="fa fa-check-circle" aria-hidden="true"></i> ${esc(t("Transferred"))}</div>` : ""}
      </section>`;
    }

    function draw() {
      let html = '<div class="plr-shell">';
      if (state.mode === "EMPTY") {
        html += `<div class="plr-empty"><i class="fa fa-qrcode" aria-hidden="true"></i>
          <strong>${esc(t("Open a Pick List QR code"))}</strong></div>`;
      } else if (state.mode === "LOADING") {
        html += `<div class="plr-empty"><i class="fa fa-spinner fa-spin" aria-hidden="true"></i>
          <span>${esc(t("Loading"))}...</span></div>`;
      } else if (state.mode === "ERROR") {
        html += `<div class="plr-empty plr-error"><i class="fa fa-exclamation-circle" aria-hidden="true"></i>
          <strong>${esc(t("Unable to open Pick List"))}</strong>
          <button type="button" class="btn btn-default" data-action="reload">${esc(t("Retry"))}</button></div>`;
      } else {
        const displayRows = state.rows || [];
        const done = state.mode === "TRANSFERRED";
        html += `<header class="plr-header">
          <div class="plr-heading"><span class="plr-kicker">${esc(t("Pick List"))}</span>
            <h2>${esc(state.id)}</h2>
            ${state.review?.reference ? `<span class="plr-work-order">${esc(t("Work Order"))}: ${esc(state.review.reference)}</span>` : ""}
          </div>
          <span class="plr-status ${done ? "plr-complete" : ""}">${esc(statusText())}</span>
        </header>
        <main class="plr-items">${displayRows.map(renderItem).join("")}</main>`;
        if (done) {
          html += `<div class="plr-success" role="status">
            <i class="fa fa-check-circle" aria-hidden="true"></i>
            <div><strong>${esc(t(state.justTransferred ? "Transferred Successfully" : "Already Transferred"))}</strong>
              <span>${esc(state.stockEntry)}</span>
              ${state.stockEntry ? `<a href="/app/stock-entry/${encodeURIComponent(state.stockEntry)}">${esc(t("View Stock Entry"))}</a>` : ""}
            </div></div>`;
        } else if (state.mode === "COMPLETED_REVIEW") {
          html += `<div class="plr-alert" role="status">${esc(t("Completed — review in ERPNext"))}</div>`;
        } else if (state.mode === "CANCELLED") {
          html += `<div class="plr-alert" role="status">${esc(t("Cancelled"))}</div>`;
        } else if (state.mode === "UNCERTAIN") {
          html += `<div class="plr-alert" role="alert">${esc(t("Check transfer status before retrying"))}</div>`;
        }
        if (isOpen() || state.mode === "POSTING" || state.mode === "UNCERTAIN") {
          html += `<div class="plr-footer">
            <span class="plr-progress">${isOpen() ? esc(tx("{0}/{1} confirmed", [count(), state.rows.length])) : ""}</span>
            ${state.mode === "UNCERTAIN" ? `<button class="btn btn-primary plr-primary" type="button"
              data-action="check">${esc(t("Check status"))}</button>` :
              `<button class="btn btn-primary plr-primary" type="button" data-action="transfer"
                ${verified() ? "" : "disabled"}>${esc(t(state.mode === "POSTING" ? "Transferring" : "Confirm & Transfer"))}</button>`}
          </div>`;
        }
      }
      html += '</div>';
      $root.html(html);
    }

    function updateChecksUI() {
      if (!isOpen()) return;
      const label = tx("{0}/{1} confirmed", [count(), state.rows.length]);
      $root.find(".plr-status,.plr-progress").text(label);
      $root.find('[data-action="transfer"]').prop("disabled", !verified());
    }

    async function fetchPickList(id, force = false) {
      if (!force && state.id === id && ["OPEN", "TRANSFERRED", "POSTING", "LOADING"].includes(state.mode)) return;
      if (state.mode === "POSTING") return;
      state.id = id;
      state.mode = "LOADING";
      state.review = null;
      state.rows = [];
      state.checks = {};
      state.stockEntry = "";
      state.justTransferred = false;
      const serial = ++state.requestSerial;
      draw();
      try {
        const response = await frappe.call({
          method: "taj_core.pick_list_receiving.api.get_receipt_view",
          type: "GET", args: { pick_list: id },
        });
        if (serial !== state.requestSerial) return;
        const view = response.message;
        if (!view || !["OPEN", "TRANSFERRED", "CANCELLED", "COMPLETED_REVIEW"].includes(view.status)) {
          throw new Error("Invalid Pick List view response");
        }
        state.mode = view.status;
        if (view.status === "OPEN") {
          if (!view.review || !Array.isArray(view.review.rows) || !view.review.rows.length) {
            throw new Error("Missing Pick List rows");
          }
          state.review = view.review;
          state.rows = view.review.rows;
          state.checks = Object.fromEntries(state.rows.map((row) => [row.row_id, false]));
        } else if (view.status === "TRANSFERRED") {
          state.review = { reference: view.reference };
          state.rows = Array.isArray(view.rows) ? view.rows : [];
          state.stockEntry = view.stock_entry || "";
        }
      } catch (error) {
        if (serial !== state.requestSerial) return;
        state.mode = "ERROR";
        // Native Frappe errors remain visible for permission and stock issues.
        console.warn("Pick List Receiving QR view rejected", id, error);
      }
      draw();
    }

    function loadQR() {
      const id = qrPickList();
      if (!id) {
        if (state.mode === "POSTING") return;
        ++state.requestSerial;
        state.id = null;
        state.mode = "EMPTY";
        state.review = null;
        state.rows = [];
        state.checks = {};
        state.stockEntry = "";
        state.justTransferred = false;
        draw();
        return;
      }
      fetchPickList(id);
    }

    function transfer() {
      if (!verified()) return;
      const id = state.id;
      frappe.confirm(tx("Transfer Pick List {0}?", [id]), async () => {
        if (!verified() || id !== state.id) return;
        state.mode = "POSTING";
        draw();
        const confirmations = state.rows.map((row) => ({ row_id: row.row_id, checked: state.checks[row.row_id] === true }));
        try {
          const result = (await frappe.call({
            method: "taj_core.pick_list_receiving.api.transfer_confirmed",
            type: "POST",
            args: { pick_list: id, signature: state.review.signature, confirmations: JSON.stringify(confirmations) },
          })).message;
          if (!result || result.status !== "TRANSFERRED" || result.stock_entry_docstatus !== 1 || !result.stock_entry) {
            throw new Error("Invalid Stock Entry transfer response");
          }
          state.mode = "TRANSFERRED";
          state.justTransferred = true;
          state.stockEntry = result.stock_entry;
          frappe.show_alert({ message: tx("Transferred · {0}", [result.stock_entry]), indicator: "green" }, 4);
        } catch (error) {
          // A lost network response may hide a successful POST. Never allow a blind retry.
          state.mode = "UNCERTAIN";
          console.warn("Pick List Receiving transfer response uncertain", id, error);
        }
        draw();
      });
    }

    $root.on("change", '[data-check]', (event) => {
      if (!isOpen()) return;
      const $checkbox = $(event.currentTarget);
      const rowId = String($checkbox.data("check"));
      if (!Object.prototype.hasOwnProperty.call(state.checks, rowId)) return;
      state.checks[rowId] = !!$checkbox.prop("checked");
      updateChecksUI();
    });
    $root.on("click", "[data-action]", (event) => {
      const action = $(event.currentTarget).data("action");
      if (action === "transfer") transfer();
      if (action === "check" || action === "reload") fetchPickList(state.id, true);
    });
    draw();
    loadQR();
    $(wrapper).data("plr-v08-show", loadQR);
  });
};
frappe.pages["pick-list-receiving"].on_page_show = function (wrapper) {
  const handler = $(wrapper).data("plr-v08-show");
  if (handler) handler();
};
