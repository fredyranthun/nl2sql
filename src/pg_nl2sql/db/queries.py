"""SQL queries used by PostgreSQL schema introspection."""

TABLES_QUERY = """
SELECT
  t.table_schema,
  t.table_name,
  t.table_type,
  pgd.description AS table_description
FROM information_schema.tables AS t
LEFT JOIN pg_catalog.pg_class AS c
  ON c.relname = t.table_name
LEFT JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
  AND n.nspname = t.table_schema
LEFT JOIN pg_catalog.pg_description AS pgd
  ON pgd.objoid = c.oid
  AND pgd.objsubid = 0
WHERE t.table_schema = ANY(%(schemas)s)
  AND t.table_type IN ('BASE TABLE', 'VIEW')
ORDER BY t.table_schema, t.table_name;
"""

COLUMNS_QUERY = """
SELECT
  c.table_schema,
  c.table_name,
  c.column_name,
  c.data_type,
  c.is_nullable,
  c.ordinal_position,
  pgd.description AS column_description
FROM information_schema.columns AS c
LEFT JOIN pg_catalog.pg_class AS cls
  ON cls.relname = c.table_name
LEFT JOIN pg_catalog.pg_namespace AS n
  ON n.oid = cls.relnamespace
  AND n.nspname = c.table_schema
LEFT JOIN pg_catalog.pg_attribute AS a
  ON a.attrelid = cls.oid
  AND a.attname = c.column_name
LEFT JOIN pg_catalog.pg_description AS pgd
  ON pgd.objoid = cls.oid
  AND pgd.objsubid = a.attnum
WHERE c.table_schema = ANY(%(schemas)s)
ORDER BY c.table_schema, c.table_name, c.ordinal_position;
"""

PRIMARY_KEYS_QUERY = """
SELECT
  kcu.table_schema,
  kcu.table_name,
  kcu.column_name,
  kcu.ordinal_position
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON kcu.constraint_name = tc.constraint_name
  AND kcu.constraint_schema = tc.constraint_schema
  AND kcu.table_schema = tc.table_schema
  AND kcu.table_name = tc.table_name
WHERE tc.constraint_type = 'PRIMARY KEY'
  AND tc.table_schema = ANY(%(schemas)s)
ORDER BY kcu.table_schema, kcu.table_name, kcu.ordinal_position;
"""

FOREIGN_KEYS_QUERY = """
SELECT
  src_kcu.table_schema AS table_schema,
  src_kcu.table_name AS table_name,
  src_kcu.constraint_name AS constraint_name,
  src_kcu.ordinal_position AS position,
  src_kcu.column_name AS column_name,
  ref_kcu.table_schema AS ref_table_schema,
  ref_kcu.table_name AS ref_table_name,
  ref_kcu.column_name AS ref_column_name
FROM information_schema.referential_constraints AS rc
JOIN information_schema.key_column_usage AS src_kcu
  ON src_kcu.constraint_name = rc.constraint_name
  AND src_kcu.constraint_schema = rc.constraint_schema
JOIN information_schema.key_column_usage AS ref_kcu
  ON ref_kcu.constraint_name = rc.unique_constraint_name
  AND ref_kcu.constraint_schema = rc.unique_constraint_schema
  AND ref_kcu.ordinal_position = src_kcu.position_in_unique_constraint
WHERE src_kcu.table_schema = ANY(%(schemas)s)
ORDER BY
  src_kcu.table_schema,
  src_kcu.table_name,
  src_kcu.constraint_name,
  src_kcu.ordinal_position;
"""
