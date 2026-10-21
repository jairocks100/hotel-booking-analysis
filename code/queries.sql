-- SQLite 3.25+; normalized schema; completed records from documented valid-booking cohort.
-- A-Q1: ties intentionally retained by RANK; grouping uses property_id.
WITH revenue_by_property AS (
 SELECT p.property_city,p.property_id,p.property_name,SUM(b.total_amount) AS revenue
 FROM properties p JOIN bookings b ON b.property_id=p.property_id
 WHERE b.booking_status='Completed'
 GROUP BY p.property_city,p.property_id,p.property_name
), ranked AS (
 SELECT *,RANK() OVER(PARTITION BY property_city ORDER BY revenue DESC) AS revenue_rank
 FROM revenue_by_property
)
SELECT property_city,property_id,property_name,ROUND(revenue,2) AS revenue
FROM ranked WHERE revenue_rank=1 ORDER BY property_city,property_id;

-- A-Q2: consecutive check-in to check-in gap (not previous checkout to next checkin).
-- booking_id deterministically breaks equal-checkin ties; first gap is NULL and AVG ignores it.
WITH previous AS (
 SELECT customer_id,checkin_date,
 LAG(checkin_date) OVER(PARTITION BY customer_id ORDER BY checkin_date,booking_id) AS previous_checkin
 FROM bookings WHERE booking_status='Completed'
), eligible AS (
 SELECT customer_id,AVG(julianday(checkin_date)-julianday(previous_checkin)) AS average_gap_days
 FROM previous WHERE previous_checkin IS NOT NULL
 GROUP BY customer_id HAVING AVG(julianday(checkin_date)-julianday(previous_checkin)) < 30
)
SELECT COUNT(*) AS customers_average_gap_under_30 FROM eligible;
