-- id: distinct_customers_for_sales_rep
-- description: Distinct customer accounts owned by one sales rep (Salesforce owner_id)
-- kind: list
-- param: owner_id string [A-Za-z0-9]{15,18}
SELECT DISTINCT fr_main_account AS client
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND owner_id = :owner_id
ORDER BY client
