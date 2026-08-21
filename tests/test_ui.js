/* Test phần LOGIC THUẦN của canvas trong web/index.html — chạy bằng node.
 *
 *   node tests/test_ui.js
 *
 * VÌ SAO CÓ TỆP NÀY: tôi không click được trong môi trường này. Nhưng phần lớn
 * lỗi của node-graph editor nằm ở HÌNH HỌC và ĐỊNH TUYẾN — test được không cần DOM.
 *
 * BÀI HỌC ĐÃ TRẢ GIÁ: bản trước test `portPos()` và nó xanh, nhưng UI vẫn sai —
 * lỗi nằm ở CSS: `.pts` là position:relative đặt sau header trong luồng, nên chấm
 * cổng bị đẩy xuống ~70px so với chỗ dây neo. Test chỉ kiểm MỘT PHÍA của hợp đồng.
 * Nay có thêm test đọc CSS để chặn đúng lớp lỗi đó.
 *
 * KHÔNG thay thế mở trình duyệt: kéo-thả, zoom, bấm-bấm nối dây vẫn phải người thử.
 */
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const js = html.match(/<script>([\s\S]*)<\/script>/)[1];

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
const body = js.replace(/^boot\(\);\s*$/m, '');

let ok = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { ok++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + '   ' + detail); }
};

let S;
try {
  S = new Function(stub + body + `
    return {layout, nodeH, portPos, hasPorts, orthPath, portSide,
            NW, HEAD, BODY, SP, EROW,
            setNodes: ns => { NODES = ns; }};`)();
} catch (e) {
  console.log('  ✗ không nạp được JS: ' + e.message);
  process.exit(1);
}

const okParse = { ok: true, attrs: {} };
const valve = { id: 'v', position: { x: 0, y: 0 }, parsed: okParse, ports: [
  { id: '2', kind: 'pneumatic', direction: 'out', side: 't', label: '2 / A' },
  { id: '4', kind: 'pneumatic', direction: 'out', side: 't', label: '4 / B' },
  { id: '3', kind: 'pneumatic', direction: 'out', side: 'b', label: '3 / R' },
  { id: '1', kind: 'pneumatic', direction: 'in',  side: 'b', label: '1 / P' },
  { id: '5', kind: 'pneumatic', direction: 'out', side: 'b', label: '5 / S' },
  { id: '12', kind: 'electrical', direction: 'in', side: 'e' },
  { id: '14', kind: 'electrical', direction: 'in', side: 'e' }] };
const cyl = { id: 'c', position: { x: 420, y: 260 }, parsed: okParse, ports: [
  { id: 'A', kind: 'pneumatic', direction: 'bidirectional', side: 'l' },
  { id: 'B', kind: 'pneumatic', direction: 'bidirectional', side: 'r' },
  { id: 'rod_end', kind: 'mechanical', direction: 'bidirectional', side: 't' }] };
const blank = { id: 'x', position: { x: 0, y: 0 }, parsed: null, ports: [] };
S.setNodes([valve, cyl, blank]);

// ── MỤC 2: cổng chỉ hiện khi mã hàng hợp lệ ─────────────────────────────────
console.log('\nmuc2_cong_chi_hien_khi_ma_hop_le');
check('chưa có mã → KHÔNG hiện cổng',
  S.hasPorts({ parsed: null, ports: [{ id: 'A' }] }) === false);
check('mã sai → KHÔNG hiện cổng',
  S.hasPorts({ parsed: { ok: false }, ports: [{ id: 'A' }] }) === false);
check('mã hợp lệ → hiện cổng', S.hasPorts({ parsed: okParse }) === true);
check('node "mã tự do" vẫn hiện cổng (để nối được vào sơ đồ)',
  S.hasPorts({ manual: true, parsed: null }) === true);
const lb = S.layout({ parsed: null, ports: valve.ports });
check('node chưa có mã: layout trả 0 cổng ở mọi cạnh',
  [lb.L, lb.R, lb.T, lb.B, lb.E].every(a => a.length === 0));

// ── MỤC 3: bố trí theo chuẩn catalog ────────────────────────────────────────
console.log('\nmuc3_bo_tri_theo_catalog');
const lv = S.layout(valve);
check('van: 2/A và 4/B ở cạnh TRÊN',
  lv.T.map(p => p.id).join(',') === '2,4', JSON.stringify(lv.T.map(p => p.id)));
check('van: 3/R · 1/P · 5/S ở cạnh DƯỚI',
  lv.B.map(p => p.id).join(',') === '3,1,5', JSON.stringify(lv.B.map(p => p.id)));
check('van: coil 12/14 ở hàng ĐIỆN tách riêng',
  lv.E.map(p => p.id).join(',') === '12,14');
check('van: không có cổng khí lẫn sang hai bên',
  lv.L.length === 0 && lv.R.length === 0);

const bp = S.portPos(valve, '1'), rp = S.portPos(valve, '3'), sp = S.portPos(valve, '5');
check('1/P nằm GIỮA hàng dưới, R và S hai bên',
  Math.abs(bp.x - S.NW / 2) < 0.01 && rp.x < bp.x && sp.x > bp.x,
  JSON.stringify([rp.x, bp.x, sp.x]));
check('3 cổng hàng dưới cách đều nhau',
  Math.abs((bp.x - rp.x) - (sp.x - bp.x)) < 0.01);
check('hàng điện thấp hơn hàng khí dưới',
  S.portPos(valve, '12').y > bp.y);
