-- PneuComplete — PostgreSQL 16 schema
-- Xem docs/DESIGN.md §2 để hiểu lý do thiết kế.

create extension if not exists pg_trgm;      -- tìm mã hàng gần đúng

-- ═══════════════════════════════════════════════════════════════════
-- A. TRUY XUẤT NGUỒN — mọi dữ liệu phải trả lời được "lấy ở đâu"
-- ═══════════════════════════════════════════════════════════════════

create table source_doc (
  id          serial primary key,
  kind        text not null check (kind in ('pdf','xlsx','web','manual')),
  uri         text not null,                    -- đường dẫn file hoặc URL
  title       text,
  sha256      text,                             -- phát hiện catalog đã đổi bản
  page_count  int,
  fetched_at  timestamptz not null default now(),
  unique (uri, sha256)
);

-- ═══════════════════════════════════════════════════════════════════
-- B. PHÂN LOẠI & SERIES
-- ═══════════════════════════════════════════════════════════════════

create table category (
  id        serial primary key,
  code      text unique not null,               -- 'actuator.cylinder.compact'
  name      text not null,
  parent_id int references category(id),
  layer     text not null
            check (layer in ('actuator','valve','air_prep','piping','accessory','electrical'))
);

create table series (
  id          serial primary key,
  code        text not null,                    -- 'CM2', 'AS2000', 'SY3000', 'KQ2'
  maker       text not null default 'SMC',
  name        text,
  category_id int not null references category(id),
  catalog_ref text,                             -- 'CAT.ES20-201 p.34'
  source_id   int references source_doc(id),
  notes       text,
  unique (maker, code)
);

-- ═══════════════════════════════════════════════════════════════════
-- C. NGỮ PHÁP MÃ HÀNG — parse & sinh mã, thay cho danh sách SKU phẳng
-- ═══════════════════════════════════════════════════════════════════

create table code_slot (
  id          serial primary key,
  series_id   int not null references series(id) on delete cascade,
  pos         int not null,                     -- thứ tự trong mã, từ 1
  name        text not null,                    -- 'bore','mounting','stroke','auto_switch'
  is_required boolean not null default true,
  separator   text not null default '',         -- ký tự đứng trước ô này, vd '-'
  value_type  text not null default 'enum'
              check (value_type in ('enum','integer','free')),
  unique (series_id, pos)
);

create table code_option (
  id       serial primary key,
  slot_id  int not null references code_slot(id) on delete cascade,
  code     text not null,                       -- '32', 'L', 'M9BW'
  label    text,
  -- spec mà lựa chọn này kéo theo; merge attrs của mọi option = spec đầy đủ
  attrs    jsonb not null default '{}',         -- {"bore_mm":32,"port_size":"Rc1/8"}
  -- điều kiện hợp lệ, vd option này chỉ dùng được khi bore >= 32
  requires jsonb not null default '{}',
  unique (slot_id, code)
);

-- Ô kiểu integer (stroke) dùng dải thay vì liệt kê
create table code_range (
  slot_id  int primary key references code_slot(id) on delete cascade,
  min_val  numeric not null,
  max_val  numeric not null,
  step     numeric,                             -- stroke CM2: bước 25/50mm
  unit     text
);

-- ═══════════════════════════════════════════════════════════════════
-- D. SẢN PHẨM ĐÃ HOÀN CHỈNH (materialize khi cần, không sinh trước hàng loạt)
-- ═══════════════════════════════════════════════════════════════════

create table part (
  id           bigserial primary key,
  part_number  text not null,
  maker        text not null default 'SMC',
  series_id    int references series(id),
  description  text,
  -- toàn bộ spec đã phẳng hoá: bore_mm, stroke_mm, port_size, cv, voltage, tube_od_mm...
  attrs        jsonb not null default '{}',
  is_verified  boolean not null default false,  -- true = người đã đối chiếu catalog
  verified_by  text,
  verified_at  timestamptz,
  source_id    int references source_doc(id),
  source_page  int,
  created_at   timestamptz not null default now(),
  unique (maker, part_number)
);

create index part_attrs_gin  on part using gin (attrs jsonb_path_ops);
create index part_series_idx  on part (series_id);
create index part_number_trgm on part using gin (part_number gin_trgm_ops);

create table price (
  id         bigserial primary key,
  part_id    bigint not null references part(id) on delete cascade,
  currency   char(3) not null default 'VND',
  list_price numeric(14,2),
  valid_from date not null default current_date,
  source_id  int references source_doc(id),
  unique (part_id, currency, valid_from)
);

-- ═══════════════════════════════════════════════════════════════════
-- E. GIAO DIỆN KẾT NỐI — trái tim của khả năng suy luận
-- ═══════════════════════════════════════════════════════════════════

