# Product Proposal Trial, Samples, Label, and Sensory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement approved Product Proposal R&D improvements: pre-creation Planned Cooking Qty scaling and immutability, lightweight customer samples with secure direct evaluation, a 6x4 Trial thermal label, and controlled time-window Sensory visibility.

**Architecture:** Keep Trial formulation logic authoritative in `product_proposal_trial.py`, keep lightweight sample rows owned by Product Proposal, and make Sensory Feedback resolve public context server-side from either an active Trial or a non-guessable sample token. UI JavaScript only assists selection/printing; it never becomes the security or scaling authority.

**Tech Stack:** Frappe 15.119.1, ERPNext 15.120.0, Python, Frappe DocType JSON, Desk JavaScript, Web Form JavaScript, Jinja Print Format.

**Spec:** `docs/superpowers/specs/2026-09-08-product-proposal-trial-samples-sensory-design.md`

## Global Constraints

- Target Frappe / ERPNext V15.
- Baseline local production handoff commit: `cc9423e`.
- Do not change BOM lineage, Final Trial uniqueness, Trial costing valuation/conversion policy, scheduler state, or production integration.
- test1.com Scheduler must remain Disabled.
- No push unless explicitly requested.
- No destructive Git commands and never `git add .`.
- Scaling, Trial quantity immutability, sample token integrity, Trial ownership, and Sensory visibility must be enforced server-side.
- QR rendering, customer notifications, CRM opportunity creation, automatic production activation, and yield dashboards are out of scope.

---

### Task 1: Planned Cooking Qty scaling and immutable Trial identity

**Files:**
- Modify: `taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.py`
- Modify: `taj_core/rnd/doctype/product_proposal/product_proposal.js`
- Modify: `taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.js`
- Test: `taj_core/tests/test_trial_cooking.py`

**Interfaces:**
- Consumes: Product Proposal `quantity`, Product Proposal `pp_items`, previous Trial `planned_cooking_qty`, previous Trial `items`.
- Produces: `create_trial(product_proposal, source="previous", based_on_trial=None, planned_cooking_qty=None)` with server-side scaling; `_scale_snapshot_qty(source_qty, target_qty, row_qty) -> float`; immutable `planned_cooking_qty` after insert.

- [ ] **Step 1: Add failing unit tests for scaling helper and locked planned quantity**

Add tests that require:

```python
from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
    ProductProposalTrial,
    _scale_snapshot_qty,
)


def test_scale_snapshot_qty(self):
    self.assertAlmostEqual(_scale_snapshot_qty(100, 10, 50), 5)


def test_scale_snapshot_qty_rejects_zero_source(self):
    with self.assertRaises(frappe.ValidationError):
        _scale_snapshot_qty(0, 10, 50)


def test_planned_cooking_qty_is_locked_after_insert(self):
    old_doc = frappe._dict(planned_cooking_qty=10)

    class FakeTrial:
        planned_cooking_qty = 20
        product_proposal = "PP-TEST"
        trial_no = 1
        based_on_trial = None
        posting_date = "2026-09-08"
        trial_user = "Administrator"

        @staticmethod
        def get_doc_before_save():
            return old_doc

        @staticmethod
        def get(fieldname):
            return getattr(FakeTrial, fieldname, None)

    with self.assertRaises(frappe.ValidationError):
        ProductProposalTrial.validate_locked_identity(FakeTrial())
```

- [ ] **Step 2: Run targeted tests and confirm RED**

Run from bench when available:

```bash
bench --site test1.com run-tests --module taj_core.tests.test_trial_cooking
```

For the source-only mounted copy, use Python compile/static inspection only if Frappe runtime is absent. Expected RED in a real bench because `_scale_snapshot_qty` does not yet exist and `planned_cooking_qty` is not in the locked identity tuple.

- [ ] **Step 3: Implement server scaling and validation**

In `product_proposal_trial.py`:

```python
def _scale_snapshot_qty(source_qty, target_qty, row_qty):
    source_qty = flt(source_qty)
    target_qty = flt(target_qty)

    if target_qty <= 0:
        frappe.throw(_("Planned Cooking Qty must be greater than zero."))

    if source_qty <= 0:
        frappe.throw(_("Source quantity must be greater than zero to scale Trial Items."))

    return flt(row_qty) * target_qty / source_qty
```

