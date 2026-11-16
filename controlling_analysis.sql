SELECT
	d.department, 
    SUM(f.budget_amount) AS total_budget, 
    SUM(f.actual_amount) AS total_actual, 
    SUM(f.budget_amount - f.actual_amount) AS variance_eur,
    ROUND(SUM(f.budget_amount-f.actual_amount)/SUM(f.budget_amount)*100, 2) AS variance_pct
FROM dim_department d
JOIN fact_transactions f ON d.department_id = f.department_id
GROUP BY d.department
ORDER BY variance_pct;

WITH monthly_summary AS (
	SELECT 
		YEAR(date) AS fiscal_year, 
		MONTH(date) AS fiscal_month,
		SUM(budget_amount) AS monthly_budget, 
		SUM(actual_amount) AS monthly_actual
	FROM fact_transactions
	GROUP BY YEAR(date), MONTH(date)) -- to follow SQL standards --

SELECT 
	fiscal_year, 
    fiscal_month, 
    monthly_budget, 
    monthly_actual,
    SUM(monthly_budget) OVER (PARTITION BY fiscal_year ORDER BY fiscal_month) AS ytd_budget,
    SUM(monthly_actual) OVER (PARTITION BY fiscal_year ORDER BY fiscal_month) AS ytd_actual
 FROM monthly_summary
 ORDER BY fiscal_year, fiscal_month; -- to avoid problems in another SQL database --   

WITH category_variances AS (
	SELECT 
		c.category,
		r.region, 
		SUM(f.budget_amount - f.actual_amount) AS variance_eur,
		RANK() OVER (PARTITION BY r.region ORDER BY SUM(f.budget_amount - f.actual_amount)) AS overrun_rank
	FROM dim_region r 
	JOIN fact_transactions f ON r.region_id = f.region_id
	JOIN dim_category c ON f.category_id = c.category_id
	GROUP BY r.region, c.category)
    
SELECT region, category, variance_eur
FROM category_variances
WHERE overrun_rank <= 3 AND variance_eur > 0; -- filter top 3 budget overruns after ranking --