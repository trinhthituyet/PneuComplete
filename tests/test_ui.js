/* Test logic thuần của UI cây trong web/index.html — chạy bằng node.
 *
 *   node tests/test_ui.js
 *
 * VÌ SAO CÓ TỆP NÀY: tôi không click được. Nhưng yêu cầu "đảm bảo sơ đồ KHÔNG
 * CHỒNG LẤN" là thứ CHỨNG MINH ĐƯỢC bằng máy: sinh cây rồi kiểm mọi cặp hộp có
 * giao nhau hay không. Đó là kiểm mạnh hơn nhìn mắt.
 *
 * BÀI HỌC ĐÃ TRẢ GIÁ: bản canvas trước test portPos() và nó xanh, nhưng UI vẫn
 * sai vì lỗi nằm ở CSS phía bên kia của hợp đồng. Nên ngoài hàm thuần, test còn
 * đọc CSS/HTML để chặn đúng lớp lỗi đó.
 *
 * KHÔNG thay thế mở trình duyệt: bấm, cuộn, nhập liệu vẫn phải người thử.
 */
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];

const stub = `
  const stubEl = () => {
    const e = { style:{}, dataset:{}, value:'', checked:false, textContent:'',
      innerHTML:'', title:'', placeholder:'', type:'', colSpan:1, id:'',
      classList:{add(){},remove(){},toggle(){},contains(){return false}},
      appendChild(){return e}, remove(){}, addEventListener(){}, setAttribute(){},
      closest(){return null}, focus(){},
      getBoundingClientRect(){return {left:0,top:0,width:900,height:600}},
      querySelector(){return stubEl()}, querySelectorAll(){return []},
      onclick:null, onchange:null, oninput:null };
    return e;
  };
  const document = { querySelector: stubEl, querySelectorAll: () => [],
    getElementById: stubEl, createElement: stubEl, createElementNS: stubEl,
    body: stubEl() };
  const addEventListener = () => {};
  const fetch = async () => ({ json: async () => ({}) });
  const Option = function(a,b){ return {text:a,value:b}; };
`;
const body = js.replace(/^boot\(\);\s*$/m, '');

let ok = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { ok++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + '   ' + detail); }
};

let S;
try {
  S = new Function(stub + body + `
    return {layoutTree, boxW, walk, statusOf, gapWhy, allowedChildren, addStation,
            BOXH, VGAP, HGAP, PADX, PADY,
            setTree: t => { TREE = t; }, getTree: () => TREE,
            setGroups: g => { GROUPS = g; },
            setParentOf: p => { PARENT_OF = p; },
            setSeq: v => { seq = v; }};`)();
} catch (e) {
  console.log('  ✗ không nạp được JS: ' + e.message);
  process.exit(1);
}

// ── cây mẫu: giống máy thật, 1 manifold nhiều trạm ──────────────────────────
function mkTree(nStations, extra = {}) {
  let id = 0;
  const nid = () => 'n' + (id++);
  const stations = [];
  for (let i = 0; i < nStations; i++) {
    const sc = [
      { id: nid(), type: 'speed_controller', name: 'Tiết lưu cửa A',
        code: 'AS2201F-01-06SA', attrs: {}, children: [] },
      { id: nid(), type: 'speed_controller', name: 'Tiết lưu cửa B',
        code: '', attrs: {}, children: [] }];
    const cyl = { id: nid(), type: 'cylinder',
      name: extra.longName ? 'Xy-lanh đẩy cửa lò gia nhiệt số ' + (i + 1) : 'Xy-lanh',
      code: 'CDM2L32-500Z', attrs: {}, children: sc };
    stations.push({ id: nid(), type: 'valve', name: 'Trạm SV' + (i + 1),
      code: 'SY5220-5MZE-C6', attrs: {}, children: [cyl] });
  }
  const mfd = { id: nid(), type: 'manifold', name: 'Manifold',
    code: 'SS5Y5-20-12', attrs: {}, children: stations };
  return { id: nid(), type: 'frl', name: 'Bộ xử lý khí (nguồn chung)',
    code: 'AC30B-03DG-A', attrs: {}, children: [mfd] };
}
S.setGroups({ frl: { layer: 'air_prep' }, manifold: { layer: 'valve' },
  valve: { layer: 'valve' }, cylinder: { layer: 'actuator' },
  speed_controller: { layer: 'accessory' } });