check('xy-lanh: cửa A bên trái, B bên phải (dòng khí trái→phải)',
  S.portPos(cyl, 'A').x === cyl.position.x &&
  S.portPos(cyl, 'B').x === cyl.position.x + S.NW);

for (const n of [valve, cyl]) {
  const seen = new Set(), dup = [];
  n.ports.forEach(p => { const k = JSON.stringify(S.portPos(n, p.id));
    if (seen.has(k)) dup.push(p.id); seen.add(k); });
  check(`node ${n.id}: ${n.ports.length} cổng ra ${seen.size} vị trí khác nhau`,
    dup.length === 0, 'trùng: ' + dup.join(','));
}
check('cổng không tồn tại → trả tâm node, không NaN',
  Number.isFinite(S.portPos(cyl, 'khong-co').x));
check('node chưa có cổng vẫn cao > 0', S.nodeH(blank) > 0);

// ── MỤC 1: đường nối vuông góc ──────────────────────────────────────────────
console.log('\nmuc1_duong_noi_vuong_goc');
const d = S.orthPath(valve, '2', cyl, 'A');
check('sinh được path', typeof d === 'string' && d.startsWith('M'), String(d).slice(0, 40));
check('KHÔNG dùng cubic bezier (không có lệnh C)', !/C/.test(d), d);
check('bo góc bằng cung Q ở điểm gấp', /Q/.test(d));

function segments(dd) {
  const toks = dd.match(/[MLQ][^MLQ]*/g) || [];
  let cur = null; const segs = [];
  toks.forEach(t => {
    const nums = t.slice(1).trim().split(/[\s,]+/).map(Number);
    if (t[0] === 'M') cur = { x: nums[0], y: nums[1] };
    else if (t[0] === 'L') { const p = { x: nums[0], y: nums[1] };
      segs.push([cur, p]); cur = p; }
    else if (t[0] === 'Q') cur = { x: nums[2], y: nums[3] };
  });
  return segs;
}
const segs = segments(d);
const bad = segs.filter(([a, b]) =>
  Math.abs(a.x - b.x) > 0.01 && Math.abs(a.y - b.y) > 0.01);
check(`${segs.length} đoạn thẳng, tất cả song song trục (Manhattan)`,
  bad.length === 0, JSON.stringify(bad.slice(0, 2)));

// node di chuyển → path phải đổi theo, không giữ path cũ
const before = S.orthPath(valve, '2', cyl, 'A');
cyl.position = { x: 700, y: 90 };
const after = S.orthPath(valve, '2', cyl, 'A');
check('kéo node → path định tuyến lại (không giữ path cũ)', before !== after);
cyl.position = { x: 420, y: 260 };

// ── MỤC 4: dây neo ĐÚNG TÂM cổng ────────────────────────────────────────────
console.log('\nmuc4_neo_dung_tam_cong');
const dd = S.orthPath(valve, '2', cyl, 'A');
const first = dd.match(/^M([\d.-]+),([\d.-]+)/);
const lastL = [...dd.matchAll(/L([\d.-]+),([\d.-]+)/g)].pop();
const a1 = S.portPos(valve, '2'), p2 = S.portPos(cyl, 'A');
check('điểm đầu path = tâm cổng nguồn',
  Math.abs(+first[1] - a1.x) < 0.01 && Math.abs(+first[2] - a1.y) < 0.01,
  `${first[1]},${first[2]} vs ${a1.x},${a1.y}`);
check('điểm cuối path = tâm cổng đích',
  Math.abs(+lastL[1] - p2.x) < 0.01 && Math.abs(+lastL[2] - p2.y) < 0.01,
  `${lastL[1]},${lastL[2]} vs ${p2.x},${p2.y}`);

// Chặn ĐÚNG lỗi đã mắc: .pts phải absolute inset:0, không thì gốc toạ độ của chấm
// cổng lệch khỏi gốc portPos() và dây lại lệch tâm như cũ.
const css = html.match(/\.node \.pts \{[^}]*\}/);
check('.node .pts là position:absolute (không phải relative)',
  !!css && /position:\s*absolute/.test(css[0]), css ? css[0] : 'không thấy quy tắc');
check('.node .pts dùng inset:0 để trùng gốc với portPos()',
  !!css && /inset:\s*0/.test(css[0]), css ? css[0] : '');
check('hướng thoát cổng lấy theo cạnh nó nằm',
  S.portSide(valve, '2') === 't' && S.portSide(valve, '1') === 'b' &&
  S.portSide(cyl, 'A') === 'l' && S.portSide(cyl, 'B') === 'r');

// ── parser nhập nhanh ───────────────────────────────────────────────────────
console.log('\nparser_nhap_nhanh');
const parse = l => { const m = l.match(/^(\S+)\s*[x×]\s*(\d+)$/i);
  return m ? { code: m[1], q: +m[2] } : { code: l, q: 1 }; };
[['CDM2L32-500Z', 'CDM2L32-500Z', 1],
 ['MGPM25-200Z-M9BL x4', 'MGPM25-200Z-M9BL', 4],
 ['CDQSB20-25D-M9BZ ×12', 'CDQSB20-25D-M9BZ', 12],
 ['SY5120-5MZE-C6', 'SY5120-5MZE-C6', 1],
].forEach(([inp, code, q]) => {
  const r = parse(inp);
  check(`"${inp}" → ${code} ×${q}`, r.code === code && r.q === q, JSON.stringify(r));
});

console.log('\n' + '='.repeat(56));
console.log(`${ok} đạt · ${fail} lỗi`);
process.exit(fail ? 1 : 0);
