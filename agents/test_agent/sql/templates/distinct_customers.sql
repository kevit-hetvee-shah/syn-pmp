-- id: distinct_customers
-- description: Distinct customer accounts the rep can select for a meeting
-- kind: list
-- param: (none)
SELECT DISTINCT fr_main_account AS client
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
ORDER BY client
