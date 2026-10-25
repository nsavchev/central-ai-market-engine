-- A04 READ-ONLY inventory. Execute manually using a dedicated SELECT-only role.
-- Do not use a superuser or application writer credentials.
BEGIN TRANSACTION READ ONLY;
SELECT current_database() AS database_name, current_schema() AS schema_name,
       current_user AS connected_role, current_setting('server_version') AS pg_version;
SELECT to_regclass(format('%I.%I', current_schema(), 'alembic_version')) IS NOT NULL
       AS alembic_version_table_present;
-- Run only when alembic_version_table_present is true:
-- SELECT version_num FROM alembic_version ORDER BY version_num;
SELECT table_name, column_name, data_type, numeric_precision, numeric_scale,
       is_nullable
FROM information_schema.columns
WHERE table_schema=current_schema()
  AND table_name IN ('paper_accounts','paper_trades','paper_request_keys','paper_write_fence')
ORDER BY table_name, ordinal_position;
SELECT table_name, constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema=current_schema()
  AND table_name IN ('paper_accounts','paper_trades','paper_request_keys','paper_write_fence')
ORDER BY table_name, constraint_name;
ROLLBACK;
