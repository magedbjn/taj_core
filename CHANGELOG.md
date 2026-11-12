# TAJ Core - Changelog

## [Unreleased]

### 2026-11-12 - Nutrition Facts Ar: Less Than 1

**Component:** Nutrition Facts Ar
**Compatibility:** ERPNext / Frappe v16

#### Fixed
- Allow Item and Variant printing when Less Than 1 rules exist.
- Display the fixed phrase "أقل من ١ جم" or "أقل من ١ ملجم".
- Do not scale flagged nutrient values.
- Leave daily-value percentages blank for flagged nutrients.
- Continue scaling other nutrients by package weight.

#### Testing
- 8 synthetic test scenarios: PASS on test1.com.
- No database or Print Format changes.
- QC review is required before production label use.
