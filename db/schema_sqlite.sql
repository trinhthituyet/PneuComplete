-- PneuComplete — schema SQLite (bản dịch từ db/schema.sql)
-- Dùng cho pha ingest. Chuyển sang Postgres ở pha 8 khi web app cần đa người dùng.
-- Quy ước dịch: jsonb→TEXT(json) · serial→INTEGER PK AUTOINCREMENT
--               timestamptz→TEXT ISO8601 · numeric→REAL · boolean→INTEGER 0/1
--               GIN(jsonb)→index trên json_extract() · pg_trgm→FTS5

pragma journal_mode = wal;
pragma foreign_keys = on;

-- ═══════════════════════════════════════════════════════════════════
-- A. TRUY XUẤT NGUỒN
-- ═══════════════════════════════════════════════════════════════════

create table if not exists source_doc (
  id         integer primary key autoincrement,
  kind       text not null check (kind in ('pdf','xlsx','web','manual')),
  uri        text not null,
  title      text,
  sha256     text,
  page_count integer,
  fetched_at text not null default (datetime('now')),
  unique (uri, sha256)
);

-- ═══════════════════════════════════════════════════════════════════
-- B. PHÂN LOẠI & SERIES
-- ═══════════════════════════════════════════════════════════════════

create table if not exists category (
  id        integer primary key autoincrement,
  code      text unique not null,          -- slug từ URL: 'air-cylinders'
  name      text not null,
  parent_id integer references category(id),
  layer     text check (layer in ('actuator','valve','air_prep','piping',
                                  'accessory','electrical','other'))
);

create table if not exists series (
  id          integer primary key autoincrement,
  code        text not null,                -- 'CM2/CDM2/Z', 'AS'
  catalog_id  text,                         -- id trong URL: 'CM2-CDM2-Z-E'
  -- Tiền tố THẬT của mã hàng, phải khai tường minh vì không suy ra được từ
  -- catalog_id: cả AS-E-E (núm thường) và AS1-E (push-lock) đều có mã bắt đầu
  -- bằng 'AS', nhưng catalog_id 'AS1-E' sinh ra tiền tố giả 'AS1' làm parser
  -- chọn sai ngữ pháp và báo dư ký tự.
  part_prefix text,
  -- 'manual' = ngữ pháp do người đọc catalog và nhập tay (đã duyệt) ·
  -- 'auto'   = do parser PDF sinh. Parser KHÔNG được ghi đè bản 'manual':
  -- đã gặp lỗi thật — lệnh `grammar` chạy lại đè ô 'bore' lên ngữ pháp TU
  -- nhập tay và làm parser hỏng.
  grammar_source text,
  maker       text not null default 'SMC',
  name        text,                         -- 'Air Cylinder'
  category_id integer references category(id),
  category_raw text,                        -- chuỗi category gốc từ indexSearch
  url         text,
  catalog_ref text,
  source_id   integer references source_doc(id),
  notes       text,
  unique (maker, catalog_id)
);

create index if not exists series_code_idx on series (code);
create index if not exists series_cat_idx  on series (category_id);

-- ═══════════════════════════════════════════════════════════════════
-- C. NGỮ PHÁP MÃ HÀNG
-- ═══════════════════════════════════════════════════════════════════

create table if not exists code_slot (
  id          integer primary key autoincrement,
  series_id   integer not null references series(id) on delete cascade,
  pos         integer not null,
  name        text not null,
  is_required integer not null default 1,
  separator   text not null default '',
  -- Số chữ số tối thiểu cho ô kiểu integer, đệm 0 phía trước. Nhiều mã SMC
  -- dùng mã 2 chữ số có đệm: số station của SS5Y ghi '05' chứ không phải '5'
  -- (catalog: '02 = 2 stations'). Không đệm thì sinh ra mã không tồn tại.
  pad         integer,
  value_type  text not null default 'enum'
              check (value_type in ('enum','integer','free')),
  unique (series_id, pos)
);

create table if not exists code_option (
  id       integer primary key autoincrement,
  slot_id  integer not null references code_slot(id) on delete cascade,
  code     text not null,
  label    text,
  attrs    text not null default '{}' check (json_valid(attrs)),
  requires text not null default '{}' check (json_valid(requires)),
  unique (slot_id, code)
);

