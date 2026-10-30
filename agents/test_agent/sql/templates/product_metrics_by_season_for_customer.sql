-- id: product_metrics_by_season_for_customer
-- description: Quantity ordered and revenue per product per season for one customer — feeds slide 4's product table and doughnut chart
-- kind: table
-- param: customer string [A-Za-z0-9,.'&()/\s-]+
SELECT
    tradename_en AS product,
    sales_uom AS unit,
    season,
    season_start_date,
    SUM(customer_order_qty_suom)   AS qty,
    SUM(customer_invoiced_value)   AS revenue
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND fr_main_account = :customer
GROUP BY tradename_en, sales_uom, season, season_start_date
ORDER BY revenue DESC