// ── KHÔNG CHỒNG LẤN — kiểm mọi cặp hộp ──────────────────────────────────────
console.log('\nkhong_chong_lan');
function overlaps(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w &&
         a.y < b.y + S.BOXH && b.y < a.y + S.BOXH;
}
function checkNoOverlap(tree, label) {
  S.setTree(tree);
  const { pos, width, height } = S.layoutTree(tree);
  const boxes = [...S.walk(tree)].map(([n]) => ({ id: n.id, ...pos.get(n.id) }));
  const bad = [];
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++)
      if (overlaps(boxes[i], boxes[j])) bad.push([boxes[i].id, boxes[j].id]);
  check(`${label}: ${boxes.length} hộp, 0 cặp chồng lấn`,
    bad.length === 0, `chồng: ${JSON.stringify(bad.slice(0, 3))}`);
  // mọi hộp phải nằm TRỌN trong khung — prototype bị cắt mất phần trên vì
  // mainY cố định 380 và box mọc lên có thể ra ngoài y<0
  const out = boxes.filter(b => b.x < 0 || b.y < 0 ||
    b.x + b.w > width + 0.01 || b.y + S.BOXH > height + 0.01);
  check(`${label}: mọi hộp nằm trọn trong khung ${Math.round(width)}×${Math.round(height)}`,
    out.length === 0, JSON.stringify(out.slice(0, 2)));
  return { pos, width, height, boxes };
}
checkNoOverlap(mkTree(1), '1 trạm');
checkNoOverlap(mkTree(9), '9 trạm (như prototype)');
checkNoOverlap(mkTree(40), '40 trạm');
checkNoOverlap(mkTree(9, { longName: true }), '9 trạm tên rất dài');

// cây lệch: một trạm có 12 con, trạm khác không có con
(function () {
  const t = mkTree(3);
  const deep = t.children[0].children[0];       // trạm SV1
  for (let k = 0; k < 12; k++)
    deep.children.push({ id: 'x' + k, type: 'speed_controller',
      name: 'phụ kiện ' + k, code: '', attrs: {}, children: [] });
  checkNoOverlap(t, 'cây lệch (1 trạm 12 con)');
})();

// ── khung phải giãn theo nội dung, không cố định ─────────────────────────────
console.log('\nkhung_gian_theo_noi_dung');
const a = checkNoOverlap(mkTree(3), 'so sánh 3 trạm');
const b = checkNoOverlap(mkTree(12), 'so sánh 12 trạm');
check('nhiều trạm hơn → khung CAO hơn (không cắt bớt)', b.height > a.height,
  `${a.height} → ${b.height}`);
const c = checkNoOverlap(mkTree(3, { longName: true }), 'so sánh tên dài');
check('tên dài hơn → cột RỘNG hơn (không tràn sang cột bên)', c.width > a.width,
  `${a.width} → ${c.width}`);
// Quét CODE, không quét comment: comment trong index.html có nhắc "mainY=380"
// khi giải thích lỗi của prototype, và lần đầu test bắt đúng vào chữ đó.
const jsCode = js.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('không có toạ độ cố định kiểu mainY=380 trong CODE',
  !/mainY\s*=\s*\d/.test(jsCode) && !/colW\s*=\s*\d/.test(jsCode),
  (jsCode.match(/.*(mainY|colW)\s*=\s*\d.*/) || [''])[0].slice(0, 70));

