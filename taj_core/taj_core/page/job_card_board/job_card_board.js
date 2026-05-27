frappe.pages["job-card-board"].on_page_load = function (wrapper) {
  $(document.body).addClass("full-width");

  const RT_EVENT = "job_card_board_update";
  const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
  const OP_SPEC_CACHE_PREFIX = "jc_board:op_spec:v9:";
  const COOK_REQ_CACHE_PREFIX = "jc_board:cook_req:v1:";
  const FILTERS_HIDDEN_KEY = "job_card_board_filters_hidden_v1";

  const urlParams = new URLSearchParams(window.location.search || "");

  const IS_WALL =
    (urlParams.get("mode") || "").toLowerCase() === "wall" ||
    urlParams.get("wall") === "1";

  if (IS_WALL) $(document.body).addClass("jc-wall");

  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Job Card Board"),
    single_column: true,
  });

  const state = { limit: 60, offset: 0, loading: false };

  const root = $("<div class=\"jc-board\"></div>").appendTo(page.body);
  const grid = $("<div class=\"jc-grid\"></div>").appendTo(root);

  // -------------------------
  // Helpers
  // -------------------------
  function roomify(val) {
    return String(val || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function slug_status(s) {
    return (s || "")
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/\s+/g, "-")
      .trim();
  }

  function format_hms(totalSeconds) {
    const s = Math.max(cint(totalSeconds || 0), 0);
    const hh = Math.floor(s / 3600);
    const mm = Math.floor((s - hh * 3600) / 60);
    const ss = s - hh * 3600 - mm * 60;
    const pad = (n) => (n < 10 ? "0" + n : "" + n);
    return `${pad(hh)}:${pad(mm)}:${pad(ss)}`;
  }

  const DEC_SEP = (() => {
    try {
      const s = String(format_number(1.1));
      const onlySep = s.replace(/[0-9\u0660-\u0669\u06F0-\u06F9]/g, "").trim();
      return onlySep ? onlySep[0] : ".";
    } catch (e) {
      return ".";
    }
  })();

  function format_qty(val, max_dp = 6) {
    const n = flt(val || 0);
    if (!isFinite(n)) return "-";

    let s = "";
    try {
      s = String(format_number(n, null, max_dp));
    } catch (e) {
      s = String(n);
    }

    const ds = DEC_SEP;
    const esc = ds.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

    s = s.replace(new RegExp(`(${esc}\\d*?[1-9])0+$`), "$1");
    s = s.replace(new RegExp(`${esc}0+$`), "");
    s = s.replace(new RegExp(`${esc}$`), "");

    return s;
  }

  function escape_html(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function read_ttl_cache(prefix, key) {
    try {
      const raw = localStorage.getItem(`${prefix}${key}`);
      if (!raw) return null;

      const parsed = JSON.parse(raw);
      if (!parsed || !parsed.expires_at) return null;

      if (Date.now() > cint(parsed.expires_at)) {
        localStorage.removeItem(`${prefix}${key}`);
        return null;
      }

      return parsed.payload || null;
    } catch (e) {
      return null;
    }
  }

  function write_ttl_cache(prefix, key, payload) {
    try {
      localStorage.setItem(
        `${prefix}${key}`,
        JSON.stringify({
          expires_at: Date.now() + CACHE_TTL_MS,
          payload: payload || {},
        })
      );
    } catch (e) {}
  }

  const opSpecCache = new Map();
  const cookReqCache = new Map();

  async function get_operation_spec(job_card) {
    if (!job_card) return {};

    if (opSpecCache.has(job_card)) {
      return opSpecCache.get(job_card);
    }

    const lsCached = read_ttl_cache(OP_SPEC_CACHE_PREFIX, job_card);
    if (lsCached) {
      opSpecCache.set(job_card, lsCached);
      return lsCached;
    }

    const r = await frappe.call({
      method: "taj_core.taj_core.page.job_card_board.job_card_board.get_operation_spec",
      args: { job_card },
      freeze: false,
    });

    const payload = r.message || {};
    opSpecCache.set(job_card, payload);
    write_ttl_cache(OP_SPEC_CACHE_PREFIX, job_card, payload);
    return payload;
  }

  async function get_cooking_operation_items(job_card) {
    if (!job_card) return {};

    if (cookReqCache.has(job_card)) {
      return cookReqCache.get(job_card);
    }

    const lsCached = read_ttl_cache(COOK_REQ_CACHE_PREFIX, job_card);
    if (lsCached) {
      cookReqCache.set(job_card, lsCached);
      return lsCached;
    }

    const r = await frappe.call({
      method: "taj_core.taj_core.page.job_card_board.job_card_board.get_cooking_operation_items",
      args: { job_card },
      freeze: false,
    });

    const payload = r.message || {};
    cookReqCache.set(job_card, payload);
    write_ttl_cache(COOK_REQ_CACHE_PREFIX, job_card, payload);
    return payload;
  }

  async function get_start_requirements(job_card) {
    if (!job_card) {
      return {
        enabled: 0,
        needs_metal_detector: 0,
        values: {},
      };
    }

    const r = await frappe.call({
      method: "taj_core.taj_core.page.job_card_board.job_card_board.get_start_requirements",
      args: { job_card },
      freeze: false,
    });

    return r.message || {
      enabled: 0,
      needs_metal_detector: 0,
      values: {},
    };
  }

  function show_operation_spec_popup(data) {
    const op = data?.operation || "-";
    const wo = data?.work_order || "-";
    const pf = data?.plant_floor || "-";
    const desc = String(data?.description || "").trim();

    const rawMaterials = Array.isArray(data?.raw_materials) ? data.raw_materials : [];
    const fillingDetails = data?.filling_details || {};
    const fillingRows = Array.isArray(fillingDetails?.rows) ? fillingDetails.rows : [];
    const fillingTotals = fillingDetails?.totals || {};
    const pouchSize = fillingDetails?.pouch_size || "";

    const fmt = (v, dp = 2) => escape_html(format_qty(v || 0, dp));
    const txt = (v) => escape_html(v == null || v === "" ? "-" : String(v));

    let bodyHtml = `
      <div style="display:grid; gap:14px;">
        <div style="font-size:12px; color:#6b7280;">
          <div><b>${__("Work Order")}:</b> ${escape_html(wo)}</div>
          <div><b>${__("Operation")}:</b> ${escape_html(op)}</div>
          <div><b>${__("Plant Floor")}:</b> ${escape_html(pf)}</div>
        </div>
    `;

    if (pf === "Preparation Area") {
      const rawRows = rawMaterials.length
        ? rawMaterials
            .map(
              (r, i) => `
                <tr>
                  <td style="padding:8px; border:1px solid #e5e7eb;">${i + 1}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb;">${txt(r.item_code)}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb;">${txt(r.item_name)}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb; text-align:right;">${fmt(r.qty, 2)}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb;">${txt(r.uom)}</td>
                </tr>
              `
            )
            .join("")
        : `
            <tr>
              <td colspan="5" style="padding:12px; text-align:center; border:1px solid #e5e7eb;" class="text-muted">
                ${__("No raw materials found.")}
              </td>
            </tr>
          `;

      bodyHtml += `
        <div>
          <div style="font-size:13px; font-weight:700; margin-bottom:6px;">${__("Raw Materials")}</div>
          <div style="overflow:auto; max-height:320px;">
            <table style="width:100%; border-collapse:collapse; font-size:13px;">
              <thead>
                <tr style="background:#f8fafc;">
                  <th style="padding:8px; border:1px solid #e5e7eb;">#</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Item Code")}</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Item Name")}</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Qty")}</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("UOM")}</th>
                </tr>
              </thead>
              <tbody>${rawRows}</tbody>
            </table>
          </div>
        </div>
      `;
    } else if (pf === "Filling Area") {
      const rows = fillingRows.length
        ? fillingRows
            .map(
              (r) => `
                <tr>
                  <td style="padding:8px; border:1px solid #e5e7eb;">${txt(r.type)}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb;">${txt(r.value)}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb;">${txt(r.viscosity_or_size)}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb; text-align:right;">${fmt(r.weight, 2)}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb; text-align:right;">${fmt(r.under_weight, 2)}</td>
                  <td style="padding:8px; border:1px solid #e5e7eb; text-align:right;">${fmt(r.over_weight, 2)}</td>
                </tr>
              `
            )
            .join("")
        : `
            <tr>
              <td colspan="6" style="padding:12px; text-align:center; border:1px solid #e5e7eb;" class="text-muted">
                ${__("No filling data available")}
              </td>
            </tr>
          `;

      bodyHtml += `
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <div style="font-size:13px; font-weight:700;">${__("Filling Details")}</div>
            <div style="font-size:12px; color:#6b7280;">${__("Pouch Size")}: ${txt(pouchSize)}</div>
          </div>

          <div style="overflow:auto; max-height:320px;">
            <table style="width:100%; border-collapse:collapse; font-size:13px;">
              <thead>
                <tr style="background:#f8fafc;">
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Type")}</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Value")}</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Viscosity/Size")}</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Weight")}</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Under Weight")}</th>
                  <th style="padding:8px; border:1px solid #e5e7eb;">${__("Over Weight")}</th>
                </tr>
              </thead>
              <tbody>
                ${rows}
                ${
                  fillingRows.length
                    ? `
                      <tr style="background:#f8fafc; font-weight:700;">
                        <td colspan="3" style="padding:8px; border:1px solid #e5e7eb;">${__("Total")}</td>
                        <td style="padding:8px; border:1px solid #e5e7eb; text-align:right;">${fmt(fillingTotals.weight, 2)}</td>
                        <td style="padding:8px; border:1px solid #e5e7eb; text-align:right;">${fmt(fillingTotals.under_weight, 2)}</td>
                        <td style="padding:8px; border:1px solid #e5e7eb; text-align:right;">${fmt(fillingTotals.over_weight, 2)}</td>
                      </tr>
                    `
                    : ""
                }
              </tbody>
            </table>
          </div>
        </div>
      `;
    } else {
      bodyHtml += `
        <div>
          <div style="font-size:13px; font-weight:700; margin-bottom:6px;">${__("Description")}</div>
          <div style="
            white-space: pre-wrap;
            line-height: 1.7;
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 12px;
            min-height: 90px;
          ">
            ${
              desc
                ? escape_html(desc)
                : `<span class="text-muted">${__("No operation description found.")}</span>`
            }
          </div>
        </div>
      `;
    }

    bodyHtml += `</div>`;

    const d = new frappe.ui.Dialog({
      title: `${__("Operation Specs")} - ${op}`,
      fields: [{ fieldtype: "HTML", fieldname: "content" }],
      size: "large",
      primary_action_label: __("Close"),
      primary_action() {
        d.hide();
      },
    });

    d.fields_dict.content.$wrapper.html(bodyHtml);
    d.show();
  }

  function show_cooking_operation_items_popup(data) {
    const op = data?.operation || "-";
    const wo = data?.work_order || "-";
    const pf = data?.plant_floor || "-";
    const items = Array.isArray(data?.items) ? data.items : [];

    const rows = items.length
      ? items
          .map(
            (r, i) => `
        <tr>
          <td style="padding:8px; border:1px solid #e5e7eb;">${i + 1}</td>
          <td style="padding:8px; border:1px solid #e5e7eb;">${escape_html(r.item_name || "-")}</td>
          <td style="padding:8px; border:1px solid #e5e7eb;">${escape_html(r.taj_temperature ?? "-")}</td>
          <td style="padding:8px; border:1px solid #e5e7eb;">${escape_html(r.taj_duration ?? "-")}</td>
          <td style="padding:8px; border:1px solid #e5e7eb; white-space:pre-wrap;">${escape_html(r.taj_notes ?? "-")}</td>
        </tr>
      `
          )
          .join("")
      : `
        <tr>
          <td colspan="5" style="padding:12px; text-align:center; border:1px solid #e5e7eb;" class="text-muted">
            ${__("No cooking items found for this operation.")}
          </td>
        </tr>
      `;

    const d = new frappe.ui.Dialog({
      title: `${__("Cooking Items")} - ${op}`,
      fields: [{ fieldtype: "HTML", fieldname: "content" }],
      primary_action_label: __("Close"),
      primary_action() {
        d.hide();
      },
    });

    d.fields_dict.content.$wrapper.html(`
      <div style="display:grid; gap:10px;">
        <div style="font-size:12px; color:#6b7280;">
          <div><b>${__("Work Order")}:</b> ${escape_html(wo)}</div>
          <div><b>${__("Operation")}:</b> ${escape_html(op)}</div>
          <div><b>${__("Plant Floor")}:</b> ${escape_html(pf)}</div>
        </div>

        <div style="overflow:auto; max-height:420px;">
          <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <thead>
              <tr style="background:#f8fafc;">
                <th style="padding:8px; border:1px solid #e5e7eb;">#</th>
                <th style="padding:8px; border:1px solid #e5e7eb;">${__("Item Name")}</th>
                <th style="padding:8px; border:1px solid #e5e7eb;">${__("Temperature")}</th>
                <th style="padding:8px; border:1px solid #e5e7eb;">${__("Duration")}</th>
                <th style="padding:8px; border:1px solid #e5e7eb;">${__("Notes")}</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `);

    d.show();
  }

  async function print_preparation_label(name) {
    if (!name) return;

    try {
      const r = await frappe.call({
        method: "taj_core.taj_manufacturing.api.preparation_labels.render_preparation_labels_from_job_card",
        args: {
          job_card: name,
          label_mode: "cooking",
        },
        freeze: true,
        freeze_message: __("Generating Cooking Label..."),
      });

      const html = r.message && r.message.html;

      if (!html) {
        frappe.msgprint(__("No labels were generated."));
        return;
      }

      const printWindow = window.open("", "_blank");

      if (!printWindow) {
        frappe.msgprint(__("Popup blocked. Please allow popups and try again."));
        return;
      }

      printWindow.document.open();
      printWindow.document.write(html);
      printWindow.document.close();

      printWindow.focus();

      setTimeout(() => {
        printWindow.print();
      }, 300);
    } catch (e) {
      frappe.msgprint({
        title: __("Cooking Label"),
        message: e?.message || __("Unable to generate Cooking Label."),
        indicator: "red",
      });
    }
  }

  // -------------------------
  // Sound / Mute
  // -------------------------
  let audioCtx = null;
  let alarmInterval = null;
  let lastBeepAt = 0;

  const MUTE_KEY = "job_card_board_muted_cards_v2";
  const MUTE_ALL_KEY = "job_card_board_mute_all_v2";

  function loadMutedSet() {
    try {
      const raw = localStorage.getItem(MUTE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return new Set(Array.isArray(arr) ? arr : []);
    } catch {
      return new Set();
    }
  }

  function saveMutedSet(set) {
    try {
      localStorage.setItem(MUTE_KEY, JSON.stringify(Array.from(set)));
    } catch {}
  }

  function loadMuteAll() {
    if (IS_WALL) return true;
    try {
      return localStorage.getItem(MUTE_ALL_KEY) === "1";
    } catch {
      return false;
    }
  }

  function saveMuteAll(v) {
    try {
      localStorage.setItem(MUTE_ALL_KEY, v ? "1" : "0");
    } catch {}
  }

  let muted = loadMutedSet();
  let muteAll = loadMuteAll();

  function isMuted(name) {
    return muted.has(name);
  }

  function ensureAudioCtx() {
    if (IS_WALL) return null;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!audioCtx) audioCtx = new Ctx();
    if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
    return audioCtx;
  }

  function beepPulse() {
    if (IS_WALL || muteAll) return;

    const now = performance.now();
    if (now - lastBeepAt < 600) return;
    lastBeepAt = now;

    const ctx = ensureAudioCtx();
    if (!ctx) return;

    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "sine";
    o.frequency.value = 880;
    o.connect(g);
    g.connect(ctx.destination);

    const t = ctx.currentTime;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.16, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);

    o.start(t);
    o.stop(t + 0.24);
  }

  function startAlarm() {
    if (IS_WALL) return;
    if (alarmInterval) return;
    beepPulse();
    alarmInterval = setInterval(() => beepPulse(), 2000);
  }

  function stopAlarm() {
    if (!alarmInterval) return;
    clearInterval(alarmInterval);
    alarmInterval = null;
  }

  if (!IS_WALL) $(document).one("click", () => ensureAudioCtx());

  function refresh_alarm_state() {
    if (IS_WALL || muteAll) {
      stopAlarm();
      grid.find(".jc-card").removeClass("alerting");
      return;
    }

    const active = grid.find(".jc-card.is-overdue").filter((_, el) => {
      const c = $(el);
      const name = c.attr("data-name");
      const completed = cint(c.attr("data-completed") || 0);
      return !!name && completed === 0 && !isMuted(name);
    });

    grid.find(".jc-card").removeClass("alerting");
    if (active.length) {
      active.addClass("alerting");
      startAlarm();
    } else {
      stopAlarm();
    }
  }

  function toggleMute(name) {
    if (IS_WALL) return;
    if (!name) return;

    if (muted.has(name)) muted.delete(name);
    else muted.add(name);

    saveMutedSet(muted);

    const card = grid.find(`.jc-card[data-name="${name}"]`);
    card.toggleClass("is-muted", muted.has(name));
    card.find(`.jc-mute[data-name="${name}"]`).text(muted.has(name) ? "🔕" : "🔔");

    refresh_alarm_state();
  }

  if (!IS_WALL) {
    page.add_action_item(__("Mute All"), () => {
      muteAll = !muteAll;
      saveMuteAll(muteAll);
      frappe.show_alert({
        message: muteAll ? __("Muted all alerts") : __("Sound enabled"),
        indicator: muteAll ? "orange" : "green",
      });
      refresh_alarm_state();
    });
  }

  // -------------------------
  // Timer ticker
  // -------------------------
  let timerTicker = null;

  function stopTimerTicker() {
    if (timerTicker) {
      clearInterval(timerTicker);
      timerTicker = null;
    }
  }

  function startTimerTickerIfNeeded() {
    const hasRunning = grid.find(".jc-card.state-running .jc-timer").length > 0;
    if (!hasRunning) {
      stopTimerTicker();
      return;
    }
    if (timerTicker) return;

    timerTicker = setInterval(() => {
      grid.find(".jc-card.state-running .jc-timer").each(function () {
        const el = $(this);
        const card = el.closest(".jc-card");
        const completed = cint(card.attr("data-completed") || 0);
        if (completed === 1) return;

        let sec = cint(el.attr("data-seconds") || 0);
        sec += 1;
        el.attr("data-seconds", sec);
        el.text(format_hms(sec));

        const expected = cint(el.attr("data-expected") || 0);
        const paused = card.hasClass("state-paused");
        if (!paused && expected > 0 && sec > expected + 120) {
          if (!card.hasClass("is-overdue")) {
            card.addClass("is-overdue");
            refresh_alarm_state();
          }
        }
      });
    }, 1000);
  }

  // -------------------------
  // Filters
  // -------------------------
  const f_plant_floor = page.add_field({
    fieldtype: "Link",
    label: __("Plant Floor"),
    fieldname: "plant_floor",
    options: "Plant Floor",
    change: () => {
      setup_realtime_subscription();
      refresh_board();
    },
  });

  const f_work_order = page.add_field({
    fieldtype: "Link",
    label: __("Work Order"),
    fieldname: "work_order",
    options: "Work Order",
    change: () => refresh_board(),
  });

  const f_workstation = page.add_field({
    fieldtype: "Link",
    label: __("Workstation"),
    fieldname: "workstation",
    options: "Workstation",
    change: () => refresh_board(),
  });

  const f_operation = page.add_field({
    fieldtype: "Link",
    label: __("Operation"),
    fieldname: "operation",
    options: "Operation",
    change: () => refresh_board(),
  });

  const f_date_from = page.add_field({
    fieldtype: "Date",
    label: __("From Date"),
    fieldname: "date_from",
    change: () => refresh_board(),
  });

  const f_date_to = page.add_field({
    fieldtype: "Date",
    label: __("To Date"),
    fieldname: "date_to",
    change: () => refresh_board(),
  });

  const f_status = page.add_field({
    fieldtype: "Select",
    label: __("Status"),
    fieldname: "status_filter",
    options: [
      { label: __("All"), value: "ALL" },
      { label: __("Active"), value: "ACTIVE" },
      { label: __("Open"), value: "Open" },
      { label: __("Work In Progress"), value: "Work In Progress" },
      { label: __("On Hold"), value: "On Hold" },
      { label: __("Material Transferred"), value: "Material Transferred" },
      { label: __("Completed"), value: "Completed" },
      { label: __("Submitted"), value: "Submitted" },
    ],
    default: "ALL",
    change: () => refresh_board(),
  });

  const f_docstatus = page.add_field({
    fieldtype: "Select",
    label: __("Docstatus"),
    fieldname: "docstatus_filter",
    options: [
      { label: __("All (Draft + Submitted)"), value: "ALL" },
      { label: __("Draft"), value: "DRAFT" },
      { label: __("Submitted"), value: "SUBMITTED" },
    ],
    default: "ALL",
    change: () => refresh_board(),
  });

  const f_search = page.add_field({
    fieldtype: "Data",
    label: __("Search"),
    fieldname: "search",
    change: frappe.utils.debounce(() => {
      setup_realtime_subscription();
      refresh_board();
    }, 350),
  });

  if (!IS_WALL) {
    page.set_primary_action(__("Refresh"), () => refresh_board(), "refresh");
    page.add_action_item(__("Load more"), () => load_cards(false));
  } else {
    try {
      $(page.page_form).hide();
    } catch (e) {}
    try {
      $(page.page_actions).hide();
    } catch (e) {}
  }

  // -------------------------
  // Responsive filters toggle
  // -------------------------
  function loadFiltersHidden() {
    try {
      return localStorage.getItem(FILTERS_HIDDEN_KEY) === "1";
    } catch {
      return false;
    }
  }

  function saveFiltersHidden(v) {
    try {
      localStorage.setItem(FILTERS_HIDDEN_KEY, v ? "1" : "0");
    } catch {}
  }

  function isCompactFiltersScreen() {
    return window.matchMedia(
      "(max-width: 1180px), (orientation: landscape) and (max-width: 1366px) and (hover: none) and (pointer: coarse)"
    ).matches;
  }

  let filtersHidden = loadFiltersHidden() || isCompactFiltersScreen();

  const $filterToggleBtn = $(`
    <button type="button"
            class="btn btn-default btn-sm jc-filter-toggle"
            title="${__("Show / Hide Filters")}">☰</button>
  `);

  if (!IS_WALL) {
    const $actions = $(page.page_actions);
    if ($actions.length) $actions.prepend($filterToggleBtn);
  }

  function syncFiltersUI(animate = false) {
    const compact = !IS_WALL && isCompactFiltersScreen();
    const $form = $(page.page_form);

    if (!compact) {
      $filterToggleBtn.hide();
      $form.show();
      return;
    }

    $filterToggleBtn.show();
    $filterToggleBtn.text(filtersHidden ? "☰" : "✕");
    $filterToggleBtn.attr("title", filtersHidden ? __("Show Filters") : __("Hide Filters"));

    if (animate) {
      if (filtersHidden) $form.stop(true, true).slideUp(180);
      else $form.stop(true, true).slideDown(180);
    } else {
      if (filtersHidden) $form.hide();
      else $form.show();
    }
  }

  $filterToggleBtn.on("click", function () {
    filtersHidden = !filtersHidden;
    saveFiltersHidden(filtersHidden);
    syncFiltersUI(true);
  });

  const handleResponsiveFilters = frappe.utils.debounce(() => {
    syncFiltersUI(false);
  }, 100);

  window.addEventListener("resize", handleResponsiveFilters);
  window.addEventListener("orientationchange", handleResponsiveFilters);

  // -------------------------
  // Default dates
  // -------------------------
  let setting_dates = false;

  function ensure_today_dates_in_fields() {
    if (setting_dates) return;
    const df = f_date_from.get_value();
    const dt = f_date_to.get_value();
    if (!df && !dt) {
      setting_dates = true;
      const t = frappe.datetime.get_today();
      f_date_from.set_value(t);
      f_date_to.set_value(t);
      setting_dates = false;
    }
  }

  function get_dates_for_api() {
    const t = frappe.datetime.get_today();
    return { df: f_date_from.get_value() || t, dt: f_date_to.get_value() || t };
  }

  // -------------------------
  // Server calls
  // -------------------------
  async function call_api(method, args) {
    return frappe.call({
      method: `taj_core.taj_core.page.job_card_board.job_card_board.${method}`,
      args,
      freeze: true,
    });
  }

  async function fetch_card_payload_bulk(names) {
    const r = await frappe.call({
      method: "taj_core.taj_core.page.job_card_board.job_card_board.get_cards_payload_bulk_api",
      args: { names },
    });
    return r.message?.items || [];
  }

  // -------------------------
  // Filter matching
  // -------------------------
  function card_matches_filters(d) {
    const pf = (f_plant_floor.get_value() || "").trim();
    if (pf && String(d.plant_floor || "") !== pf) return false;

    const wo = f_work_order.get_value();
    if (wo && d.work_order !== wo) return false;

    const ws = f_workstation.get_value();
    if (ws && d.workstation !== ws) return false;

    const op = f_operation.get_value();
    if (op && d.operation !== op) return false;

    const sf = f_status.get_value();
    if (sf && sf !== "ALL") {
      if (sf === "ACTIVE") {
        const active = ["Open", "Work In Progress", "On Hold", "Material Transferred"];
        if (!active.includes(d.status)) return false;
      } else if (d.status !== sf) return false;
    }

    const ds = f_docstatus.get_value();
    if (ds === "DRAFT" && cint(d.docstatus) !== 0) return false;
    if (ds === "SUBMITTED" && cint(d.docstatus) !== 1) return false;

    const s = (f_search.get_value() || "").trim();
    if (s && !String(d.name || "").includes(s)) return false;

    return true;
  }

  // -------------------------
  // DOM update
  // -------------------------
  function insert_card_sorted(cardEl, name) {
    const cards = grid.find(".jc-card");
    if (!cards.length) return grid.append(cardEl);

    let inserted = false;
    cards.each(function () {
      const n = $(this).attr("data-name") || "";
      if (n && name && n.localeCompare(name) > 0) {
        $(this).before(cardEl);
        inserted = true;
        return false;
      }
      return true;
    });

    if (!inserted) grid.append(cardEl);
  }

  function remove_card(name) {
    const el = grid.find(`.jc-card[data-name="${name}"]`);
    if (el.length) el.remove();
  }

  function update_single_card(card) {
    if (!card || !card.name) return;

    const el = grid.find(`.jc-card[data-name="${card.name}"]`);

    if (!card_matches_filters(card)) {
      if (el.length) el.remove();
      startTimerTickerIfNeeded();
      refresh_alarm_state();
      return;
    }

    if (el.length) el.replaceWith(render_card(card));
    else insert_card_sorted(render_card(card), card.name);

    startTimerTickerIfNeeded();
    refresh_alarm_state();
  }

  // -------------------------
  // Lite realtime batching
  // -------------------------
  const dirtyNames = new Set();
  let dirtyTimer = null;

  function markDirty(name) {
    if (!name) return;
    dirtyNames.add(name);
    if (dirtyTimer) return;
    dirtyTimer = setTimeout(flushDirty, 160);
  }

  async function flushDirty() {
    dirtyTimer = null;
    const names = Array.from(dirtyNames);
    dirtyNames.clear();
    if (!names.length) return;

    try {
      const items = await fetch_card_payload_bulk(names);
      for (const c of items) update_single_card(c);
    } catch (e) {}
  }

  // -------------------------
  // Realtime subscription
  // -------------------------
  let doctypeSubscribed = false;
  let currentPfRoom = null;
  let currentDocRoom = null;

  function looks_like_job_card_name(s) {
    const v = (s || "").trim();
    if (!v) return false;
    if (v.includes(" ")) return false;
    if (v.length < 5) return false;
    return true;
  }

  function ensure_doctype_subscribe() {
    if (!frappe.realtime || doctypeSubscribed) return;
    try {
      frappe.realtime.subscribe("doctype: Job Card");
    } catch (e) {}
    try {
      frappe.realtime.subscribe("doctype:Job Card");
    } catch (e) {}
    doctypeSubscribed = true;
  }

  function setup_realtime_subscription() {
    ensure_doctype_subscribe();
    if (!frappe.realtime || !frappe.realtime.subscribe) return;

    const pf = (f_plant_floor.get_value() || "").trim();
    const nextPfRoom = pf ? `jc_board:pf:${roomify(pf)}` : null;

    const s = (f_search.get_value() || "").trim();
    const nextDocRoom = looks_like_job_card_name(s) ? `doc:Job Card/${s}` : null;

    if (currentPfRoom && frappe.realtime.unsubscribe && currentPfRoom !== nextPfRoom) {
      try {
        frappe.realtime.unsubscribe(currentPfRoom);
      } catch (e) {}
    }

    if (currentDocRoom && frappe.realtime.unsubscribe && currentDocRoom !== nextDocRoom) {
      try {
        frappe.realtime.unsubscribe(currentDocRoom);
      } catch (e) {}
    }

    if (nextPfRoom && nextPfRoom !== currentPfRoom) {
      try {
        frappe.realtime.subscribe(nextPfRoom);
      } catch (e) {}
    }

    if (nextDocRoom && nextDocRoom !== currentDocRoom) {
      try {
        frappe.realtime.subscribe(nextDocRoom);
      } catch (e) {}
    }

    currentPfRoom = nextPfRoom;
    currentDocRoom = nextDocRoom;
  }

  if (frappe.realtime) {
    setup_realtime_subscription();

    if (frappe.realtime.off) frappe.realtime.off(RT_EVENT);

    frappe.realtime.on(RT_EVENT, (data) => {
      if (!data || !data.name) return;

      if (data.__action === "remove") {
        remove_card(data.name);
        return;
      }

      if (data.__lite) {
        const st = (data.status || "").trim();
        const isCompleted = cint(data.docstatus) === 1 || st === "Completed";
        const isPaused = cint(data.is_paused) === 1 || st === "On Hold";

        if (isCompleted || isPaused) {
          const mins = flt(data.total_time_in_mins || 0);
          data.timer_seconds = Math.round(mins * 60);
          data.expected_seconds = 0;
          data.is_overdue = 0;
          data.is_completed = isCompleted ? 1 : 0;
          data.running = 0;
          markDirty(data.name);
          return;
        }

        markDirty(data.name);
        return;
      }

      update_single_card(data);
    });
  }

  // -------------------------
  // Fallback poll
  // -------------------------
  let pollTimer = null;
  let pollInFlight = false;

  async function poll_visible_cards() {
    if (pollInFlight) return;
    pollInFlight = true;

    try {
      const names = [];
      grid.find(".jc-card[data-name]").each(function () {
        const n = $(this).attr("data-name");
        if (n) names.push(n);
      });

      const sample = names.slice(0, 80);
      if (!sample.length) return;

      const cards = await fetch_card_payload_bulk(sample);
      for (const c of cards) update_single_card(c);
    } catch (e) {
    } finally {
      pollInFlight = false;
    }
  }

  function start_poll() {
    if (pollTimer) return;
    pollTimer = setInterval(() => poll_visible_cards(), 12000);
  }

  function stop_poll() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    pollInFlight = false;
  }

  const pollRaw = (urlParams.get("poll") || "").trim().toLowerCase();
  const pollOnValues = new Set(["on", "1", "true", "yes"]);
  const pollEnabled = pollOnValues.has(pollRaw);
  if (pollEnabled) start_poll();

  // -------------------------
  // Rendering
  // -------------------------
  function get_badge_class(status) {
    switch (status) {
      case "Completed":
        return "badge-success";
      case "On Hold":
        return "badge-warning";
      case "Work In Progress":
        return "badge-info";
      case "Material Transferred":
        return "badge-info";
      default:
        return "badge-light";
    }
  }

  function render_actions(d) {
    if (IS_WALL) return "";

    const planned = flt(d.planned) || flt(d.for_quantity) || 0;
    const done = flt(d.done) || flt(d.total_completed_qty) || 0;
    const remaining = Math.max(planned - done, 0);

    const paused = String(d.status || "") === "On Hold" || cint(d.is_paused) === 1;
    const running = cint(d.running) === 1 && !paused;
    const is_submitted = cint(d.docstatus) === 1;

    const wo_status = String(d.work_order_status || "").trim();
    const wo_docstatus = cint(d.work_order_docstatus || 0);
    const wo_closed =
      cint(d.hide_actions_due_to_wo_closed) === 1 ||
      wo_docstatus === 2 ||
      ["Closed", "Completed", "Cancelled"].includes(wo_status);

    if (is_submitted || wo_closed) return "";

    if (paused) {
      return `<button type="button" class="btn btn-primary btn-sm" data-cmd="resume" data-name="${d.name}">${__("Resume Job")}</button>`;
    }

    if (running) {
      return `
        <button type="button" class="btn btn-default btn-sm" data-cmd="pause" data-name="${d.name}">${__("Pause Job")}</button>
        <button type="button" class="btn btn-primary btn-sm" data-cmd="complete" data-name="${d.name}">${__("Complete Job")}</button>
      `;
    }

    if (planned && remaining <= 0) {
      return `<button type="button" class="btn btn-primary btn-sm" data-cmd="submit" data-name="${d.name}">${__("Submit")}</button>`;
    }

    return `<button type="button" class="btn btn-primary btn-sm" data-cmd="start" data-name="${d.name}">${__("Start Job")}</button>`;
  }

  function render_extra(d) {
    const pf = String(d.taj_plant_floor || d.plant_floor || "").trim();
    const isSubmitted = cint(d.docstatus) === 1;

    let label = "";
    let val = 0;

    if (pf === "Preparation Area") {
      label = __("RM Used Qty");
      val = flt(d.taj_rm_used_qty || 0);
    } else if (pf === "Cooking Area") {
      label = __("Total Weight");
      val = flt(d.taj_total_weight || 0);
    } else {
      return "";
    }

    const shouldShow = isSubmitted || Math.abs(val) > 0.000001;
    if (!shouldShow) return "";

    return `
      <div class="jc-extra" data-pf="${pf}">
        <span class="lbl">${label}</span>
        <span class="eq">=</span>
        <span class="val">${format_qty(val)}</span>
      </div>
    `;
  }

  function render_card(d) {
    const planned = flt(d.planned) || flt(d.for_quantity) || 0;
    const done = flt(d.done) || flt(d.total_completed_qty) || 0;
    const remaining = flt(d.remaining) || Math.max(planned - done, 0);
    const pct = planned ? Math.min((done / planned) * 100, 100) : 0;

    const paused = String(d.status || "") === "On Hold" || cint(d.is_paused) === 1;
    const running = cint(d.running) === 1 && !paused;

    const isCompleted =
      cint(d.is_completed) === 1 ||
      cint(d.is_finished_qty) === 1 ||
      cint(d.docstatus) === 1;

    const isCooking = cint(d.is_cooking_mode) === 1;

    const stateClass = paused
      ? "state-paused"
      : running
      ? "state-running"
      : "state-idle";

    const idleStatusClass = !paused && !running ? `idle-${slug_status(d.status)}` : "";

    const showSubmit =
      !paused &&
      !running &&
      planned &&
      remaining <= 0 &&
      cint(d.docstatus) === 0;

    const wipBlink =
      !paused &&
      !running &&
      d.status === "Work In Progress" &&
      remaining > 0 &&
      !showSubmit
        ? "state-wip"
        : "";

    const overdueClass =
      cint(d.is_overdue) === 1 && !isCompleted && !paused ? "is-overdue" : "";

    const badgeClass = get_badge_class(d.status);
    const timerSeconds = cint(d.timer_seconds || 0);
    const expectedSeconds = cint(d.expected_seconds || 0);
    const seq = cint(d.wo_op_seq || 0);

    const showCookItemsBtn =
      String(d.plant_floor || "").trim() === "Cooking Area" &&
      !!String(d.operation || "").trim();

    const showPrepPrintBtn =
      String(d.taj_plant_floor || d.plant_floor || "").trim() === "Preparation Area" &&
      !!String(d.work_order || "").trim();

    return $(`
      <div class="jc-card ${stateClass} ${idleStatusClass} ${wipBlink} ${overdueClass} ${
      isMuted(d.name) ? "is-muted" : ""
    } ${isCooking ? "mode-cooking" : ""}"
           data-name="${d.name}"
           data-wo="${d.work_order || ""}"
           data-op="${d.operation || ""}"
           data-docstatus="${cint(d.docstatus || 0)}"
           data-completed="${isCompleted ? 1 : 0}">
        <div>
          <div class="jc-head">
            <div class="jc-left">
              <div class="jc-title jc-title-row">
                <div class="jc-title-main">
                  <span class="jc-seq">${seq ? `${seq}# ` : ""}</span>
                  <a class="jc-title-link" href="/app/job-card/${d.name}" target="_blank">${d.name}</a>
                </div>

                <div class="jc-title-actions">
                  ${
                    d.operation
                      ? `<button type="button"
                           class="btn btn-default btn-xs jc-mini-btn jc-spec-btn"
                           data-name="${d.name}"
                           title="${__("View Operation Specs")}">ⓘ</button>`
                      : ""
                  }

                  ${
                    showPrepPrintBtn
                      ? `<button type="button"
                           class="btn btn-default btn-xs jc-mini-btn jc-prep-print-btn"
                           data-name="${d.name}"
                           title="${__("Cooking Label")}">🖨️</button>`
                      : ""
                  }

                  ${
                    showCookItemsBtn
                      ? `<button type="button"
                           class="btn btn-default btn-xs jc-mini-btn jc-cook-req-btn"
                           data-name="${d.name}"
                           title="${__("View Cooking Items")}">📋</button>`
                      : ""
                  }
                </div>
              </div>

              <div class="jc-meta">
                <div>${__("Item")}: ${d.item_name || d.item_code || "-"}</div>
                <div>${__("WS")}: ${d.workstation || "-"}</div>
                <div>${__("Op")}: ${d.operation || "-"}</div>
              </div>
            </div>

            <div class="jc-right">
              <div class="jc-top-right">
                ${
                  IS_WALL
                    ? ""
                    : `<button type="button" class="btn btn-default btn-xs jc-mute" data-name="${d.name}" title="${__("Mute")}">
                        ${isMuted(d.name) ? "🔕" : "🔔"}
                       </button>`
                }
                <div class="jc-timer" data-seconds="${timerSeconds}" data-expected="${expectedSeconds}">
                  ${format_hms(timerSeconds)}
                </div>
              </div>

              <div class="jc-badges">
                <span class="badge ${badgeClass}">${__(d.status || "")}</span>
              </div>
            </div>
          </div>

          ${
            isCooking
              ? `
            <div class="jc-cooking-center">
              <div class="jc-cooking-ws">${d.workstation || "-"}</div>
              <div class="jc-cooking-op">${d.operation || "-"}</div>
            </div>
          `
              : `
            <div class="jc-kpis">
              <div class="jc-kpi"><div class="lbl">${__("Planned")}</div><div class="val">${format_qty(planned)}</div></div>
              <div class="jc-kpi"><div class="lbl">${__("Done")}</div><div class="val">${format_qty(done)}</div></div>
              <div class="jc-kpi"><div class="lbl">${__("Remaining")}</div><div class="val">${format_qty(remaining)}</div></div>
            </div>

            <div class="jc-progress">
              <div class="pct"><span>${__("Progress")}</span><b>${pct.toFixed(1)}%</b></div>
              <div class="bar"><div class="fill" style="width:${pct.toFixed(1)}%"></div></div>
            </div>
          `
          }
        </div>

        <div class="jc-actions">
          ${render_actions(d)}
          <a class="btn btn-default btn-sm" href="/app/job-card/${d.name}" target="_blank">${__("Open")}</a>
        </div>

        ${render_extra(d)}
      </div>
    `);
  }

  // -------------------------
  // Create Batch
  // -------------------------
  async function start_job_with_batch_guard(name) {
    const doc = await frappe
      .call({
        method: "frappe.client.get",
        args: { doctype: "Job Card", name },
      })
      .then((r) => r.message || {});

    const plant_floor = String(doc.taj_plant_floor || "").trim();

    if (plant_floor !== "Retort Area") {
      return start_job(name);
    }

    if (doc.taj_batch_id) {
      return start_job(name);
    }

    return show_batch_before_start_dialog(name, doc);
  }


  async function show_batch_before_start_dialog(name, doc) {
    const r = await frappe.call({
      method: "taj_job_card_batch_action",
      args: {
        action: "preview",
        job_card: name
      },
      freeze: true,
      freeze_message: __("Preparing Batch ID...")
    });

    const proposed_batch_id = r.message && r.message.batch_id;

    if (!proposed_batch_id) {
      frappe.msgprint({
        title: __("Batch Required"),
        message: __("No Batch ID could be proposed."),
        indicator: "orange"
      });
      return;
    }

    const dialog = new frappe.ui.Dialog({
      title: __("Batch Required Before Start"),
      fields: [
        {
          fieldname: "batch_note",
          fieldtype: "HTML",
          options: `
            <div style="padding:12px; border:1px solid #e5e7eb; border-radius:10px; background:#f8fafc; margin-bottom:10px;">
              <div style="font-size:13px; color:#6b7280; margin-bottom:6px;">
                ${__("This Job Card requires a Batch before starting. Review or edit the Batch ID.")}
              </div>
              <div style="font-size:12px; color:#6b7280;">
                <b>${__("Job Card")}:</b> ${frappe.utils.escape_html(name)}<br>
                <b>${__("Production Item")}:</b> ${frappe.utils.escape_html(doc.production_item || doc.item_code || "")}<br>
                <b>${__("Workstation")}:</b> ${frappe.utils.escape_html(doc.workstation || "")}
              </div>
            </div>
          `
        },
        {
          label: __("Batch ID"),
          fieldname: "batch_id",
          fieldtype: "Data",
          default: proposed_batch_id,
          reqd: 1,
          description: __("If you are in a hurry, keep the suggested number and press Create Batch & Start Job.")
        }
      ],
      primary_action_label: __("Create Batch & Start Job"),
      primary_action: async function (values) {
        const final_batch_id = String(values.batch_id || "").trim();

        if (!final_batch_id) {
          frappe.msgprint({
            title: __("Missing Batch ID"),
            message: __("Batch ID is required."),
            indicator: "red"
          });
          return;
        }

        try {
          dialog.set_primary_action(__("Working..."), function () {});
          dialog.get_primary_btn().prop("disabled", true);

          await frappe.call({
            method: "taj_job_card_batch_action",
            args: {
              action: "create",
              job_card: name,
              batch_id: final_batch_id
            },
            freeze: true,
            freeze_message: __("Creating Batch...")
          });

          dialog.hide();

          frappe.show_alert({
            message: __("Batch created: {0}", [final_batch_id]),
            indicator: "green"
          });

          return start_job(name);

        } catch (e) {
          dialog.get_primary_btn().prop("disabled", false);
          dialog.set_primary_action(__("Create Batch & Start Job"), async function () {
            const values = dialog.get_values() || {};
            dialog.primary_action(values);
          });
        }
      }
    });

    dialog.show();

    setTimeout(() => {
      const field = dialog.fields_dict.batch_id;
      if (field && field.$input) {
        field.$input.focus();
        field.$input.select();
      }
    }, 300);
  }

  // -------------------------
  // Actions
  // -------------------------
  async function start_job(name) {
    const doc = await frappe
      .call({
        method: "frappe.client.get",
        args: { doctype: "Job Card", name },
      })
      .then((r) => r.message);

    const existing = (doc.employee || []).map((r) => r.employee).filter(Boolean);
    const company = doc?.company || null;
    const req = await get_start_requirements(name);
    const needsDialog =
      cint(req?.enabled) === 1 &&
      String(req?.plant_floor || "").trim() === "Filling Area" &&
      cint(req?.needs_metal_detector) === 1;
    const showLiquidFields = cint(req?.show_liquid_fields || 0) === 1;
    const currentValues = req?.values || {};

    const employeeField = {
      fieldtype: "MultiSelectList",
      fieldname: "employees",
      label: __("Select Employees"),
      reqd: 1,
      get_data: function (txt) {
        const filters = { status: "Active" };
        if (company) filters.company = company;

        return frappe
          .call({
            method: "frappe.desk.search.search_link",
            args: {
              doctype: "Employee",
              txt: txt || "",
              filters,
              page_length: 20,
            },
          })
          .then((r) => r.message || []);
      },
    };

    const requiredFieldLabels = () => {
      const labels = [
        ["taj_check_weight_1", __("Check Weight #1")],
        ["taj_anritus_weight_1", __("Anritus Weight #1")],
        ["taj_check_weight_2", __("Check Weight #2")],
        ["taj_anritus_weight_2", __("Anritus Weight #2")],
      ];

      if (showLiquidFields) {
        labels.push(
          ["taj_ferrous_detection", __("Ferrous Detection 2mm")],
          ["taj_non_ferrous_detection", __("Non Ferrous Detection 2mm")],
          ["taj_sus_detection", __("SUS Detection 2mm")],
          ["taj_threshold_set_point", __("Threshold set point")],
          ["taj_gain_set_point", __("Gain Set point")]
        );
      }

      return labels;
    };

    const getMissingRequiredLabels = (values = {}) => {
      const missing = [];

      for (const [fieldname, label] of requiredFieldLabels()) {
        if (
          fieldname === "taj_ferrous_detection" ||
          fieldname === "taj_non_ferrous_detection" ||
          fieldname === "taj_sus_detection"
        ) {
          if (!cint(values[fieldname] || 0)) missing.push(label);
        } else {
          if (flt(values[fieldname] || 0) === 0) missing.push(label);
        }
      }

      return missing;
    };

    const baseArgsFromValues = (values = {}) => ({
      job_card: name,
      taj_check_weight_1: values.taj_check_weight_1,
      taj_anritus_weight_1: values.taj_anritus_weight_1,
      taj_check_weight_2: values.taj_check_weight_2,
      taj_anritus_weight_2: values.taj_anritus_weight_2,
      taj_ferrous_detection: values.taj_ferrous_detection,
      taj_non_ferrous_detection: values.taj_non_ferrous_detection,
      taj_sus_detection: values.taj_sus_detection,
      taj_threshold_set_point: values.taj_threshold_set_point,
      taj_gain_set_point: values.taj_gain_set_point,
    });

    const saveChecks = async (values = {}, hideAlert = false) => {
      const r = await frappe.call({
        method: "taj_core.taj_core.page.job_card_board.job_card_board.save_metal_detector_checks",
        args: baseArgsFromValues(values),
        freeze: true,
        freeze_message: __("Saving checks..."),
      });

      if (!hideAlert) {
        frappe.show_alert({
          message: __("Checks saved"),
          indicator: "green",
        });
      }

      return r.message || {};
    };

    const do_start = async (emp_ids, values = {}) => {
      const employees = (emp_ids || []).map((emp) => ({ employee: emp }));
      if (!employees.length) {
        frappe.msgprint({
          message: __("Please select at least one employee."),
          indicator: "orange",
        });
        return false;
      }

      const r = await call_api("board_start_job", {
        ...baseArgsFromValues(values),
        job_card: name,
        employees,
      });

      if (r.message?.card) update_single_card(r.message.card);
      else markDirty(name);

      return true;
    };

    if (existing.length && !needsDialog) {
      return do_start(existing);
    }

    if (!needsDialog) {
      return frappe.prompt(
        [employeeField],
        async (d) => {
          await do_start(d.employees || []);
        },
        __("Assign Job to Employee"),
        __("Start Job")
      );
    }

    const fields = [];

    if (!existing.length) {
      fields.push(employeeField);
    }

    fields.push({
      fieldtype: "HTML",
      fieldname: "metal_detector_note",
      options: `
        <div style="margin-bottom:8px; font-size:12px; color:#6b7280; line-height:1.7;">
          ${__("Filling Area checks. Save partial values any time. Start will continue only after the required fields are complete.")}
        </div>
      `,
    });

    fields.push({
      fieldtype: "Section Break",
      fieldname: "always_fields_section",
      label: __("Always Visible Fields"),
    });

    fields.push(
      {
        fieldtype: "Int",
        fieldname: "taj_check_weight_1",
        label: __("Check Weight #1"),
        default: cint(currentValues.taj_check_weight_1 || 0),
      },
      {
        fieldtype: "Float",
        fieldname: "taj_anritus_weight_1",
        label: __("Anritus Weight #1"),
        default: flt(currentValues.taj_anritus_weight_1 || 0),
      },
      {
        fieldtype: "Column Break",
        fieldname: "md_col_break_1",
      },
      {
        fieldtype: "Int",
        fieldname: "taj_check_weight_2",
        label: __("Check Weight #2"),
        default: cint(currentValues.taj_check_weight_2 || 0),
      },
      {
        fieldtype: "Int",
        fieldname: "taj_anritus_weight_2",
        label: __("Anritus Weight #2"),
        default: cint(currentValues.taj_anritus_weight_2 || 0),
      }
    );

    if (showLiquidFields) {
      fields.push(
        {
          fieldtype: "Section Break",
          fieldname: "liquid_fields_section",
          label: __("Liquid Fields"),
        },
        {
          fieldtype: "Check",
          fieldname: "taj_ferrous_detection",
          label: __("Ferrous Detection 2mm"),
          default: cint(currentValues.taj_ferrous_detection || 0),
        },
        {
          fieldtype: "Check",
          fieldname: "taj_non_ferrous_detection",
          label: __("Non Ferrous Detection 2mm"),
          default: cint(currentValues.taj_non_ferrous_detection || 0),
        },
        {
          fieldtype: "Check",
          fieldname: "taj_sus_detection",
          label: __("SUS Detection 2mm"),
          default: cint(currentValues.taj_sus_detection || 0),
        },
        {
          fieldtype: "Column Break",
          fieldname: "md_col_break_2",
        },
        {
          fieldtype: "Float",
          fieldname: "taj_threshold_set_point",
          label: __("Threshold set point"),
          default: flt(currentValues.taj_threshold_set_point || 0),
        },
        {
          fieldtype: "Float",
          fieldname: "taj_gain_set_point",
          label: __("Gain Set point"),
          default: flt(currentValues.taj_gain_set_point || 0),
        }
      );
    }

    fields.push({
      fieldtype: "Button",
      fieldname: "save_only",
      label: __("Save"),
    });

    const dialog = new frappe.ui.Dialog({
      title: __("Filling Start Check"),
      fields,
      primary_action_label: __("Start Job"),
      primary_action: async () => {
        const values = dialog.get_values() || {};
        const empIds = existing.length ? existing : (values.employees || []);

        await saveChecks(values, true);

        const missing = getMissingRequiredLabels(values);
        if (missing.length) {
          frappe.msgprint({
            title: __("Metal Detector Check"),
            message: __("Saved current values. Still required before Start: {0}", [missing.join(", ")]),
            indicator: "orange",
          });
          return;
        }

        const ok = await do_start(empIds, values);
        if (ok) dialog.hide();
      },
    });

    dialog.show();

    const saveBtn =
      dialog.fields_dict.save_only?.$input || dialog.fields_dict.save_only?.input;

    if (saveBtn) {
      $(saveBtn).off("click").on("click", async () => {
        const values = dialog.get_values() || {};
        await saveChecks(values, false);
        dialog.hide();
      });
    }
  }

  async function pause_job(name) {
    const r = await call_api("board_pause_job", { job_card: name });
    if (r.message?.card) update_single_card(r.message.card);
    else markDirty(name);
  }

  async function resume_job(name) {
    const r = await call_api("board_resume_job", { job_card: name });
    if (r.message?.card) update_single_card(r.message.card);
    else markDirty(name);
  }

  async function complete_job(name) {
    const one = (await fetch_card_payload_bulk([name]))[0];
    const planned = flt(one?.for_quantity || one?.planned || 0) || 0;
    const done = flt(one?.total_completed_qty || one?.done || 0) || 0;
    const remaining_default = Math.max(planned - done, 0);

    const jc = await frappe
      .call({
        method: "frappe.client.get",
        args: { doctype: "Job Card", name },
      })
      .then((r) => r.message || {});

    const operation_name = jc?.operation || "";

    let requires_temperature = 0;

    if (operation_name) {
      try {
        const op = await frappe
          .call({
            method: "frappe.client.get",
            args: { doctype: "Operation", name: operation_name },
          })
          .then((r) => r.message || {});

        requires_temperature = cint(op?.taj_requires_temperature || 0);
      } catch (e) {
        requires_temperature = 0;
      }
    }

    const fields = [
      {
        fieldtype: "Float",
        label: __("Completed Quantity"),
        fieldname: "completed_qty",
        reqd: 1,
        default: remaining_default,
      },
    ];

    if (requires_temperature) {
      fields.push({
        fieldtype: "Float",
        label: __("Temperature"),
        fieldname: "taj_temperature",
        reqd: 1,
      });
    }

    frappe.prompt(
      fields,
      async (d) => {
        const r = await call_api("board_complete_job", {
          job_card: name,
          qty: d.completed_qty,
          taj_temperature: d.taj_temperature,
        });

        if (r.message?.card) update_single_card(r.message.card);
        else markDirty(name);
      },
      __("Complete Job"),
      __("Update")
    );
  }

  async function submit_job(name) {
    const cur = (await fetch_card_payload_bulk([name]))[0];
    if (!cur) return;

    const completed = flt(cur.total_completed_qty || cur.done || 0);
    const planned_now = flt(cur.for_quantity || cur.planned || 0);
    const pf = String(cur.plant_floor || "").trim();

    if (cint(cur.docstatus) === 1) return;

    const fq_default = planned_now && planned_now > 0 ? planned_now : completed;
    const hide_qty_fields = Math.abs(fq_default - completed) < 0.000001;

    const fields = [];

    fields.push({
      fieldtype: "Int",
      fieldname: "taj_manpower_used",
      label: __("Manpower"),
      reqd: 1,
      default: 1,
    });

    if (pf === "Cooking Area") {
      fields.push({
        fieldtype: "Float",
        fieldname: "taj_total_weight",
        label: __("Total Weight"),
        reqd: 1,
        default: flt(cur.taj_total_weight || 0),
      });
    }

    if (pf === "Preparation Area") {
      fields.push({
        fieldtype: "Float",
        fieldname: "taj_rm_used_qty",
        label: __("RM Used Qty"),
        reqd: 1,
        default: flt(cur.taj_rm_used_qty || 0),
      });
    }

    if (hide_qty_fields) {
      fields.push(
        {
          fieldtype: "Float",
          fieldname: "for_quantity",
          label: __("Qty to Manufacture"),
          reqd: 1,
          hidden: 1,
          default: fq_default,
        },
        {
          fieldtype: "Float",
          fieldname: "completed_qty",
          label: __("Completed Qty"),
          reqd: 1,
          hidden: 1,
          default: completed,
        },
        {
          fieldtype: "Float",
          fieldname: "process_loss_qty",
          label: __("Process Loss Qty"),
          read_only: 1,
          hidden: 1,
          default: 0,
        }
      );
    } else {
      fields.push(
        {
          fieldtype: "Float",
          fieldname: "for_quantity",
          label: __("Qty to Manufacture"),
          reqd: 1,
          default: planned_now || completed,
          change() {
            let fq = flt(dialog.get_value("for_quantity") || 0);
            if (fq < completed) {
              fq = completed;
              dialog.set_value("for_quantity", fq);
              frappe.show_alert({
                message: __("Qty to Manufacture cannot be less than Completed Qty"),
                indicator: "orange",
              });
            }
            dialog.set_value("completed_qty", completed);
            dialog.set_value("process_loss_qty", Math.max(fq - completed, 0));
          },
        },
        {
          fieldtype: "Float",
          fieldname: "completed_qty",
          label: __("Completed Qty"),
          read_only: 0,
          reqd: 1,
          default: completed,
        },
        {
          fieldtype: "Float",
          fieldname: "process_loss_qty",
          label: __("Process Loss Qty"),
          read_only: 1,
          default: Math.max((planned_now || 0) - completed, 0),
        }
      );
    }

    let dialog = null;

    dialog = frappe.prompt(
      fields,
      async (v) => {
        const fq = flt(v.for_quantity || 0);
        if (fq < completed) {
          frappe.msgprint({
            message: __("Qty to Manufacture cannot be less than Completed Qty"),
            indicator: "red",
          });
          return;
        }

        const loss = Math.max(fq - completed, 0);

        const args = {
          job_card: name,
          for_quantity: fq,
          confirm_loss: loss > 0 ? 1 : 0,
          taj_manpower_used: cint(v.taj_manpower_used || 0),
          taj_total_weight: v.taj_total_weight,
          taj_rm_used_qty: v.taj_rm_used_qty,
        };

        const do_submit = async () => {
          const r = await call_api("board_submit_job", args);
          if (r.message?.card) update_single_card(r.message.card);
          else markDirty(name);
        };

        if (loss > 0) {
          frappe.confirm(
            __(
              "Qty to Manufacture = {0}<br>Completed = {1}<br>Process Loss = {2}<br><br>The difference will be treated as process loss. Continue?",
              [format_number(fq), format_number(completed), format_number(loss)]
            ),
            async () => do_submit()
          );
        } else {
          await do_submit();
        }
      },
      __("Submit Job Card"),
      __("Submit")
    );

    setTimeout(() => {
      const $w = dialog.$wrapper;

      function normalizeNumber(v) {
        if (v == null) return v;
        v = String(v);

        const map = {
          "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
          "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
          "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
          "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
        };
        v = v.replace(/[٠-٩۰-۹]/g, (d) => map[d] || d);
        v = v.replace(/,/g, ".");
        v = v.replace(/\u066B/g, ".");
        return v;
      }

      function commitValue($inp) {
        const $ctrl = $inp.closest(".frappe-control");
        const fieldname = $ctrl.attr("data-fieldname");
        if (!fieldname) return;

        let raw = $inp.val();
        raw = normalizeNumber(raw);

        dialog.set_value(fieldname, raw);
        $inp.trigger("input");
        $inp.trigger("change");
        $inp.blur();
      }

      $w.on("keydown.jc_enter_fix", "input, textarea, select", function (e) {
        const isEnter = e.key === "Enter" || e.keyCode === 13 || e.which === 13;
        if (!isEnter) return;

        e.preventDefault();
        e.stopPropagation();

        const $inp = $(this);
        commitValue($inp);

        const $focusables = $w.find("input, textarea, select").filter(":visible:enabled:not([readonly])");

        const idx = $focusables.index(this);
        const hasNext = idx >= 0 && idx < $focusables.length - 1;

        if (hasNext) {
          setTimeout(() => $focusables.eq(idx + 1).focus(), 0);
        } else {
          setTimeout(() => dialog.get_primary_btn().trigger("click"), 0);
        }

        return false;
      });

      dialog.onhide = () => {
        try {
          $w.off("keydown.jc_enter_fix");
        } catch (e) {}
      };
    }, 0);

    if (!hide_qty_fields) dialog.trigger("for_quantity");
  }

  // -------------------------
  // Events
  // -------------------------
  $(page.body).on("click.jcboard", ".jc-mute", function (e) {
    e.preventDefault();
    e.stopPropagation();
    toggleMute($(this).attr("data-name"));
  });

  $(page.body).on("click.jcboard", ".jc-spec-btn", async function (e) {
    e.preventDefault();
    e.stopPropagation();

    const btn = $(this);
    const name = btn.attr("data-name");
    if (!name) return;

    try {
      btn.prop("disabled", true);
      const data = await get_operation_spec(name);
      show_operation_spec_popup(data);
    } catch (err) {
      frappe.msgprint({
        title: __("Operation Specs"),
        message: err?.message || __("Unable to load operation description."),
        indicator: "red",
      });
    } finally {
      btn.prop("disabled", false);
    }
  });

  $(page.body).on("click.jcboard", ".jc-prep-print-btn", async function (e) {
    e.preventDefault();
    e.stopPropagation();

    const btn = $(this);
    const name = btn.attr("data-name");
    if (!name) return;

    try {
      btn.prop("disabled", true);
      await print_preparation_label(name);
    } finally {
      btn.prop("disabled", false);
    }
  });

  $(page.body).on("click.jcboard", ".jc-cook-req-btn", async function (e) {
    e.preventDefault();
    e.stopPropagation();

    const btn = $(this);
    const name = btn.attr("data-name");
    if (!name) return;

    try {
      btn.prop("disabled", true);
      const data = await get_cooking_operation_items(name);
      show_cooking_operation_items_popup(data);
    } catch (err) {
      frappe.msgprint({
        title: __("Cooking Items"),
        message: err?.message || __("Unable to load cooking items."),
        indicator: "red",
      });
    } finally {
      btn.prop("disabled", false);
    }
  });

  $(page.body).on("click.jcboard", ".jc-actions button[data-cmd]", async function () {
    if (IS_WALL) return;

    const cmd = $(this).attr("data-cmd");
    const name = $(this).attr("data-name");

    if (cmd === "start") return start_job_with_batch_guard(name);
    if (cmd === "pause") return pause_job(name);
    if (cmd === "resume") return resume_job(name);
    if (cmd === "complete") return complete_job(name);
    if (cmd === "submit") return submit_job(name);
  });

  // -------------------------
  // Load cards
  // -------------------------
  async function load_cards(reset) {
    if (state.loading) return;
    state.loading = true;

    if (reset) {
      state.offset = 0;
      grid.empty();
      stopTimerTicker();
      stopAlarm();
    }

    ensure_today_dates_in_fields();
    const { df, dt } = get_dates_for_api();

    try {
      const r = await frappe.call({
        method: "taj_core.taj_core.page.job_card_board.job_card_board.get_board_data",
        args: {
          plant_floor: f_plant_floor.get_value(),
          work_order: f_work_order.get_value(),
          workstation: f_workstation.get_value(),
          operation: f_operation.get_value(),
          status_filter: f_status.get_value(),
          docstatus_filter: f_docstatus.get_value(),
          search: f_search.get_value(),
          date_from: df,
          date_to: dt,
          limit: state.limit,
          offset: state.offset,
        },
        freeze: reset && !IS_WALL,
      });

      const items = r.message?.items || [];
      if (!items.length) {
        if (reset) grid.append(`<div class="text-muted">${__("No Job Cards found.")}</div>`);
        return;
      }

      for (const d of items) insert_card_sorted(render_card(d), d.name);
      state.offset += state.limit;

      startTimerTickerIfNeeded();
      refresh_alarm_state();
    } catch (e) {
      if (!IS_WALL) {
        frappe.msgprint({ title: __("Error"), message: e?.message || e, indicator: "red" });
      }
    } finally {
      state.loading = false;
    }
  }

  function refresh_board() {
    load_cards(true);
  }

  // -------------------------
  // Cleanup
  // -------------------------
  function destroy_board() {
    stop_poll();
    stopTimerTicker();
    stopAlarm();

    if (dirtyTimer) {
      clearTimeout(dirtyTimer);
      dirtyTimer = null;
    }
    dirtyNames.clear();

    if (currentPfRoom && frappe.realtime?.unsubscribe) {
      try {
        frappe.realtime.unsubscribe(currentPfRoom);
      } catch (e) {}
    }
    currentPfRoom = null;

    if (currentDocRoom && frappe.realtime?.unsubscribe) {
      try {
        frappe.realtime.unsubscribe(currentDocRoom);
      } catch (e) {}
    }
    currentDocRoom = null;

    try {
      $(page.body).off(".jcboard");
    } catch (e) {}

    try {
      $filterToggleBtn.off("click");
    } catch (e) {}

    try {
      window.removeEventListener("resize", handleResponsiveFilters);
      window.removeEventListener("orientationchange", handleResponsiveFilters);
    } catch (e) {}

    if (frappe.realtime?.off) {
      try {
        frappe.realtime.off(RT_EVENT);
      } catch (e) {}
    }
  }

  // -------------------------
  // Init
  // -------------------------
  ensure_today_dates_in_fields();
  setup_realtime_subscription();
  syncFiltersUI(false);
  load_cards(true);

  wrapper.__jc_destroy = destroy_board;
};

frappe.pages["job-card-board"].on_page_hide = function (wrapper) {
  $(document.body).removeClass("full-width");
  try {
    if (wrapper && wrapper.__jc_destroy) wrapper.__jc_destroy();
  } catch (e) {}
};