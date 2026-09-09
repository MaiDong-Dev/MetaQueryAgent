-- 元数据表（SQLite 方言）

CREATE TABLE IF NOT EXISTS md_instance (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_name TEXT NOT NULL,
  host          TEXT NOT NULL,
  port          INTEGER NOT NULL DEFAULT 3306,
  username      TEXT NOT NULL,
  password      TEXT NOT NULL,
  remark        TEXT,
  created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_name)
);

CREATE TABLE IF NOT EXISTS md_database (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id   INTEGER NOT NULL,
  database_name TEXT NOT NULL,
  charset       TEXT,
  collation     TEXT,
  comment       TEXT,
  is_deleted    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name)
);

CREATE TABLE IF NOT EXISTS md_table (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id   INTEGER NOT NULL,
  database_name TEXT NOT NULL,
  table_name    TEXT NOT NULL,
  table_type    TEXT,
  engine        TEXT,
  table_comment TEXT,
  charset       TEXT,
  collation     TEXT,
  is_deleted    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name, table_name)
);

CREATE TABLE IF NOT EXISTS md_column (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id       INTEGER NOT NULL,
  database_name     TEXT NOT NULL,
  table_name        TEXT NOT NULL,
  column_name       TEXT NOT NULL,
  ordinal_position  INTEGER,
  column_default    TEXT,
  is_nullable       TEXT,
  data_type         TEXT,
  column_type       TEXT,
  char_max_length   INTEGER,
  numeric_precision INTEGER,
  numeric_scale     INTEGER,
  charset           TEXT,
  collation         TEXT,
  column_extra      TEXT,
  column_comment    TEXT,
  is_deleted        INTEGER NOT NULL DEFAULT 0,
  created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name, table_name, column_name)
);

CREATE TABLE IF NOT EXISTS md_index (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id   INTEGER NOT NULL,
  database_name TEXT NOT NULL,
  table_name    TEXT NOT NULL,
  index_name    TEXT NOT NULL,
  non_unique    INTEGER NOT NULL,
  seq_in_index  INTEGER NOT NULL,
  column_name   TEXT,
  index_type    TEXT,
  created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name, table_name, index_name, seq_in_index)
);

CREATE TABLE IF NOT EXISTS md_change_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id   INTEGER NOT NULL,
  database_name TEXT NOT NULL,
  table_name    TEXT,
  column_name   TEXT,
  change_type   TEXT NOT NULL,
  object_type   TEXT NOT NULL,
  old_value     TEXT,
  new_value     TEXT,
  changed_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS md_table_biz (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id     INTEGER NOT NULL,
  database_name   TEXT NOT NULL,
  table_name      TEXT NOT NULL,
  table_biz_desc  TEXT,
  business_domain TEXT,
  owner           TEXT,
  ai_generated    INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name, table_name)
);

CREATE TABLE IF NOT EXISTS md_column_biz (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id     INTEGER NOT NULL,
  database_name   TEXT NOT NULL,
  table_name      TEXT NOT NULL,
  column_name     TEXT NOT NULL,
  biz_desc        TEXT,
  sensitivity     TEXT,
  business_domain TEXT,
  ai_generated    INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name, table_name, column_name)
);

CREATE TABLE IF NOT EXISTS md_code_dict (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id   INTEGER NOT NULL,
  database_name TEXT NOT NULL,
  table_name    TEXT NOT NULL,
  column_name   TEXT NOT NULL,
  code_value    TEXT NOT NULL,
  code_label    TEXT,
  ai_generated  INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name, table_name, column_name, code_value)
);