// ── cha nằm giữa các con ─────────────────────────────────────────────────────
console.log('\ncha_nam_giua_cac_con');
(function () {
  const t = mkTree(4);
  S.setTree(t);
  const { pos } = S.layoutTree(t);
  const mfd = t.children[0];
  const ys = mfd.children.map(c => pos.get(c.id).y);
  const mid = (Math.min(...ys) + Math.max(...ys)) / 2;
  check('manifold nằm giữa 4 trạm con',
    Math.abs(pos.get(mfd.id).y - mid) < 0.01,
    `${pos.get(mfd.id).y} vs ${mid}`);
  check('cấp sâu hơn nằm bên PHẢI cấp cha (dòng khí trái→phải)',
    pos.get(mfd.id).x > pos.get(t.id).x &&
    pos.get(mfd.children[0].id).x > pos.get(mfd.id).x);
})();

// ── trạng thái node ──────────────────────────────────────────────────────────
console.log('\ntrang_thai_node');
check('có mã → đã chốt', S.statusOf({ code: 'X', attrs: {} }) === 'specified');
check('không mã, có thuộc tính → mới biết loại',
  S.statusOf({ code: '', attrs: { bore_mm: 32 } }) === 'type_only');
check('không mã, không thuộc tính → trống',
  S.statusOf({ code: '', attrs: {} }) === 'empty');

// ── quy tắc cha–con lấy TỪ ENGINE, không hard-code ở UI ─────────────────────
console.log('\nquy_tac_cha_con_tu_engine');
S.setParentOf({
  cylinder: { allowed: ['valve'], why: 'van điều khiển xy-lanh' },
  speed_controller: { allowed: ['cylinder'], why: 'vặn vào cửa xy-lanh' },
  valve: { allowed: ['manifold', 'frl', null], why: '' },
  manifold: { allowed: ['frl', null], why: '' },
});
check('thêm vào VAN chỉ hiện xy-lanh',
  JSON.stringify(S.allowedChildren('valve')) === '["cylinder"]',
  JSON.stringify(S.allowedChildren('valve')));
check('thêm vào XY-LANH chỉ hiện tiết lưu',
  JSON.stringify(S.allowedChildren('cylinder')) === '["speed_controller"]',
  JSON.stringify(S.allowedChildren('cylinder')));
check('thêm vào MANIFOLD chỉ hiện van',
  JSON.stringify(S.allowedChildren('manifold')) === '["valve"]',
  JSON.stringify(S.allowedChildren('manifold')));
check('UI không hard-code danh sách cha–con (đọc từ /api/groups)',
  /parent_of/.test(js) && !/const\s+PARENT_OF\s*=\s*\{[^}]*cylinder/.test(js));

// ── một trạm = 1 van + 1 xy-lanh, chỉ cần nhập mã xy-lanh ───────────────────
console.log('\nmot_tram_toi_thieu');
(function () {
  S.setTree({ id: 'r', type: 'frl', name: 'FRL', code: '', attrs: {}, children: [] });
  S.setSeq(1);
  S.addStation();
  const t = S.getTree();
  const types = [...S.walk(t)].map(([n]) => n.type);
  check('thêm trạm sinh đúng 1 van + 1 xy-lanh',
    types.filter(x => x === 'valve').length === 1 &&
    types.filter(x => x === 'cylinder').length === 1, JSON.stringify(types));
  const cyl = [...S.walk(t)].map(([n]) => n).find(n => n.type === 'cylinder');
  const val = [...S.walk(t)].map(([n]) => n).find(n => n.type === 'valve');
  check('xy-lanh là CON của van (van điều khiển xy-lanh)',
    (val.children || []).includes(cyl));
  check('cả hai để trống mã — engine tự chọn van, người dùng chỉ nhập xy-lanh',
    !cyl.code && !val.code);
})();

