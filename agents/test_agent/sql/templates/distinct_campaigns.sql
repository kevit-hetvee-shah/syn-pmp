-- id: distinct_campaigns
-- description: Distinct sales campaigns (e.g. "F03") — a separate dimension from season, not derived from it
-- kind: list
-- param: (none)
SELECT DISTINCT campaign
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND campaign IS NOT NULL
ORDER BY campaign
