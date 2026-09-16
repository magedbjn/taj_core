const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const source = fs.readFileSync('taj_core/checklist/page/checklist_today/checklist_today.js', 'utf8');
const context = {
  console,
  frappe: {
    pages: { 'checklist-today': {} },
  },
};
vm.createContext(context);
vm.runInContext(source, context);

assert.strictEqual(vm.runInContext('format_checklist_delay(340)', context), '5h 40m');
assert.strictEqual(vm.runInContext('format_checklist_delay(45)', context), '45 min');
assert.strictEqual(vm.runInContext('format_checklist_delay(60)', context), '1h');
assert.strictEqual(vm.runInContext('format_checklist_delay(1620)', context), '1d 3h');

assert.strictEqual(
  vm.runInContext("checklist_scope_label({department: 'Production - Taj'})", context),
  'Production'
);
assert.strictEqual(
  vm.runInContext("checklist_scope_label({department: 'Quality Management - _TC'})", context),
  'Quality Management'
);
assert.strictEqual(
  vm.runInContext("checklist_scope_label({plant_floor: 'Cooking Area', department: 'Production - Taj'})", context),
  'Cooking Area'
);

console.log('Checklist Today UI helper tests: PASS');
