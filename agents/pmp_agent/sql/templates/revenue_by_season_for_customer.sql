-- id: revenue_by_season_for_customer
-- description: Total invoiced revenue by season for one customer — feeds slide 3's "Ventes Syngenta au distributeur" KPI row
-- kind: series
-- unit: EUR
-- param: customer string [\w,.'&()/\s-]+
SELECT season, season_start_date, SUM(customer_invoiced_value) AS revenue
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND fr_main_account = :customer
GROUP BY season, season_start_date
ORDER BY season_start_date DESC