Extend `_append_snapshot_row(..., qty=None)` so copied `qty` can be overridden without changing other snapshot fields or `line_key`.

Change `create_trial` signature to accept `planned_cooking_qty`. Validate `flt(planned_cooking_qty) > 0` before creating the Trial. For `previous`, use `base_trial.planned_cooking_qty` as source quantity. For `proposal`, use `proposal.quantity`. For `empty`, require/store target quantity but copy no rows. Scale every copied row server-side before costing and insertion.

Add `("planned_cooking_qty", "Planned Cooking Qty")` to `validate_locked_identity()`.

- [ ] **Step 4: Update Desk creation dialog and read-only UI**

In Product Proposal `create_new_trial(frm)`, add required `Planned Cooking Qty` field and pass it to `create_trial`.

In Product Proposal Trial `set_trial_snapshot_read_only(frm)`, make `planned_cooking_qty` read-only whenever `!frm.is_new()`, while keeping the remaining Draft fields editable until the Trial leaves Draft.

- [ ] **Step 5: Run targeted Trial tests and JavaScript syntax check**

```bash
bench --site test1.com run-tests --module taj_core.tests.test_trial_cooking
node --check taj_core/rnd/doctype/product_proposal/product_proposal.js
node --check taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.js
```

Expected: Trial tests GREEN and both JS files parse.

- [ ] **Step 6: Commit in real repository**

```bash
git add taj_core/tests/test_trial_cooking.py \
  taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.py \
  taj_core/rnd/doctype/product_proposal/product_proposal.js \
  taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.js
git commit -m "feat: scale product proposal trial quantities"
```

---

### Task 2: Customer Sample child table, ownership validation, and secure token

**Files:**
- Create: `taj_core/rnd/doctype/product_proposal_sample/__init__.py`
- Create: `taj_core/rnd/doctype/product_proposal_sample/product_proposal_sample.py`
- Create: `taj_core/rnd/doctype/product_proposal_sample/product_proposal_sample.json`
- Modify: `taj_core/rnd/doctype/product_proposal/product_proposal.json`
- Modify: `taj_core/rnd/doctype/product_proposal/product_proposal.py`
- Modify: `taj_core/rnd/doctype/product_proposal/product_proposal.js`
- Test: `taj_core/tests/test_trial_cooking.py`

**Interfaces:**
- Produces child fields: `customer`, `trial_document`, `sample_date`, `sample_qty`, `uom`, `interest_status`, `notes`, `evaluation_token`, `evaluation_link`.
- Produces parent methods `set_customer_sample_tokens()` and `validate_customer_samples()`.
- Token generation uses `secrets.token_urlsafe(24)` only when a row has no token; token is never regenerated on later saves.

- [ ] **Step 1: Add failing tests for token stability and Trial ownership**

Test parent helpers with lightweight rows and patched database lookups:

```python
def test_customer_sample_token_is_generated_once(self):
    row = frappe._dict(evaluation_token="")
    fake = SimpleNamespace(customer_samples=[row])
    ProductProposal.set_customer_sample_tokens(fake)
    first = row.evaluation_token
    self.assertTrue(first)
    ProductProposal.set_customer_sample_tokens(fake)
    self.assertEqual(row.evaluation_token, first)


def test_customer_sample_trial_must_belong_to_parent(self):
    row = frappe._dict(
        customer="CUST-1",
        trial_document="OTHER-TRIAL",
        sample_qty=1,
        uom="Nos",
    )
    fake = SimpleNamespace(name="PP-1", customer_samples=[row])
    with patch(
        "taj_core.rnd.doctype.product_proposal.product_proposal.frappe.db.get_value",
        return_value="PP-2",
    ):
        with self.assertRaises(frappe.ValidationError):
            ProductProposal.validate_customer_samples(fake)
```

- [ ] **Step 2: Run tests and confirm RED**

Expected RED because the sample helpers and child DocType do not exist.

- [ ] **Step 3: Create `Product Proposal Sample` child DocType**

