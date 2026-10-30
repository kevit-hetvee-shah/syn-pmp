-- id: revenue_by_season_and_segment_for_customer
-- description: Revenue per market segment per season for one customer — feeds slide 5's segment-sales table
-- kind: table
-- param: customer string [A-Za-z0-9,.'&()/\s-]+
SELECT
    france_sms_fr AS segment,
    season,
    season_start_date,
    SUM(customer_invoiced_value) AS revenue
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND fr_main_account = :customer
GROUP BY france_sms_fr, season, season_start_date
ORDER BY revenue DESC