create table part_interface (
  id         bigserial primary key,
  part_id    bigint not null references part(id) on delete cascade,
  role       text not null,        -- 'air_port','air_in','air_out','exhaust',
                                   -- 'mount','rod_end','switch_rail','electrical'
  kind       text not null,        -- 'thread','onetouch','tube','flange','rail','connector'
  gender     text check (gender in ('male','female','neutral')),
  standard   text,                 -- 'Rc','R','NPT','G','M','SMC-D'
  size       text,                 -- '1/8','1/4','M5'
  tube_od_mm numeric,
  qty        int not null default 1,
  attrs      jsonb not null default '{}',
  check (kind <> 'thread' or (standard is not null and size is not null))
);

create index pi_part_idx  on part_interface (part_id);
create index pi_match_idx on part_interface (kind, standard, size, tube_od_mm);

-- Bảng tương thích chuẩn ren: R lắp được vào Rc, G không lắp NPT...
create table thread_compat (
  male_standard   text not null,
  female_standard text not null,
  is_ok           boolean not null,
  note            text,
  primary key (male_standard, female_standard)
);

-- ═══════════════════════════════════════════════════════════════════
-- F. LUẬT KỸ THUẬT — dữ liệu, không hard-code
-- ═══════════════════════════════════════════════════════════════════

create table rule (
  id        serial primary key,
  code      text unique not null,               -- 'R-SPD-01'
  name      text not null,
  scope     text not null
            check (scope in ('per_actuator','per_valve','per_station','per_system')),
  priority  int not null default 100,           -- nhỏ hơn = chạy trước
  when_expr jsonb not null,                     -- điều kiện kích hoạt
  then_spec jsonb not null,                     -- requirement sinh ra
  rationale text not null,                       -- LUÔN phải có: hiện lên UI
  source    text,                                -- trang catalog / tên người quyết
  enabled   boolean not null default true,
  created_at timestamptz not null default now()
);

-- ═══════════════════════════════════════════════════════════════════
-- G. LỊCH SỬ BOM — bộ kiểm chứng + nguồn xếp hạng
-- ═══════════════════════════════════════════════════════════════════

create table machine (
  id        serial primary key,
  name      text not null,
  customer  text,
  built_year int,
  is_golden boolean not null default false,     -- dùng làm test case tự động
  notes     text,
  source_id int references source_doc(id)
);

create table bom_line (
  id          bigserial primary key,
  machine_id  int not null references machine(id) on delete cascade,
  part_id     bigint references part(id),       -- null = chưa khớp được vào catalog
  raw_code    text not null,                    -- mã như trong Excel gốc
  raw_desc    text,
  qty         numeric not null default 1,
  unit        text default 'pcs',
  layer       text                              -- actuator/valve/air_prep/piping/accessory
);

create index bom_machine_idx on bom_line (machine_id);
create index bom_part_idx    on bom_line (part_id);

-- Cặp series hay đi cùng nhau; tính lại bằng job, KHÔNG tự thành luật
create table cooccurrence (
  a_series_id int not null references series(id) on delete cascade,
  b_series_id int not null references series(id) on delete cascade,
  support     int     not null,                 -- số máy có cả hai
  confidence  numeric not null,                 -- P(B|A)
  lift        numeric not null,
  updated_at  timestamptz not null default now(),
  primary key (a_series_id, b_series_id)
);

-- ═══════════════════════════════════════════════════════════════════
-- H. PHIÊN LÀM VIỆC CỦA NGƯỜI DÙNG
-- ═══════════════════════════════════════════════════════════════════

