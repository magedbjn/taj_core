# Product Proposal Trial, Customer Samples, Label, and Sensory Rating Design

Date: 2026-09-08
Project: Taj Core
Target: Frappe / ERPNext V15
Baseline: local production handoff commit cc9423e
Status: Design approved in conversation; pending user review of this written specification before implementation planning.

## 1. Goal

Improve the Product Proposal R&D workflow in four connected areas without breaking the existing Trial snapshot, costing, BOM lineage, or current Sensory Feedback linkage:

1. Require Planned Cooking Qty before creating a Product Proposal Trial and scale copied formulation quantities to that planned quantity.
2. Add a small customer sample log as a Child Table inside Product Proposal, with a direct, easy evaluation link for each sample.
3. Add a thermal Product Proposal Trial label sized 6 cm x 4 cm and a direct Print Trial Label action.
4. Prevent the Sensory Rating form from exposing every historical Product Proposal by explicitly activating only selected Trials for a limited evaluation period, defaulting to three months.

## 2. Existing Baseline

The current source already has:

- Product Proposal Trial as an independent DocType.
- Product Proposal Trial Item as a snapshot child table.
- create_trial() sources: Previous Trial, Current Product Proposal Items, Empty Trial.
- planned_cooking_qty and actual_produced_qty on Product Proposal Trial.
- Snapshot freezing after Trial leaves Draft.
- Product Proposal and Product Proposal Trial linkage into Sensory Feedback.
- A public anonymous Web Form at /sensory-rating.
- A 6 cm x 4 cm R&D print format pattern named PD Label 6*4.

Current create_trial() copies the source quantities unchanged and copies planned_cooking_qty from the previous Trial or Product Proposal.quantity. The new design changes that creation behavior.

## 3. Requirement 1 - Planned Cooking Qty Before Trial Creation

### 3.1 User flow

From Product Proposal, the New Trial Cooking dialog will contain:

- Copy Items From
  - Previous Trial
  - Current Product Proposal Items
  - Empty Trial
- Planned Cooking Qty (required, greater than zero)

The Trial is not created until Planned Cooking Qty is provided.

### 3.2 Scaling rule

For a Trial created from Product Proposal items:

- source_qty = Product Proposal.quantity
- target_qty = entered Planned Cooking Qty

For a Trial created from Previous Trial:

- source_qty = previous Trial.planned_cooking_qty
- target_qty = entered Planned Cooking Qty

For each copied formulation row:

`new_item_qty = source_item_qty * target_qty / source_qty`

The copied Trial item fields other than quantity retain the existing snapshot behavior and lineage, including line_key.

For Empty Trial:

- Planned Cooking Qty is still required and stored.
- No item scaling is performed because no formulation rows are copied.

### 3.3 Validation

- Planned Cooking Qty must be > 0.
- If the chosen source contains items and its source quantity is <= 0, creation fails with a clear message instead of assuming a ratio.
- Scaling is performed server-side, not only in JavaScript, so API callers receive the same behavior.
- Trial costing is refreshed after scaled quantities are created, preserving the existing valuation/conversion rules.

### 3.4 Locking

After Product Proposal Trial is inserted:

- planned_cooking_qty becomes immutable immediately, including while status is Draft.
- Server validation adds planned_cooking_qty to the Trial identity fields that cannot change after creation.
- Client UI sets planned_cooking_qty read-only on every saved Trial.

Other Draft formulation fields retain their current behavior unless already governed by existing snapshot rules.

If another planned quantity is required, the user creates a new Trial instead of editing the existing Trial's planned quantity.

### 3.5 Actual production

actual_produced_qty remains separate from Planned Cooking Qty. Entering actual production does not rescale the historical formulation. This preserves the exact planned/used Trial snapshot and supports future yield analysis.

## 4. Requirement 2 - Customer Sample Child Table

### 4.1 Design choice

Use a Child Table inside Product Proposal, not a standalone transaction DocType, because the expected volume is very small (normally no more than about three customers) and the purpose is lightweight R&D tracking.

New child DocType:

`Product Proposal Sample`

New Product Proposal table field:

`customer_samples`

Suggested tab/section label:

`Customer Samples`

### 4.2 Child fields

Minimum fields:

- customer - Link / Customer, required
- trial_document - Link / Product Proposal Trial, required
- sample_date - Date, default Today, required
- sample_qty - Float, required and > 0
- uom - Link / UOM, required
- interest_status - Select:
  - Pending
  - Interested
  - Not Interested
- notes - Small Text, optional
- evaluation_token - Data, hidden/read-only, system generated
- evaluation_link - Button, label such as Copy Evaluation Link / Open Evaluation

The Trial query must be restricted to Trials belonging to the same Product Proposal.

### 4.3 Submitted Product Proposal behavior

Customer Samples are operational follow-up information and may need to be entered after the Product Proposal is submitted. The customer_samples table is therefore designed to be updateable after submit, while core Product Proposal formulation fields retain their existing submitted-document restrictions.