Use `istable: 1`, module `RND`, with the approved fields. `evaluation_token` is hidden/read-only/no-copy and `evaluation_link` is a Button. `interest_status` defaults to `Pending`. `sample_date` defaults to `Today`. `sample_qty` is Float and required. `uom`, `customer`, `trial_document` are required.

- [ ] **Step 4: Add Product Proposal table and server validation**

Add `customer_samples_tab` plus `customer_samples` Table field with `allow_on_submit: 1` to Product Proposal JSON.

In Product Proposal `validate()` and `before_update_after_submit()`, call:

```python
self.set_customer_sample_tokens()
self.validate_customer_samples()
```

`validate_customer_samples()` rejects sample qty <= 0 and rejects any Trial whose `product_proposal` differs from `self.name`. Do not trust the client-side filter.

- [ ] **Step 5: Add Desk Trial filter and row evaluation action**

Register child table handlers in `product_proposal.js`:

```javascript
frappe.ui.form.on('Product Proposal Sample', {
    evaluation_link(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.evaluation_token) {
            frappe.msgprint(__('Save the Product Proposal first to generate the evaluation link.'));
            return;
        }
        const url = `${window.location.origin}/sensory-rating?sample=${encodeURIComponent(row.evaluation_token)}`;
        window.open(url, '_blank', 'noopener');
    }
});
```

Set the grid `trial_document` query to filter by the current Product Proposal.

- [ ] **Step 6: Run targeted tests, JSON parse, and JS syntax**

```bash
bench --site test1.com run-tests --module taj_core.tests.test_trial_cooking
python3 -m json.tool taj_core/rnd/doctype/product_proposal_sample/product_proposal_sample.json >/dev/null
python3 -m json.tool taj_core/rnd/doctype/product_proposal/product_proposal.json >/dev/null
node --check taj_core/rnd/doctype/product_proposal/product_proposal.js
```

- [ ] **Step 7: Commit in real repository**

Stage only the six sample-related files plus the targeted test file and commit:

```bash
git commit -m "feat: track product proposal customer samples"
```

---

### Task 3: Authoritative sample-token Sensory Feedback resolution

**Files:**
- Modify: `taj_core/rnd/doctype/sensory_feedback/sensory_feedback.json`
- Modify: `taj_core/rnd/doctype/sensory_feedback/sensory_feedback.py`
- Modify: `taj_core/rnd/web_form/sensory_rating/sensory_rating.json`
- Modify: `taj_core/rnd/web_form/sensory_rating/sensory_rating.py`
- Test: `taj_core/tests/test_trial_cooking.py`

**Interfaces:**
- Adds Sensory Feedback fields `customer` (Link / Customer, hidden/read-only) and `sample_token` (Data, hidden/read-only).
- Produces `resolve_sample_evaluation_context(sample_token) -> frappe._dict` returning `product_proposal`, `trial_document`, `customer`, `sample_name`, plus display labels.
- `SensoryFeedback.validate()` treats token context as authoritative and overwrites submitted item/trial/customer values.

- [ ] **Step 1: Add failing tests for forged-value protection**

Test that a feedback carrying a valid sample token but forged item/trial/customer is normalized to the token-owned values. Test that an unknown token raises ValidationError.

- [ ] **Step 2: Run targeted tests and confirm RED**

Expected RED because token resolution is not implemented.

- [ ] **Step 3: Implement server-side token resolver**

In `sensory_rating.py`, add `@frappe.whitelist(allow_guest=True)` resolver. Look up `Product Proposal Sample` by `evaluation_token`, then verify:

1. child row exists,
2. `parenttype == "Product Proposal"` and `parentfield == "customer_samples"`,
3. referenced Trial still belongs to the parent Product Proposal.

Return only the required context; never accept replacement item/trial/customer values from query arguments.

- [ ] **Step 4: Enforce token context in Sensory Feedback validation**

When `sample_token` exists, resolve it and assign:

```python
self.item = context.product_proposal
self.trial_document = context.trial_document
self.customer = context.customer
```

Then run the existing Trial ownership check. When there is no token, preserve current behavior and let Task 4 add active-window enforcement for public general submissions.

