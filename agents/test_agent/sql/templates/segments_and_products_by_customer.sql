-- id: segments_and_products_by_customer
-- description: Market segments and their products for one customer — feeds deck_plan.compute_slide_plan's total_market_segments/segment_product_counts inputs
-- kind: table
-- param: customer string [A-Za-z0-9,.'&()/\s-]+
SELECT DISTINCT
    france_sms_fr AS segment,
    tradename_en  AS product
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND fr_main_account = :customer
ORDER BY segment, product