// ── node CHƯA CÓ MÃ: sơ đồ phải NÓI RA, không vẽ mờ rồi thôi ───────────────
// Yêu cầu của bạn: vật tư thiếu mã vẫn phải liệt kê ở CẢ sơ đồ và BOM. Trên sơ đồ
// nó khác hẳn node "bạn chưa gõ gì": engine BIẾT máy cần thứ đó, chỉ thiếu đầu vào.
console.log('\nnode_chua_co_ma_tren_so_do');
const GAPN = { id: 'g1', type: 'fitting', name: 'Đầu nối one-touch (KQ2)', code: '',
  attrs: {}, children: [], gap_item: 'Đầu nối one-touch (KQ2)',
  gap_fields: ['fitting_points'],
  gap_fields_vn: ['Danh sách điểm nối ống → ren'] };
check('node thiếu dữ liệu có trạng thái riêng (gap), không lẫn với "trống"',
  S.statusOf(GAPN) === 'gap', S.statusOf(GAPN));
check('trống thật vẫn là empty', S.statusOf({ code: '', attrs: {} }) === 'empty');
check('có mã rồi thì hết gap dù dấu cũ còn dính',
  S.statusOf({ ...GAPN, code: 'KQ2L06-02NS' }) === 'specified');
check('nói ra ĐANG THIẾU GÌ, bằng tiếng Việt',
  S.gapWhy(GAPN) === 'Danh sách điểm nối ống → ren', S.gapWhy(GAPN));
check('không có bản dịch thì in khoá kỹ thuật, không in rỗng',
  S.gapWhy({ gap_fields: ['tube_total_m'] }) === 'tube_total_m');
// Hộp phải đủ rộng cho dòng 'CHƯA CÓ MÃ — cần …', nếu không chữ bị cắt.
check('bề rộng hộp tính theo dòng ĐANG HIỆN, không theo mã',
  S.boxW(GAPN) > S.boxW({ ...GAPN, gap_fields: [], gap_fields_vn: [] }),
  `${S.boxW(GAPN)} vs ${S.boxW({ ...GAPN, gap_fields: [], gap_fields_vn: [] })}`);
check('sơ đồ tô node chưa có mã bằng màu --gap, cùng màu với dòng BOM',
  /st===.gap.\?.var\(--gap\)./.test(html));
// Dòng chưa có mã có part_number=null → khoá theo mã sẽ in HAI LẦN (một ở khối cây,
// một ở khối 'dùng chung cả máy'). Khoá chung chặn đúng lỗi đó.
check('BOM khớp dòng-với-node bằng khoá chung, không bằng part_number',
  /const keyOf=/.test(html) && /inTree\.has\(keyOf\(l\)\)/.test(html));

// ── giao diện: các tab không đè nhau ────────────────────────────────────────
console.log('\ntab_khong_de_nhau');
const views = [...html.matchAll(/id="v-(\w+)"/g)].map(m => m[1]);
check('có đủ 4 tab: cây · cấu hình · BOM · sơ đồ',
  ['tree', 'cfg', 'bom', 'diagram'].every(v => views.includes(v)), JSON.stringify(views));
const viewCss = html.match(/\.view\{[^}]*\}/);
check('.view mặc định display:none — chỉ tab active hiện, không đè nhau',
  !!viewCss && /display:none/.test(viewCss[0]), viewCss ? viewCss[0] : '');
check('.view.active mới hiện', /\.view\.active\{[^}]*display:block/.test(html));
check('mỗi vùng cuộn riêng (overflow:auto) — không tràn ra ngoài',
  /\.view\{[^}]*overflow:auto/.test(html));
check('cột cây có chiều rộng cố định và tự cuộn',
  /\.treepanel\{[^}]*width:330px/.test(html) && /\.tscroll\{[^}]*overflow-y:auto/.test(html));

console.log('\n' + '='.repeat(58));
console.log(`${ok} đạt · ${fail} lỗi`);
process.exit(fail ? 1 : 0);
