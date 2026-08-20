/* Test phần LOGIC THUẦN của canvas trong web/index.html — chạy bằng node.
 *
 *   node tests/test_ui.js
 *
 * VÌ SAO CÓ TỆP NÀY: tôi không click được trong môi trường này, nên không thể
 * "thử là biết". Nhưng phần lớn lỗi của một node-graph editor nằm ở HÌNH HỌC
 * (cổng trùng vị trí, A/B ra cùng toạ độ → vẽ dây sai chỗ) và ở PARSER nhập
 * nhanh — hai thứ đó test được mà không cần DOM.
 *
 * KHÔNG thay thế việc mở trình duyệt kiểm tay: kéo-thả, zoom, bấm-bấm nối dây
 * vẫn phải người thật thử. Tệp này chỉ chặn lớp lỗi tính toán.
 */
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];

// Cắt lấy các hàm thuần, bỏ phần cần DOM. Chạy trong sandbox có stub tối thiểu.
const stub = `
  const stubEl = () => {
    const e = { style:{}, dataset:{}, value:'', checked:false, textContent:'',
      innerHTML:'', title:'', placeholder:'', type:'', draggable:false,
      classList:{add(){},remove(){},toggle(){},contains(){return false}},
      appendChild(){return e}, remove(){}, addEventListener(){}, setAttribute(){},
      closest(){return null}, getBoundingClientRect(){return {left:0,top:0,width:900,height:600}},
      querySelector(){return stubEl()}, querySelectorAll(){return []},
      onclick:null, onchange:null };
    return e;
  };
  const document = { querySelector: stubEl, querySelectorAll: () => [],
    createElement: stubEl, createElementNS: stubEl,
    body: stubEl(), elementFromPoint: () => null };
  const addEventListener = () => {};
  const fetch = async () => ({ json: async () => ({}) });
  const innerWidth = 1200, innerHeight = 800;
  const setTimeout = () => {};
  const Option = function(a,b){ return {text:a,value:b}; };
`;
// boot() gọi fetch nên bỏ dòng cuối; giữ nguyên phần còn lại.
const body = js.replace(/^boot\(\);\s*$/m, '');

let ok = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { ok++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + '   ' + detail); }
};

let S;
try {
  S = new Function(stub + body + `
    return {sides, nodeH, portPos, NW, HEAD, BODY};`)();
} catch (e) {
  console.log('  ✗ không nạp được JS: ' + e.message);
  process.exit(1);
}

// ── hình học cổng ───────────────────────────────────────────────────────────
console.log('\nhinh_hoc_cong');
const cyl = { id: 'c', position: { x: 100, y: 50 }, ports: [
  { id: 'A', kind: 'pneumatic', direction: 'bidirectional' },
  { id: 'B', kind: 'pneumatic', direction: 'bidirectional' },
  { id: 'rod_end', kind: 'mechanical', direction: 'bidirectional' }] };
const valve = { id: 'v', position: { x: 0, y: 0 }, ports: [
  { id: '1', kind: 'pneumatic', direction: 'in' },
  { id: '2', kind: 'pneumatic', direction: 'out' },
  { id: '4', kind: 'pneumatic', direction: 'out' },
  { id: '12', kind: 'electrical', direction: 'in' },
  { id: '14', kind: 'electrical', direction: 'in' }] };

const pa = S.portPos(cyl, 'A'), pb = S.portPos(cyl, 'B');
check('cổng A và B KHÔNG trùng toạ độ',
  pa.x !== pb.x || pa.y !== pb.y, JSON.stringify([pa, pb]));

// mọi cổng của cùng một node phải ra vị trí khác nhau — trùng là vẽ dây sai chỗ
for (const n of [cyl, valve]) {
  const seen = new Set(), dup = [];
  n.ports.forEach(p => { const k = JSON.stringify(S.portPos(n, p.id));
    if (seen.has(k)) dup.push(p.id); seen.add(k); });
  check(`node ${n.id}: ${n.ports.length} cổng ra ${seen.size} vị trí khác nhau`,
    dup.length === 0, 'trùng: ' + dup.join(','));
}

// cổng 'in' bên trái, 'out' bên phải → dây chảy trái sang phải
const p1 = S.portPos(valve, '1'), p2 = S.portPos(valve, '2');
check('cổng vào ở mép trái node', p1.x === valve.position.x, JSON.stringify(p1));
check('cổng ra ở mép phải node', p2.x === valve.position.x + S.NW, JSON.stringify(p2));

// cổng điện xuống đáy, không lẫn với cổng khí hai bên
const e12 = S.portPos(valve, '12');
check('cổng điện nằm ở đáy node',
  Math.abs(e12.y - (valve.position.y + S.nodeH(valve))) < 0.01, JSON.stringify(e12));
check('cổng điện không nằm trên mép trái/phải',
  e12.x !== valve.position.x && e12.x !== valve.position.x + S.NW, JSON.stringify(e12));

// chiều cao node phải đủ chứa hàng cổng nhiều nhất
const {L, R, B} = S.sides(valve);
check('phân cổng: 1 vào trái · 2 ra phải · 2 điện đáy',
  L.length === 1 && R.length === 2 && B.length === 2, `${L.length}/${R.length}/${B.length}`);
check('node cao đủ chứa hàng cổng nhiều nhất',
  S.nodeH(valve) >= S.HEAD + S.BODY + Math.max(L.length, R.length) * 18,
  String(S.nodeH(valve)));

// cổng không xác định không được làm vỡ (trả tâm node)
const un = S.portPos(cyl, 'khong-ton-tai');
check('cổng không tồn tại → trả tâm node, không NaN',
  Number.isFinite(un.x) && Number.isFinite(un.y), JSON.stringify(un));

// node rỗng (chưa có cổng nào) vẫn phải có chiều cao dương
check('node chưa có cổng vẫn cao > 0',
  S.nodeH({ id: 'x', position: { x: 0, y: 0 }, ports: [] }) > 0);

// ── parser nhập nhanh ───────────────────────────────────────────────────────
console.log('\nparser_nhap_nhanh');
// cùng biểu thức dùng trong $('#pastego').onclick
const parse = l => { const m = l.match(/^(\S+)\s*[x×]\s*(\d+)$/i);
  return m ? { code: m[1], q: +m[2] } : { code: l, q: 1 }; };
const cases = [
  ['CDM2L32-500Z', 'CDM2L32-500Z', 1],
  ['MGPM25-200Z-M9BL x4', 'MGPM25-200Z-M9BL', 4],
  ['CDQSB20-25D-M9BZ ×12', 'CDQSB20-25D-M9BZ', 12],
  ['CDM2L32-500Z X3', 'CDM2L32-500Z', 3],
];
cases.forEach(([inp, code, q]) => {
  const r = parse(inp);
  check(`"${inp}" → ${code} ×${q}`, r.code === code && r.q === q, JSON.stringify(r));
});
// mã có chữ x bên trong KHÔNG được hiểu là số lượng
const tricky = parse('SY5120-5MZE-C6');
check('mã chứa dấu gạch không bị cắt sai', tricky.code === 'SY5120-5MZE-C6' && tricky.q === 1,
  JSON.stringify(tricky));

console.log('\n' + '='.repeat(56));
console.log(`${ok} đạt · ${fail} lỗi`);
process.exit(fail ? 1 : 0);
