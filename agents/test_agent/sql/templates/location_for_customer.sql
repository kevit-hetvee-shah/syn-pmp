-- id: location_for_customer
-- description: Distinct account city for one customer account — auto-fills the read-only Location field on the meeting and feeds the slide deck hook
-- kind: list
-- param: customer string [A-Za-z0-9,.'&()/\s-]+
SELECT DISTINCT account_city AS location
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND fr_main_account = :customer
ORDER BY location