create table if not exists code_range (
  slot_id integer primary key references code_slot(id) on delete cascade,
  min_val real not null,
  max_val real not null,
  step    real,
  unit    text
);

-- ═══════════════════════════════════════════════════════════════════
-- D. SẢN PHẨM
-- ═══════════════════════════════════════════════════════════════════

create table if not exists part (
  id          integer primary key autoincrement,
  part_number text not null,
  maker       text not null default 'SMC',
  series_id   integer references series(id),
  description text,
  attrs       text not null default '{}' check (json_valid(attrs)),
  is_verified integer not null default 0,
  verified_by text,
  verified_at text,
  source_id   integer references source_doc(id),
  source_page integer,
  created_at  text not null default (datetime('now')),
  unique (maker, part_number)
);

create index if not exists part_series_idx on part (series_id);
-- thay cho GIN: index biểu thức trên các spec tra cứu nhiều nhất
create index if not exists part_bore_idx on part (json_extract(attrs,'$.bore_mm'));
create index if not exists part_port_idx on part (json_extract(attrs,'$.port_size'));

-- thay cho pg_trgm: tìm mã hàng gần đúng
create virtual table if not exists part_fts using fts5(
  part_number, description, content='part', content_rowid='id'
);

create table if not exists price (
  id         integer primary key autoincrement,
  part_id    integer not null references part(id) on delete cascade,
  currency   text not null default 'VND',
  list_price real,
  valid_from text not null default (date('now')),
  source_id  integer references source_doc(id),
  unique (part_id, currency, valid_from)
);

-- ═══════════════════════════════════════════════════════════════════
-- E. GIAO DIỆN KẾT NỐI
-- ═══════════════════════════════════════════════════════════════════

create table if not exists part_interface (
  id         integer primary key autoincrement,
  part_id    integer not null references part(id) on delete cascade,
  role       text not null,
  kind       text not null,
  gender     text check (gender in ('male','female','neutral')),
  standard   text,
  size       text,
  tube_od_mm real,
  qty        integer not null default 1,
  attrs      text not null default '{}' check (json_valid(attrs)),
  check (kind <> 'thread' or (standard is not null and size is not null))
);

create index if not exists pi_part_idx  on part_interface (part_id);
create index if not exists pi_match_idx on part_interface (kind, standard, size, tube_od_mm);

create table if not exists thread_compat (
  male_standard   text not null,
  female_standard text not null,
  is_ok           integer not null,
  note            text,
  primary key (male_standard, female_standard)
);

-- ═══════════════════════════════════════════════════════════════════
-- F. LUẬT KỸ THUẬT
-- ═══════════════════════════════════════════════════════════════════