Implementation must verify Frappe V15 update-after-submit behavior for the Table field and child rows and add only the minimum allow_on_submit flags required.

### 4.4 Direct evaluation link

Each sample row receives a cryptographically random token when first saved.

The public customer link uses the token, for example conceptually:

`/sensory-rating?sample=<random-token>`

The customer does not select Product Proposal, Trial, or Customer.

The token resolves server-side to:

- parent Product Proposal
- Product Proposal Trial
- Customer
- sample row

The evaluation is stored against the resolved records.

Do not trust item/trial/customer query-string values for a customer sample evaluation.

### 4.5 Easy customer experience

When opened through a sample token, the form should show only what is useful to the customer, with Product Proposal / Trial already selected internally.

The current sensory fields may continue to be used, but the sample path should minimize unnecessary identity entry. Customer and Trial are resolved automatically.

A customer-linked evaluation can store customer on Sensory Feedback as a hidden/internal Link. The existing `your_name` field may be optional or prefilled for the token path; exact UI behavior will be chosen during implementation while keeping the evaluation one-step and simple.

### 4.6 Future QR support

QR printing is explicitly future-ready but not required in this implementation. The permanent evaluation_token becomes the stable identifier that a future QR code can encode on the 6x4 Trial/sample label.

## 5. Requirement 3 - Product Proposal Trial Thermal Label 6x4

### 5.1 Print Format

Create a standard Taj Core Print Format:

`Product Proposal Trial Label 6x4`

DocType:

`Product Proposal Trial`

Physical page size:

- width 6 cm
- height 4 cm

Follow the existing PD Label 6*4 thermal-print CSS pattern where practical.

### 5.2 Required content

The label contains:

- Taj Food Factory for Ready Meals
- R&D TRIAL - NOT FOR SALE
- Product name
- Trial Title
- Trial No
- Posting Date

The design should prioritize product name and Trial identity and avoid costing, raw-material details, or other dense data.

### 5.3 Product name source

Use the Product Proposal associated with the Trial to render the product name. The implementation must avoid unsafe assumptions if product_name is absent and use a clear fallback such as the Product Proposal name.

### 5.4 Direct print action

Add a Product Proposal Trial form button:

`Print Trial Label`

It opens/prints using the dedicated Product Proposal Trial Label 6x4 format, so the user does not need to choose a Print Format manually each time.

### 5.5 Future extension

The format must leave room for a later QR code without making QR generation part of this implementation.

## 6. Requirement 4 - Sensory Rating Visibility

### 6.1 Design choice

Control Sensory availability at Product Proposal Trial level, not at Product Proposal level, because Sensory Feedback is already Trial-aware and evaluation should identify the exact formulation tested.

Add to Product Proposal Trial:

- enable_sensory_rating - Check
- sensory_from_date - Date
- sensory_until_date - Date

Suggested section:

`Sensory Availability`

### 6.2 Defaults

When Enable Sensory Rating is turned on:

- sensory_from_date defaults to Today when empty.
- sensory_until_date defaults to three months after sensory_from_date when empty.

The user may manually change the period.

### 6.3 Validation

When enabled:

- From Date is required.
- Until Date is required.
- Until Date cannot be before From Date.

Disabling sensory availability hides the Trial from general Sensory Rating selection without deleting historical feedback.

No automatic activation from Production is included. Activation is deliberately manual because production does not necessarily mean a product should be under sensory review.

### 6.4 General Sensory Rating form

The public/general Sensory Rating page must no longer expose the full historical Product Proposal list.

It will show only Trials where:

- enable_sensory_rating = 1
- sensory_from_date <= today
- sensory_until_date >= today

The exact UI should make the active Trial the authoritative selection. Product Proposal is derived from the selected Trial and does not need to be separately searchable across all proposals.

This permits two, five, or any deliberately selected small set of Trials to be visible at one time, regardless of the total historical Product Proposal count.

### 6.5 Direct links

Existing direct Trial links and new customer sample-token links bypass the need for a broad picker, but still resolve and validate the target Trial server-side.

A customer sample link is allowed to identify its specific Trial directly even when the general picker is not exposing every Product Proposal. Historical feedback remains immutable/auditable according to existing Sensory Feedback behavior.

## 7. Data Flow

### Trial creation

Product Proposal -> New Trial Cooking dialog -> choose source + Planned Cooking Qty -> server validates source quantity -> scales copied rows -> refreshes costs -> inserts immutable Planned Cooking Qty Trial snapshot.

### Customer sample

Product Proposal -> Customer Samples row -> choose Customer + Trial + date + qty -> token generated -> Copy/Open Evaluation Link -> customer opens token link -> server resolves sample -> Sensory Feedback stored against exact Trial/Product Proposal/Customer.

### Internal/general sensory

R&D user enables Sensory Rating on selected Trial -> default three-month window -> general Sensory Rating picker queries only currently active Trials -> evaluator rates selected Trial -> historical feedback remains after the window expires.