- [ ] **Step 5: Add fields to DocType and Web Form JSON**

Add hidden/read-only `customer` and `sample_token` fields to Sensory Feedback and hidden Web Form fields. Keep stored feedback auditable to the exact sample/customer.

- [ ] **Step 6: Run tests and JSON checks**

Expected: forged values cannot redirect the evaluation; unknown tokens fail; existing Trial ownership tests remain GREEN.

- [ ] **Step 7: Commit in real repository**

```bash
git commit -m "feat: secure sensory sample evaluation links"
```

---

### Task 4: Sensory availability window and active Trial query

**Files:**
- Modify: `taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.json`
- Modify: `taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.py`
- Modify: `taj_core/rnd/web_form/sensory_rating/sensory_rating.py`
- Modify: `taj_core/rnd/web_form/sensory_rating/sensory_rating.json`
- Modify: `taj_core/rnd/web_form/sensory_rating/sensory_rating.js`
- Modify: `taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.js`
- Test: `taj_core/tests/test_trial_cooking.py`

**Interfaces:**
- Adds Trial fields `enable_sensory_rating`, `sensory_from_date`, `sensory_until_date`.
- Produces `set_sensory_availability_defaults()` and `validate_sensory_availability()`.
- Produces guest-safe query `active_sensory_trial_query(doctype, txt, searchfield, start, page_len, filters)` returning only enabled Trials with `sensory_from_date <= today <= sensory_until_date`.
- Produces `get_trial_evaluation_context(trial_document)` that allows active Trials to Guest; authenticated users may resolve an inactive Trial only after Trial `read` permission.

- [ ] **Step 1: Add failing tests for defaults and date validation**

With `today()` patched to 2026-09-08, enabling with empty dates must set from `2026-09-08` and until `2026-12-08`. Until before From must raise ValidationError.

- [ ] **Step 2: Add failing query/security tests**

Assert the active query contains filters for `enable_sensory_rating=1`, From <= today, Until >= today. Assert Guest cannot resolve an inactive direct Trial while authenticated users require read permission.

- [ ] **Step 3: Implement Trial fields and server defaults**

Use `frappe.utils.add_months` and `getdate`. Call defaults and validation from `ProductProposalTrial.validate()` before final-trial checks. Disabling the flag leaves historical dates/feedback untouched but the Trial no longer qualifies for the active query.

- [ ] **Step 4: Make Trial the general Web Form selection authority**

In Web Form JSON:
- `trial_document` becomes visible and required with label `Product / Trial`.
- `item` remains required but is read-only; JavaScript derives it from selected Trial.
- `sample_token` and `customer` remain hidden.

In Web Form JS:
- set `trial_document.get_query` to `active_sensory_trial_query`;
- on Trial change, call `get_trial_evaluation_context` and set `item`;
- if URL contains `sample`, call `resolve_sample_evaluation_context`, set fields, and make Trial read-only;
- if URL contains `trial_document` from the authenticated Desk button, call `get_trial_evaluation_context` instead of trusting `item` in the URL.

- [ ] **Step 5: Enforce public non-token submissions server-side**

In `SensoryFeedback.validate()`, if `frappe.session.user == "Guest"` and there is no sample token, require the selected Trial to be currently enabled and within its date window. This prevents forged POST values from bypassing the filtered picker.

- [ ] **Step 6: Run targeted tests and static checks**

```bash
bench --site test1.com run-tests --module taj_core.tests.test_trial_cooking
node --check taj_core/rnd/web_form/sensory_rating/sensory_rating.js
node --check taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.js
python3 -m json.tool taj_core/rnd/web_form/sensory_rating/sensory_rating.json >/dev/null
python3 -m json.tool taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.json >/dev/null
```

- [ ] **Step 7: Commit in real repository**

```bash
git commit -m "feat: control product trial sensory availability"
```

---

### Task 5: Product Proposal Trial thermal label 6x4 and direct print action

**Files:**
- Create: `taj_core/rnd/print_format/product_proposal_trial_label_6x4/__init__.py`
- Create: `taj_core/rnd/print_format/product_proposal_trial_label_6x4/product_proposal_trial_label_6x4.json`
- Modify: `taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.js`
- Test: `taj_core/tests/test_audit_guards.py` or `taj_core/tests/test_trial_cooking.py`

