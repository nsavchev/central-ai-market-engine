-- Stage 2 read-only legacy schema inventory.
-- Run ONLY with a read-only PostgreSQL role and a read-only transaction.
-- No ALTER, CREATE, INSERT, DELETE, UPDATE, stamp or migration commands.
BEGIN TRANSACTION READ ONLY;
SELECT current_database() AS database_name, current_user AS role_name,
       current_setting('server_version') AS server_version;
SELECT n.nspname AS schema_name,c.relname AS table_name,c.relkind,
       pg_get_userbyid(c.relowner) AS owner,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind IN ('r','p','S')
ORDER BY c.relname;
SELECT table_name,column_name,ordinal_position,data_type,udt_name,
       character_maximum_length,numeric_precision,numeric_scale,
       is_nullable,column_default,is_identity,identity_generation
FROM information_schema.columns
WHERE table_schema='public'
ORDER BY table_name,ordinal_position;
SELECT c.conrelid::regclass::text AS table_name,c.conname AS constraint_name,
       c.contype,pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
WHERE n.nspname='public' ORDER BY table_name,constraint_name;
SELECT schemaname,tablename,indexname,indexdef
FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname;
SELECT table_name, column_name, is_identity, identity_generation, column_default
FROM information_schema.columns WHERE table_schema='public'
  AND table_name IN ('paper_accounts','paper_trades') AND column_name='id';
SELECT 'paper_accounts' AS table_name,count(*) AS row_count FROM public.paper_accounts
UNION ALL
SELECT 'paper_trades',count(*) FROM public.paper_trades;
SELECT to_regclass('public.alembic_version') AS alembic_table,
       to_regclass('public.paper_write_fence') AS fence_table,
       to_regclass('public.paper_request_keys') AS key_table;
COMMIT;
