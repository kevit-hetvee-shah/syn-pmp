-- id: distinct_products
-- description: Distinct products (focus-product suggestions), optionally scoped to one customer
-- kind: list
-- param: customer string [A-Za-z0-9,.'&()/\s-]+ optional
SELECT DISTINCT tradename_en AS product
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
  AND (:customer IS NULL OR fr_main_account = :customer)
ORDER BY product
