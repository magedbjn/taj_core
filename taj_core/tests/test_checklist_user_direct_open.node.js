const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const source = fs.readFileSync('taj_core/checklist/page/checklist_user/checklist_user.js', 'utf8');
const context = {
  console,
  frappe: {
    pages: { 'checklist-user': {} },
  },
};
vm.createContext(context);
vm.runInContext(source, context);

const pageHooks = context.frappe.pages['checklist-user'];
assert.strictEqual(typeof pageHooks.on_page_show, 'function', 'checklist-user must process route options every time the cached page is shown');

let calls = 0;
const wrapper = {
  checklist_user_page: {
    on_page_show() {
      calls += 1;
    },
  },
};
pageHooks.on_page_show(wrapper);
assert.strictEqual(calls, 1, 'on_page_show must delegate to the existing ChecklistUserPage instance');

console.log('Checklist User direct-open lifecycle tests: PASS');