create table project (
  id         serial primary key,
  name       text not null,
  -- mặc định toàn dự án: {"pressure_mpa":0.5,"thread":"Rc","tube_od_mm":6,
  --                       "voltage":"DC24V","automation":true}
  config     jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Actuator người dùng nhập vào
create table project_input (
  id          bigserial primary key,
  project_id  int not null references project(id) on delete cascade,
  part_id     bigint references part(id),
  raw_code    text not null,
  qty         int not null default 1,
  overrides   jsonb not null default '{}'       -- ghi đè spec cho riêng dòng này
);

-- Dòng BOM engine sinh ra, có giải thích và trạng thái xác nhận
create table project_output (
  id          bigserial primary key,
  project_id  int not null references project(id) on delete cascade,
  part_id     bigint references part(id),
  proposed_code text,                            -- khi chưa materialize thành part
  qty         numeric not null,
  layer       text not null,
  rule_code   text references rule(code),
  rationale   text not null,                     -- hiện trực tiếp cho người dùng
  confidence  numeric check (confidence between 0 and 1),
  status      text not null default 'suggested'
              check (status in ('suggested','accepted','rejected','gap')),
  -- status='gap' = engine biết cần gì nhưng không chọn được → yêu cầu người quyết định
  requirement jsonb,                             -- requirement gốc, để debug
  alternatives jsonb not null default '[]'       -- các candidate bị xếp sau
);

create index po_project_idx on project_output (project_id, layer);

-- Cảnh báo từ bước validate (Cv thiếu, tốc độ vượt dải, ren lẫn chuẩn...)
create table project_warning (
  id         bigserial primary key,
  project_id int not null references project(id) on delete cascade,
  severity   text not null check (severity in ('info','warn','error')),
  code       text not null,
  message    text not null,
  detail     jsonb not null default '{}'
);

-- ═══════════════════════════════════════════════════════════════════
-- I. CRAWL — hạ tầng thu thập (nguồn dữ liệu chính)
--    Tầng 1 chỉ tải & lưu nguyên trạng. Tầng 2 parse từ cache.
--    Xem docs/DESIGN.md §4.
-- ═══════════════════════════════════════════════════════════════════

-- Hàng đợi URL. Loại trang khớp với cấu trúc thật của smcworld (xem docs/RECON.md §4).
-- Lưu ý: How-to-Order / spec table KHÔNG phải loại URL — chúng nằm BÊN TRONG PDF.
create table crawl_target (
  id            bigserial primary key,
  url           text unique not null,
  kind          text not null
                check (kind in ('index_letter',   -- /webcatalog/en-jp/indexSearch/<A..Z>
                                'category',       -- /webcatalog/en-jp/<cat>/
                                'subcategory',    -- /webcatalog/en-jp/<cat>/<subcat>/
                                'series',         -- seriesList/?id=<SERIES>-E
                                'accessory',      -- trang "Applicable ..."
                                'pdf',            -- ca01.smcworld.com/catalog/...
                                'other')),
  series_code   text,                             -- biết trước thì gán, để ưu tiên
  depth         int not null default 0,
  discovered_from bigint references crawl_target(id),
  -- 'pdf' của series trong phạm vi phải có priority nhỏ nhất: nó chứa code grammar
  priority      int not null default 100,
  state         text not null default 'pending'
                check (state in ('pending','fetching','done','failed','skipped')),
  attempts      int not null default 0,
  last_error    text,
  robots_allowed boolean,                          -- null = chưa kiểm tra
  enqueued_at   timestamptz not null default now(),
  completed_at  timestamptz
);

-- Chỉ số này quyết định hiệu năng vòng lặp crawler
create index ct_queue_idx  on crawl_target (state, priority, depth)
       where state = 'pending';
create index ct_series_idx on crawl_target (series_code);

-- Mỗi lần tải một URL. Body nằm trên đĩa, DB chỉ giữ metadata.
create table crawl_fetch (
  id            bigserial primary key,
  target_id     bigint not null references crawl_target(id) on delete cascade,
  fetched_at    timestamptz not null default now(),
  http_status   int,
  content_type  text,
  sha256        text not null,                    -- sha không đổi ⇒ khỏi parse lại
  body_path     text not null,                    -- cache/<sha[:2]>/<sha256>.<ext>
  byte_size     bigint,
  elapsed_ms    int,
  source_doc_id int references source_doc(id)     -- để part trỏ về được nguồn
);

create index cf_target_idx on crawl_fetch (target_id, fetched_at desc);
create index cf_sha_idx    on crawl_fetch (sha256);

-- Một lần chạy parser trên một bản tải. Giữ parser_version để truy ngược
-- đúng tập dữ liệu cần duyệt lại khi phát hiện parser sai.
create table extract_run (
  id             bigserial primary key,
  fetch_id       bigint not null references crawl_fetch(id) on delete cascade,
  parser_name    text not null,
  parser_version text not null,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  status         text check (status in ('ok','partial','failed')),
  rows_out       int not null default 0,
  rows_flagged   int not null default 0,
  log            jsonb not null default '{}'
);

create index er_fetch_idx  on extract_run (fetch_id);
create index er_parser_idx on extract_run (parser_name, parser_version);

-- Hàng đợi duyệt. Parser KHÔNG ghi thẳng vào part/code_option — đi qua đây.
create table review_item (
  id             bigserial primary key,
  extract_run_id bigint not null references extract_run(id) on delete cascade,
  entity_type    text not null
                 check (entity_type in ('series','code_slot','code_option',
                                        'part','part_interface','price','rule_hint')),
  proposed       jsonb not null,                  -- dữ liệu parser đề xuất
  existing_id    bigint,                          -- có sẵn ⇒ đây là cập nhật
  diff           jsonb,                           -- lệch ở đâu so với bản đang có
  confidence     numeric check (confidence between 0 and 1),
  -- cao khi: mã parse lại được bằng code grammar + spec trong dải hợp lý
  --          + khớp PDF/BOM cũ  → cho auto-approve, lấy mẫu 5% kiểm tay
  auto_approved  boolean not null default false,
  state          text not null default 'pending'
                 check (state in ('pending','approved','rejected','edited')),
  reviewed_by    text,
  reviewed_at    timestamptz,
  note           text
);

create index ri_queue_idx on review_item (state, confidence desc)
       where state = 'pending';
create index ri_run_idx   on review_item (extract_run_id);
