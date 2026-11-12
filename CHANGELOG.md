# TAJ Core - Changelog

## [Unreleased]

### Changed
- Nutrition Facts Ar (10x7): display "الوزن الصافي: <weight> جم" and "القيم الغذائية لكل: <weight> جم" using the actual Item package weight; retain the per-100-g fallback.
- Nutrition Facts Ar (10x7): round displayed calories and nutrient quantities to whole numbers using HALF_UP (0.5 rounds upward) after applying package weight.
- Calculate whole-number daily-value percentages from the rounded printed quantities using: total fat 65 g, saturated fat 20 g, sodium 2400 mg, carbohydrates 300 g, cholesterol 300 mg, fiber 25 g, and protein 50 g.

### Fixed
- Allow Item and Variant printing when Less Than 1 rules exist.
- Display the literal phrase "أقل من ١ جم" or "أقل من ١ ملجم" for selected nutrients, without scaling or calculating their daily-value percentage.
- Continue scaling other nutrients by package weight.