### Label

Product Proposal Trial -> Print Trial Label -> Product Proposal Trial Label 6x4 -> thermal printer.

## 8. Security and Data Integrity

- create_trial scaling and quantity validation must be server-enforced.
- Planned Cooking Qty immutability must be server-enforced; JavaScript read-only is only UX.
- Sample evaluation token must be random and non-guessable.
- Token resolution must verify the child row still belongs to its Product Proposal and the Trial still belongs to the same Product Proposal.
- Public Sensory submission must not accept a forged Product Proposal/Trial/Customer combination merely because values were supplied in URL parameters.
- General Sensory picker must return only active-window Trials.
- Existing Product Proposal Trial permission checks and BOM lineage validation must not be weakened.

## 9. Compatibility / Scope

Target remains Frappe / ERPNext V15.

Do not change:

- BOM lineage rules.
- Final Trial uniqueness rules.
- Trial costing valuation/conversion policy.
- Scheduler state.
- Existing production integration.

Out of scope for this implementation:

- QR rendering on the label.
- Customer notifications by WhatsApp/email.
- CRM opportunity creation from Interested status.
- Automatic Sensory activation from Work Order / Stock Entry / Production.
- New standalone Sample transaction/workflow.
- Yield KPI/dashboard, although the Planned vs Actual model remains compatible with it.

## 10. Expected Files / Components

Likely existing files to modify:

- taj_core/rnd/doctype/product_proposal/product_proposal.json
- taj_core/rnd/doctype/product_proposal/product_proposal.js
- taj_core/rnd/doctype/product_proposal/product_proposal.py
- taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.json
- taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.js
- taj_core/rnd/doctype/product_proposal_trial/product_proposal_trial.py
- taj_core/rnd/doctype/sensory_feedback/sensory_feedback.json
- taj_core/rnd/doctype/sensory_feedback/sensory_feedback.py
- taj_core/rnd/web_form/sensory_rating/sensory_rating.json
- taj_core/rnd/web_form/sensory_rating/sensory_rating.js
- taj_core/rnd/web_form/sensory_rating/sensory_rating.py

New components likely required:

- taj_core/rnd/doctype/product_proposal_sample/
- taj_core/rnd/print_format/product_proposal_trial_label_6x4/

Tests will be added in the existing Taj Core test structure rather than creating ad-hoc runtime-only validation.

## 11. Acceptance Criteria

### Planned Cooking Qty

1. New Trial cannot be created without Planned Cooking Qty > 0.
2. Proposal quantity 100 with source row qty 50 and target Trial qty 10 creates Trial row qty 5.
3. Previous Trial planned qty 10 with row qty 5 and new target qty 20 creates row qty 10.
4. Unknown/zero source quantity with copied items fails clearly.
5. Saved Trial Planned Cooking Qty cannot be changed in Draft through UI or API.
6. Existing Trial snapshot/BOM tests remain green.

### Samples

1. Product Proposal can record multiple small sample rows.
2. Trial selector cannot use a Trial from another Product Proposal.
3. A sample row receives a unique random evaluation token.
4. Customer link opens the exact Product Proposal/Trial without manual selection.
5. Changing URL item/trial/customer values cannot reassign the evaluation away from the token-resolved sample.
6. Samples can be maintained after Product Proposal submit if required by the approved workflow.
7. Interested status is visible from Product Proposal.

### Trial label

1. Print Format is 6 cm x 4 cm.
2. It renders Product name, Trial Title, Trial No, date, and R&D TRIAL - NOT FOR SALE.
3. Print Trial Label opens the dedicated format directly.

### Sensory visibility

1. Only enabled Trials within From/Until dates appear in the general sensory picker.
2. Disabled, future, and expired Trials do not appear.
3. Enabling an empty period defaults From to Today and Until to three months later.
4. Expired feedback remains stored and reportable.
5. Direct token-based sample evaluation resolves its exact Trial without requiring broad list selection.

## 12. Verification Strategy

Implementation must follow Taj Core's current audit discipline:

1. Add regression tests first for server-side scaling, immutability, token integrity, Trial ownership, and sensory active-window query.
2. Demonstrate RED for the new behavior where practical.
3. Apply minimal implementation changes.
4. Run targeted R&D tests.
5. Run the full Taj Core test suite.
6. Run Python compileall.
7. Run node --check for changed JavaScript.
8. Validate changed JSON.
9. Run git diff --check in the real repository.
10. Perform manual acceptance on test1.com while keeping Scheduler disabled.

Manual acceptance should include thermal label preview/print because syntax tests cannot prove 6x4 physical layout.

## 13. Release Safety

- No push unless explicitly requested.
- No destructive Git commands.
- Stage exact files only; never `git add .`.
- test1.com Scheduler remains Disabled.
- Do not claim completion until targeted tests, full app tests, static checks, and relevant manual checks provide evidence.
