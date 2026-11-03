-- id: distinct_seasons
-- description: Distinct seasons/campaigns available, most recent first
-- kind: list
-- param: (none)
SELECT DISTINCT season, season_start_date
FROM {{table:venus_gold_prod.cp_sales_overview.cp_france_sales_insight}}
WHERE sys_delete_flag = false
ORDER BY season_start_date DESC
