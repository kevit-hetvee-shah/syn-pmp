-- id: segment_product_qty_by_season
-- description: Quantity ordered per product per season, for one customer+segment — feeds slide 7's deep-dive table and column chart
-- kind: table
-- param: customer string [\w,.'&()/\s-]+
-- param: segment string [\w,.'&()/\s-]+
SELECT
    tradename_en AS product,
    season,
    season_start_date,
    SUM(customer_order_qty_suom) AS qty
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND fr_main_account = :customer
  AND france_sms_fr = :segment
GROUP BY tradename_en, season, season_start_date
ORDER BY qty DESC
