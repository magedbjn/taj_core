/* Add a QR print action to submitted stock Pick Lists; no document write. */
frappe.ui.form.on("Pick List", {
  refresh(frm) {
    if (frm.doc.docstatus !== 1 || frm.doc.purpose === "Delivery") return;
    frm.add_custom_button(__("Pick List Receiving QR"), async () => {
      const url = new URL("/app/pick-list-receiving", window.location.origin);
      url.searchParams.set("pl", frm.doc.name);
      const response = await frappe.call({
        method: "frappe.utils.print_format_generator.get_qr_code",
        args: { value: url.toString() },
      });
      const image = response.message;
      if (!/^data:image\/svg\+xml;base64,[a-zA-Z0-9+/=]+$/.test(image || "")) {
        frappe.throw(__("Unable to generate QR code"));
      }
      const name = frappe.utils.escape_html(frm.doc.name);
      const link = frappe.utils.escape_html(url.toString());
      const html = `<div style="text-align:center;direction:ltr">
        <img src="${image}" width="250" height="250" alt="Pick List Receiving QR" />
        <p><b>${name}</b></p>
        <p style="overflow-wrap:anywhere;font-size:11px">${link}</p>
        <p>${__("Scan to open Pick List Receiving")}</p>
      </div>`;
      frappe.msgprint({ title: __("Pick List Receiving QR"), message: html, wide: true });
    }, __("View"));
  },
});