**Interfaces:**
- Print Format name: `Product Proposal Trial Label 6x4`.
- DocType: `Product Proposal Trial`.
- Physical CSS: `@page { size: 6cm 4cm; margin: 1mm; }`.
- Direct button uses Frappe print route with `format=Product Proposal Trial Label 6x4`.

- [ ] **Step 1: Add failing source guard for required label properties**

Test JSON parses and asserts name/doc_type plus required strings `R&D TRIAL - NOT FOR SALE`, `6cm 4cm`, `trial_title`, `trial_no`, and `posting_date`.

- [ ] **Step 2: Run test and confirm RED**

Expected RED because the format does not exist.

- [ ] **Step 3: Create print format**

Follow `PD Label 6*4` page CSS. Jinja obtains product name safely using:

```jinja
{% set product_name = frappe.db.get_value('Product Proposal', doc.product_proposal, 'product_name') or doc.product_proposal %}
```

Render factory name, `R&D TRIAL - NOT FOR SALE`, product name, Trial Title, Trial No, and Posting Date only. Keep spacing available for future QR.

- [ ] **Step 4: Add direct Print Trial Label button**

On saved Trial, add button `Print Trial Label` that opens `/printview` for the current DocType/name with the dedicated format and `no_letterhead=1`.

- [ ] **Step 5: Parse JSON, check JS, and render manually on test1.com**

Static checks prove syntax only. Manual acceptance must inspect 6x4 preview and a thermal print because page size/layout cannot be proven by unit tests.

- [ ] **Step 6: Commit in real repository**

```bash
git commit -m "feat: add product proposal trial thermal label"
```

---

### Task 6: Migration, full regression gate, and manual acceptance

**Files:**
- No additional production files unless a migration/runtime defect is discovered.
- Update tests only if a newly discovered real regression requires coverage.

**Interfaces:**
- Produces release evidence for the four approved requirements.

- [ ] **Step 1: Validate every changed JSON file**

```bash
find taj_core/rnd -name '*.json' -print0 | xargs -0 -n1 python3 -m json.tool >/dev/null
```

- [ ] **Step 2: Python and JavaScript static checks**

```bash
python3 -m compileall -q taj_core
find taj_core -name '*.js' -print0 | xargs -0 -n1 node --check
```

- [ ] **Step 3: Run migrate on test1.com without changing Scheduler state**

```bash
bench --site test1.com migrate
bench --site test1.com scheduler status
```

Expected: migrate succeeds and Scheduler remains disabled.

- [ ] **Step 4: Run targeted R&D tests**

```bash
bench --site test1.com run-tests --module taj_core.tests.test_trial_cooking
```

- [ ] **Step 5: Run full Taj Core suite**

```bash
bench --site test1.com run-tests --app taj_core
```

Baseline before these changes: 109 tests OK. New total must include the added tests and all must pass.

- [ ] **Step 6: Git integrity checks in the real repository**

```bash
git diff --check
git status --short
git diff --stat
git diff
```

Review exact files; do not push.

- [ ] **Step 7: Manual functional acceptance on test1.com**

Verify:
1. Product Proposal qty 100 + row qty 50 + Trial target 10 creates row qty 5.
2. Previous Trial qty 10 + row qty 5 + target 20 creates row qty 10.
3. Saved Draft Trial Planned Cooking Qty cannot be changed.
4. Submitted Product Proposal accepts customer sample row update and persists token.
5. Wrong-Proposal Trial in sample row is blocked.
6. Sample evaluation link opens exact product/trial/customer context without selection and forged URL values cannot redirect it.
7. Only enabled/current Trials appear in general Sensory picker; future/expired/disabled Trials do not.
8. Enabling Sensory with blank dates defaults to Today through +3 months.
9. Old feedback remains after Trial expires.
10. `Print Trial Label` opens the dedicated 6x4 format and physical preview/print is correctly sized.

- [ ] **Step 8: Final release report**

Report actual test counts, static check results, migration result, Scheduler status, manual acceptance results, current HEAD/status, and explicitly state that no push was performed.
