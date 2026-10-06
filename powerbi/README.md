# Native Power BI project - 0.4.0

Open Corridor/Corridor.pbip in Power BI Desktop. It contains eight PBIR pages, 16 import tables, 32 DAX measures and five relationships. The active semantic model uses exported TMDL in Corridor.SemanticModel/definition. Power Query reads outputs/powerbi/*.csv; run scripts/rebind_powerbi.py after moving the folder.

The Microsoft modeling connector loaded the BIM and exported its native TMDL. Published report-schema validation passed for 66 files; outputs/powerbi_validation.json records the source check. Latest Desktop refresh remains pending at the reload dialog. The older 0.3 native receipt verifies the previous ten-table/eighteen-measure release only.

Pages cover executive decisions, customers, pricing, promotion/rewards, loyalty, transportation, experiments and monitoring. Added reporting includes digital/account engagement, reward balances/redemptions, price economics/consumer surplus, hourly directional demand, experiment bounds, PSI and model acceptance/version. Values are synthetic. Row-level governance and real stakeholder usability need deployment review.
