/* ============================================================
   job-card-board.js  (PERF + SAFE)
   - Lite realtime batching: __lite -> bulk fetch -> update cards
   - Bulk polling (single request) + no overlapping polls
   - Cleanup on page hide (no timers/poll leaks)
   - Wallboard mode: ?mode=wall  (read-only)
   - ✅ Poll default OFF. Only ON if ?poll=on
   - ✅ Realtime robustness: subscribe to doctype rooms with/without space
   - ✅ When Search is exact Job Card name => subscribe to doc room (fastest)
   - ✅ For On Hold / Completed => instant timer from total_time_in_mins (no API)
   ============================================================ */

frappe.pages["job-card-board"].on_page_load = function (wrapper) {
  $(document.body).addClass("full-width");

  const RT_EVENT = "job_card_board_update";

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

  const root = $(`<div class="jc-board"></div>`).appendTo(page.body);
  const grid = $(`<div class="jc-grid"></div>`).appendTo(root);

  
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

  // Detect decimal separator from current locale/number_format safely
  // Detect decimal separator safely (no args passed)
  const DEC_SEP = (() => {
    try {
      const s = String(format_number(1.1)); // e.g. "1.1" / "1,1" / "١٫١"
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
      // ✅ precision is 3rd arg, 2nd arg must be string/format (use null)
      s = String(format_number(n, null, max_dp));
    } catch (e) {
      // fallback
      s = String(n);
    }

    const ds = DEC_SEP;
    const esc = ds.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

    // 7.010000 -> 7.01  |  7.011000 -> 7.011
    s = s.replace(new RegExp(`(${esc}\\d*?[1-9])0+$`), "$1");
    // 7.000000 -> 7
    s = s.replace(new RegExp(`${esc}0+$`), "");
    // safety
    s = s.replace(new RegExp(`${esc}$`), "");

    return s;
  }

  // -------------------------
  // Sound / Mute (disabled in wall mode)
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
    if (now - lastBeepAt < 600) return; // prevent overlap
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
  // Timer ticker (running only)
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
      setup_realtime_subscription(); // ✅ important for doc-room subscription
      refresh_board();
    }, 350),
  });

  if (!IS_WALL) {
    page.set_primary_action(__("Refresh"), () => refresh_board(), "refresh");
    page.add_action_item(__("Load more"), () => load_cards(false));
  } else {
    // Wallboard: hide form & actions bar
    try {
      $(page.page_form).hide();
    } catch (e) {}
    try {
      $(page.page_actions).hide();
    } catch (e) {}
  }

  // -------------------------
  // Default dates => today if empty
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
  // Filter matching (for realtime updates)
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
  // DOM update (card only)
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
  // Lite realtime batching (KEY PERF)
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
    } catch (e) {
      // ignore
    }
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
    // heuristic: at least 5 chars (avoid subscribing to tiny fragments)
    if (v.length < 5) return false;
    return true;
  }

  function ensure_doctype_subscribe() {
    if (!frappe.realtime || doctypeSubscribed) return;

    // ✅ robust: subscribe to both variants
    try { frappe.realtime.subscribe("doctype: Job Card"); } catch (e) {}
    try { frappe.realtime.subscribe("doctype:Job Card"); } catch (e) {}

    doctypeSubscribed = true;
  }

  function setup_realtime_subscription() {
    ensure_doctype_subscribe();
    if (!frappe.realtime || !frappe.realtime.subscribe) return;

    const pf = (f_plant_floor.get_value() || "").trim();
    const nextPfRoom = pf ? `jc_board:pf:${roomify(pf)}` : null;

    const s = (f_search.get_value() || "").trim();
    const nextDocRoom = looks_like_job_card_name(s) ? `doc:Job Card/${s}` : null;

    // unsubscribe PF room if changed
    if (currentPfRoom && frappe.realtime.unsubscribe && currentPfRoom !== nextPfRoom) {
      try { frappe.realtime.unsubscribe(currentPfRoom); } catch (e) {}
    }

    // unsubscribe DOC room if changed
    if (currentDocRoom && frappe.realtime.unsubscribe && currentDocRoom !== nextDocRoom) {
      try { frappe.realtime.unsubscribe(currentDocRoom); } catch (e) {}
    }

    // subscribe PF room
    if (nextPfRoom && nextPfRoom !== currentPfRoom) {
      try { frappe.realtime.subscribe(nextPfRoom); } catch (e) {}
    }

    // subscribe DOC room
    if (nextDocRoom && nextDocRoom !== currentDocRoom) {
      try { frappe.realtime.subscribe(nextDocRoom); } catch (e) {}
    }

    currentPfRoom = nextPfRoom;
    currentDocRoom = nextDocRoom;
  }

  // Listen to realtime event
  if (frappe.realtime) {
    setup_realtime_subscription();

    // unique event name, safe to reset
    if (frappe.realtime.off) frappe.realtime.off(RT_EVENT);

    frappe.realtime.on(RT_EVENT, (data) => {
      if (!data || !data.name) return;

      if (data.__action === "remove") {
        remove_card(data.name);
        return;
      }

      // ✅ Lite event
      if (data.__lite) {
        const st = (data.status || "").trim();
        const isCompleted = cint(data.docstatus) === 1 || st === "Completed";
        const isPaused = cint(data.is_paused) === 1 || st === "On Hold";

        // ✅ Fast path: On Hold / Completed / Submitted
        // update instantly from total_time_in_mins WITHOUT API call
        if (isCompleted || isPaused) {
          const mins = flt(data.total_time_in_mins || 0);
          data.timer_seconds = Math.round(mins * 60);

          data.expected_seconds = 0;
          data.is_overdue = 0;
          data.is_completed = isCompleted ? 1 : 0;
          data.running = 0;

          update_single_card(data);
          return;
        }

        // otherwise, fetch full payload in batch
        markDirty(data.name);
        return;
      }

      // Full payload => update directly
      update_single_card(data);
    });
  }

  // -------------------------
  // Fallback poll: bulk sync visible cards (no overlaps)
  // (✅ Default OFF. Only ON if ?poll=on)
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
      // ignore
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

  // ✅ Poll is OFF by default; only ON if poll=on
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

    const paused =
      String(d.status || "") === "On Hold" || cint(d.is_paused) === 1;
    const running = cint(d.running) === 1 && !paused;
    const is_submitted = cint(d.docstatus) === 1;

    if (is_submitted) return "";

    if (paused) {
      return `<button type="button" class="btn btn-primary btn-sm" data-cmd="resume" data-name="${d.name}">${__(
        "Resume Job"
      )}</button>`;
    }

    if (running) {
      return `
        <button type="button" class="btn btn-default btn-sm" data-cmd="pause" data-name="${d.name}">${__(
          "Pause Job"
        )}</button>
        <button type="button" class="btn btn-primary btn-sm" data-cmd="complete" data-name="${d.name}">${__(
          "Complete Job"
        )}</button>
      `;
    }

    if (planned && remaining <= 0) {
      return `<button type="button" class="btn btn-primary btn-sm" data-cmd="submit" data-name="${d.name}">${__(
        "Submit"
      )}</button>`;
    }

    return `<button type="button" class="btn btn-primary btn-sm" data-cmd="start" data-name="${d.name}">${__(
      "Start Job"
    )}</button>`;
  }

  function render_card(d) {
    const planned = flt(d.planned) || flt(d.for_quantity) || 0;
    const done = flt(d.done) || flt(d.total_completed_qty) || 0;
    const remaining = flt(d.remaining) || Math.max(planned - done, 0);
    const pct = planned ? Math.min((done / planned) * 100, 100) : 0;

    const paused =
      String(d.status || "") === "On Hold" || cint(d.is_paused) === 1;
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

    const idleStatusClass =
      !paused && !running ? `idle-${slug_status(d.status)}` : "";

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

    return $(`
      <div class="jc-card ${stateClass} ${idleStatusClass} ${wipBlink} ${overdueClass} ${
      isMuted(d.name) ? "is-muted" : ""
    } ${isCooking ? "mode-cooking" : ""}"
           data-name="${d.name}"
           data-docstatus="${cint(d.docstatus || 0)}"
           data-completed="${isCompleted ? 1 : 0}">
        <div>
          <div class="jc-head">
            <div>
              <div class="jc-title">
                <a href="/app/job-card/${d.name}" target="_blank">${d.name}</a>
              </div>
              
              <div class="jc-meta">
                <div>${__("WS")}: ${d.workstation || "-"}</div>
                <div>${__("Op")}: ${d.operation || "-"}</div>
              </div>
              
            </div>

            <div class="jc-right">
              <div class="jc-top-right">
                ${
                  IS_WALL
                    ? ""
                    : `<button type="button" class="btn btn-default btn-xs jc-mute" data-name="${d.name}" title="${__(
                        "Mute"
                      )}">
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
              <div class="jc-kpi"><div class="lbl">${__(
                "Planned"
              )}</div><div class="val">${format_qty(planned)}</div></div>
              <div class="jc-kpi"><div class="lbl">${__(
                "Done"
              )}</div><div class="val">${format_qty(done)}</div></div>
              <div class="jc-kpi"><div class="lbl">${__(
                "Remaining"
              )}</div><div class="val">${format_qty(remaining)}</div></div>
            </div>

            <div class="jc-progress">
              <div class="pct"><span>${__("Progress")}</span><b>${pct.toFixed(
                1
              )}%</b></div>
              <div class="bar"><div class="fill" style="width:${pct.toFixed(
                1
              )}%"></div></div>
            </div>
          `
          }
        </div>

        <div class="jc-actions">
          ${render_actions(d)}
          <a class="btn btn-default btn-sm" href="/app/job-card/${d.name}" target="_blank">${__(
      "Open"
    )}</a>
        </div>
      </div>
    `);
  }

  // -------------------------
  // Actions (card-only updates)
  // -------------------------
  async function start_job(name) {
    const doc = await frappe
      .call({
        method: "frappe.client.get",
        args: { doctype: "Job Card", name },
      })
      .then((r) => r.message);

    const existing = (doc.employee || [])
      .map((r) => r.employee)
      .filter(Boolean);

    const do_start = async (emp_ids) => {
      const employees = (emp_ids || []).map((emp) => ({ employee: emp }));
      if (!employees.length) {
        frappe.msgprint({
          message: __("Please select at least one employee."),
          indicator: "orange",
        });
        return;
      }
      const r = await call_api("board_start_job", { job_card: name, employees });
      if (r.message?.card) update_single_card(r.message.card);
      else markDirty(name);
    };

    if (existing.length) return do_start(existing);

    const company = doc?.company || null;

    frappe.prompt(
      [
        {
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
        },
      ],
      async (d) => do_start(d.employees || []),
      __("Assign Job to Employee"),
      __("Start Job")
    );
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
    // fetch latest for smart default remaining
    const one = (await fetch_card_payload_bulk([name]))[0];
    const planned = flt(one?.for_quantity || one?.planned || 0) || 0;
    const done = flt(one?.total_completed_qty || one?.done || 0) || 0;
    const remaining_default = Math.max(planned - done, 0);

    frappe.prompt(
      [
        {
          fieldtype: "Float",
          label: __("Completed Quantity"),
          fieldname: "completed_qty",
          reqd: 1,
          default: remaining_default,
        },
      ],
      async (d) => {
        const r = await call_api("board_complete_job", {
          job_card: name,
          qty: d.completed_qty,
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

    // ✅ NEW: decide whether to hide qty fields
    const fq_default = (planned_now && planned_now > 0) ? planned_now : completed;
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

    // ✅ CHANGED: qty fields shown only when needed
    if (hide_qty_fields) {
      // keep them in payload but NOT visible
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
      // your existing UX (visible)
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

    // only trigger when visible fields exist (optional safety)
    if (!hide_qty_fields) dialog.trigger("for_quantity");
  }

  // -------------------------
  // Events (namespaced)
  // -------------------------
  $(page.body).on("click.jcboard", ".jc-mute", function (e) {
    e.preventDefault();
    e.stopPropagation();
    toggleMute($(this).attr("data-name"));
  });

  $(page.body).on("click.jcboard", ".jc-actions button[data-cmd]", async function () {
    if (IS_WALL) return;

    const cmd = $(this).attr("data-cmd");
    const name = $(this).attr("data-name");
    if (cmd === "start") return start_job(name);
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

    // unsubscribe PF room
    if (currentPfRoom && frappe.realtime?.unsubscribe) {
      try {
        frappe.realtime.unsubscribe(currentPfRoom);
      } catch (e) {}
    }
    currentPfRoom = null;

    // unsubscribe DOC room
    if (currentDocRoom && frappe.realtime?.unsubscribe) {
      try {
        frappe.realtime.unsubscribe(currentDocRoom);
      } catch (e) {}
    }
    currentDocRoom = null;

    // remove handlers
    try {
      $(page.body).off(".jcboard");
    } catch (e) {}

    // stop realtime listener for our event
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
  load_cards(true);

  // expose destroy to on_page_hide
  wrapper.__jc_destroy = destroy_board;
};

frappe.pages["job-card-board"].on_page_hide = function (wrapper) {
  $(document.body).removeClass("full-width");
  try {
    if (wrapper && wrapper.__jc_destroy) wrapper.__jc_destroy();
  } catch (e) {}
};