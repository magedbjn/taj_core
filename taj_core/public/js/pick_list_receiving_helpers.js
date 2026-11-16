/* Pure QR parser; never follow a scanned URL. Node-testable. */
(function (root) {
  "use strict";
  const PATH = "/app/pick-list-receiving";
  const RE = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,139}$/;
  function code(input, origin) {
    if (typeof input !== "string" || typeof origin !== "string") throw new Error("Invalid QR input");
    const value = input.trim();
    if (!value || value.length > 2048) throw new Error("Invalid QR input");
    if (!value.includes("://")) {
      if (!RE.test(value) || value === "." || value === "..") throw new Error("Invalid Pick List number");
      return value;
    }
    const url = new URL(value);
    if (!/^(https?):$/.test(url.protocol) || url.origin !== new URL(origin).origin ||
        url.pathname.replace(/\/$/, "") !== PATH || url.hash ||
        [...url.searchParams.keys()].some((key) => key !== "pl") ||
        url.searchParams.getAll("pl").length !== 1) {
      throw new Error("The QR does not belong to this Pick List Receiving site");
    }
    const name = url.searchParams.get("pl");
    if (!RE.test(name) || name === "." || name === "..") throw new Error("Invalid Pick List number");
    return name;
  }
  const api = { code, PATH };
  root.TAJ_PICK_LIST_RECEIVING_HELPERS = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
