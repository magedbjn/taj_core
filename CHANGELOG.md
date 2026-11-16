# TAJ Core - Changelog

## [Unreleased]

### Changed
- Nutrition Facts Ar (10x7): display "الوزن الصافي: <weight> جم" and "القيم الغذائية لكل: <weight> جم" using the actual Item package weight; retain the per-100-g fallback.
- Nutrition Facts Ar (10x7): round displayed calories and nutrient quantities to whole numbers using HALF_UP (0.5 rounds upward) after applying package weight.
- Nutrition Facts Ar (10x7): use a shared SFDA/GSO 2233:2021 daily-value reference for the printed, rounded quantities: total fat 70 g, saturated fat 20 g, sodium 2400 mg, carbohydrates 260 g, cholesterol 300 mg, fiber 28 g, protein 50 g, and added sugars 50 g; leave the percentage for total sugars blank.

### Fixed
- Allow Item and Variant printing when Less Than 1 rules exist.
- Display the literal phrase "أقل من ١ جم" or "أقل من ١ ملجم" for selected nutrients, without scaling or calculating their daily-value percentage.
- Continue scaling other nutrients by package weight.