create table if not exists rule (
  id         integer primary key autoincrement,
  code       text unique not null,
  name       text not null,
  scope      text not null check (scope in ('per_actuator','per_valve','per_station','per_system')),
  priority   integer not null default 100,
  when_expr  text not null check (json_valid(when_expr)),
  then_spec  text not null check (json_valid(then_spec)),
  rationale  text not null,
  source     text,
  enabled    integer not null default 1,
  created_at text not null default (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════════
-- G. LỊCH SỬ BOM
-- ═══════════════════════════════════════════════════════════════════

create table if not exists machine (
  id         integer primary key autoincrement,
  name       text not null,
  customer   text,
  built_year integer,
  is_golden  integer not null default 0,
  notes      text,
  source_id  integer references source_doc(id)
);

create table if not exists bom_line (
  id         integer primary key autoincrement,
  machine_id integer not null references machine(id) on delete cascade,
  part_id    integer references part(id),
  raw_code   text not null,
  raw_desc   text,
  qty        real not null default 1,
  unit       text default 'pcs',
  layer      text
);

create index if not exists bom_machine_idx on bom_line (machine_id);
create index if not exists bom_part_idx    on bom_line (part_id);

create table if not exists cooccurrence (
  a_series_id integer not null references series(id) on delete cascade,
  b_series_id integer not null references series(id) on delete cascade,
  support     integer not null,
  confidence  real not null,
  lift        real not null,
  updated_at  text not null default (datetime('now')),
  primary key (a_series_id, b_series_id)
);

-- ═══════════════════════════════════════════════════════════════════
-- H. PHIÊN LÀM VIỆC
-- ═══════════════════════════════════════════════════════════════════

create table if not exists project (
  id         integer primary key autoincrement,
  name       text not null,
  config     text not null default '{}' check (json_valid(config)),
  created_at text not null default (datetime('now')),
  updated_at text not null default (datetime('now'))
);

create table if not exists project_input (
  id         integer primary key autoincrement,
  project_id integer not null references project(id) on delete cascade,
  part_id    integer references part(id),
  raw_code   text not null,
  qty        integer not null default 1,
  overrides  text not null default '{}' check (json_valid(overrides))
);

create table if not exists project_output (
  id            integer primary key autoincrement,
  project_id    integer not null references project(id) on delete cascade,
  part_id       integer references part(id),
  proposed_code text,
  qty           real not null,
  layer         text not null,
  rule_code     text references rule(code),
  rationale     text not null,
  confidence    real check (confidence between 0 and 1),
  status        text not null default 'suggested'
                check (status in ('suggested','accepted','rejected','gap')),
  requirement   text check (requirement is null or json_valid(requirement)),
  alternatives  text not null default '[]' check (json_valid(alternatives))
);

create index if not exists po_project_idx on project_output (project_id, layer);

create table if not exists project_warning (
  id         integer primary key autoincrement,
  project_id integer not null references project(id) on delete cascade,
  severity   text not null check (severity in ('info','warn','error')),
  code       text not null,
  message    text not null,
  detail     text not null default '{}' check (json_valid(detail))
);

-- ═══════════════════════════════════════════════════════════════════
-- I. CRAWL
-- ═══════════════════════════════════════════════════════════════════

create table if not exists crawl_target (
  id              integer primary key autoincrement,
  url             text unique not null,
  kind            text not null
                  check (kind in ('robots','index_letter','category','subcategory',
                                  'series','accessory','pdf','other')),
  series_code     text,
  depth           integer not null default 0,
  discovered_from integer references crawl_target(id),
  priority        integer not null default 100,
  state           text not null default 'pending'
                  check (state in ('pending','fetching','done','failed','skipped')),
  attempts        integer not null default 0,
  last_error      text,
  robots_allowed  integer,
  enqueued_at     text not null default (datetime('now')),
  completed_at    text
);

create index if not exists ct_queue_idx  on crawl_target (state, priority, depth)
       where state = 'pending';
create index if not exists ct_series_idx on crawl_target (series_code);
create index if not exists ct_kind_idx   on crawl_target (kind, state);

create table if not exists crawl_fetch (
  id            integer primary key autoincrement,
  target_id     integer not null references crawl_target(id) on delete cascade,
  fetched_at    text not null default (datetime('now')),
  http_status   integer,
  content_type  text,
  sha256        text not null,
  body_path     text not null,
  byte_size     integer,
  elapsed_ms    integer,
  source_doc_id integer references source_doc(id)
);

create index if not exists cf_target_idx on crawl_fetch (target_id, fetched_at desc);
create index if not exists cf_sha_idx    on crawl_fetch (sha256);

create table if not exists extract_run (
  id             integer primary key autoincrement,
  fetch_id       integer not null references crawl_fetch(id) on delete cascade,
  parser_name    text not null,
  parser_version text not null,
  started_at     text not null default (datetime('now')),
  finished_at    text,
  status         text check (status in ('ok','partial','failed')),
  rows_out       integer not null default 0,
  rows_flagged   integer not null default 0,
  log            text not null default '{}' check (json_valid(log))
);

create index if not exists er_fetch_idx  on extract_run (fetch_id);
create index if not exists er_parser_idx on extract_run (parser_name, parser_version);

create table if not exists review_item (
  id             integer primary key autoincrement,
  extract_run_id integer not null references extract_run(id) on delete cascade,
  entity_type    text not null
                 check (entity_type in ('series','code_slot','code_option',
                                        'part','part_interface','price','rule_hint')),
  proposed       text not null check (json_valid(proposed)),
  existing_id    integer,
  diff           text check (diff is null or json_valid(diff)),
  confidence     real check (confidence between 0 and 1),
  auto_approved  integer not null default 0,
  state          text not null default 'pending'
                 check (state in ('pending','approved','rejected','edited')),
  reviewed_by    text,
  reviewed_at    text,
  note           text
);

create index if not exists ri_queue_idx on review_item (state, confidence desc)
       where state = 'pending';
create index if not exists ri_run_idx   on review_item (extract_run_id);
