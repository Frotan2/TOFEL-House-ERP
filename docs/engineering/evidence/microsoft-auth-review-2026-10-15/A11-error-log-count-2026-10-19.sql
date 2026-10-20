-- A11 read-only count: historical Error Log rows that may hold Office 365 callback code/state.
--
-- Run on an authorized restored copy of the site (or the live site, read-only, with owner approval):
--   bench --site <site> mariadb < A11-error-log-count-2026-10-19.sql
--
-- SELECT only. Prints integer counts. No method, error or metadata text is returned.
-- Do not delete or edit any row based on this output; deletion needs owner review and authorization.

SELECT
  COUNT(*) AS total_error_log_rows,
  SUM(CASE WHEN `method` LIKE '%login_via_office365%'
            OR `method` LIKE '%oauth2_logins%'
            OR `error` LIKE '%login_via_office365%' THEN 1 ELSE 0 END) AS office365_callback_rows,
  SUM(CASE WHEN (`method` LIKE '%login_via_office365%' OR `error` LIKE '%login_via_office365%')
            AND (`metadata` LIKE '%"code"%' OR `metadata` LIKE '%"state"%'
                 OR `error` LIKE '%code=%' OR `error` LIKE '%state=%') THEN 1 ELSE 0 END) AS callback_rows_possibly_holding_code_or_state,
  SUM(CASE WHEN `metadata` LIKE '%"code"%' AND `metadata` LIKE '%"state"%' THEN 1 ELSE 0 END) AS rows_with_code_and_state_keys_any_method,
  SUM(CASE WHEN `creation` >= '2026-10-18 00:00:00'
            AND (`method` LIKE '%login_via_office365%' OR `error` LIKE '%login_via_office365%') THEN 1 ELSE 0 END) AS callback_rows_since_2026_10_18,
  MIN(CASE WHEN `method` LIKE '%login_via_office365%' OR `error` LIKE '%login_via_office365%' THEN `creation` END) AS first_callback_row_date,
  MAX(CASE WHEN `method` LIKE '%login_via_office365%' OR `error` LIKE '%login_via_office365%' THEN `creation` END) AS last_callback_row_date
FROM `tabError Log`;
