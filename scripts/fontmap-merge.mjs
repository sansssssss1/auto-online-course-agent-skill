#!/usr/bin/env node
/**
 * 字体映射自举工具（纯 Node，无依赖）— chaoxing 混淆字体解密用
 * ------------------------------------------------------------------
 * 背景（实测，见 docs/field-notes.md 2026-09-17 条目）：
 *   学习通测验题干/选项用私有字体混淆，**作答前** DOM 是乱码；**提交后**页面明文显示
 *   题干 + 我的答案 + 正确答案。抓住这个"明文通道"即可自举出「混淆字形 → 真实字符」映射，
 *   暖机后读题完全不需要截图（省 vision token），也不需要任何上游字库。
 *
 * 用法：
 *   1) 采集（由监督者在页面内执行，分别存成两个文件）：
 *      - 作答前：`obf.txt`  ← 取 `#frame_content` 内 `.TiMu` 的 innerText（乱码）
 *      - 提交后：`plain.txt` ← 取同一批题目的明文 innerText（提交后页面明文）
 *      两份文件必须**行序、行数一致**（同一批题目按同序提取即可）
 *   2) 合并：`node scripts/fontmap-merge.mjs --obfuscated obf.txt --plain plain.txt`
 *   3) 解码（暖机后）：`node scripts/fontmap-merge.mjs --decode obf.txt`
 *
 * 参数：
 *   --obfuscated <file>   作答前乱码文本
 *   --plain <file>        提交后明文文本
 *   --map <file>          映射表路径（默认 knowledge/cx-font-map.json）
 *   --decode <file>       用现有映射表解码一个乱码文本文件并打印结果
 *   --dry-run             只统计不写盘
 *   --self-test           离线自测（用合成样本验证合并/解码正确性）
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_MAP = path.join(__dirname, '..', 'knowledge', 'cx-font-map.json');

const readLines = (file) =>
  fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n').split('\n');

const loadMap = (file) => {
  if (!fs.existsSync(file)) {
    return {
      $comment: 'chaoxing 混淆字体「字形→真实字符」映射表。key=混淆字形字符，value=真实字符。' +
        '由 scripts/fontmap-merge.mjs 从「作答前乱码 + 提交后明文」自举生成，只追加/投票，不手改。',
      platform: 'chaoxing', fontTag: 'font-cxsecret',
      updatedAt: null, stats: { pairs: 0, lines: 0 },
      entries: {},
    };
  }
  const m = JSON.parse(fs.readFileSync(file, 'utf8'));
  m.entries = m.entries || {};
  return m;
};

/** 合并：逐行、逐字符对齐。仅接受"两侧同长"的行对（其余跳过并计数）。 */
export function mergeMap(obfLines, plainLines, map) {
  const votes = {};           // obfChar -> { plainChar: count }
  const stats = { linePairs: 0, skippedLengthMismatch: 0, candidates: 0 };
  const n = Math.min(obfLines.length, plainLines.length);
  for (let i = 0; i < n; i++) {
    const a = obfLines[i], b = plainLines[i];
    if (!a || !b) continue;
    if (a.length !== b.length) { stats.skippedLengthMismatch++; continue; }
    stats.linePairs++;
    for (let k = 0; k < a.length; k++) {
      const from = a[k], to = b[k];
      if (from === to) continue;
      if (!from.trim() || !to.trim()) continue;      // 空白不建映射
      if (to === '\uFFFD') continue;                  // 替换符不建映射
      stats.candidates++;
      votes[from] = votes[from] || {};
      votes[from][to] = (votes[from][to] || 0) + 1;
    }
  }
  const conflicts = [];
  let added = 0, updated = 0;
  for (const [from, cand] of Object.entries(votes)) {
    const ranked = Object.entries(cand).sort((x, y) => y[1] - x[1]);
    const [best, bestCount] = ranked[0];
    if (ranked.length > 1) {
      conflicts.push({ char: from, picked: best, dropped: ranked.slice(1) });
    }
    const prev = map.entries[from];
    if (prev === undefined) { map.entries[from] = best; added++; }
    else if (prev !== best) {
      // 已有映射与本次最高票冲突：保留已有，仅记录（人工可见）
      conflicts.push({ char: from, kept: prev, ignored: best, votes: bestCount });
    } else updated++;
  }
  map.updatedAt = new Date().toISOString();
  map.stats = {
    lines: (map.stats && map.stats.lines ? map.stats.lines : 0) + stats.linePairs,
    pairs: Object.keys(map.entries).length,
  };
  return { map, stats, conflicts, added, updated };
}

/** 用映射表解码乱码文本（映射表未覆盖的字符原样保留） */
export function decode(text, map) {
  let out = '', hit = 0, total = 0;
  for (const ch of text) {
    if (map.entries[ch]) { out += map.entries[ch]; hit++; }
    else { out += ch; }
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch) || /[\uE000-\uF8FF]/.test(ch)) total++;
  }
  return { out, hit, total };
}

function selfTest() {
  const fails = [];
  const assert = (cond, msg) => { if (!cond) fails.push(msg); };

  // 合成样本：把真实文本的每个汉字换成 PUA 字形码位（模拟混淆字体）
  const plain = '通过闭合面的电通量仅由面内电荷决定\n半圆环圆心电势与电场力做功';
  const glyph = {};
  let pua = 0xE000;
  const obf = Array.from(plain).map(ch => {
    if (/[\u4e00-\u9fff]/.test(ch)) {
      if (!glyph[ch]) glyph[ch] = String.fromCharCode(pua++);
      return glyph[ch];
    }
    return ch;
  }).join('');

  const map = loadMap(path.join(__dirname, 'no-such-map.json'));
  const r1 = mergeMap(obf.split('\n'), plain.split('\n'), map);
  const uniqPlainChars = new Set(Array.from(plain).filter(c => /[\u4e00-\u9fff]/.test(c))).size;
  assert(Object.keys(r1.map.entries).length === uniqPlainChars,
    `合并条目数应为 ${uniqPlainChars}，实际 ${Object.keys(r1.map.entries).length}`);
  for (const [from, to] of Object.entries(r1.map.entries)) {
    assert(glyph[to] === from, `映射错误：${JSON.stringify(from)} → ${JSON.stringify(to)}`);
  }

  // 二次合并应为幂等（无新增）
  const r2 = mergeMap(obf.split('\n'), plain.split('\n'), r1.map);
  assert(r2.added === 0, `幂等性：二次合并不应新增，实际新增 ${r2.added}`);

  // 解码应完全还原
  const d = decode(obf, r1.map);
  assert(d.out === plain, `解码还原失败：\n期望 ${JSON.stringify(plain)}\n实际 ${JSON.stringify(d.out)}`);
  // hit/total 统计的是「字形出现次数」（非唯一字符数）：解码后应 100% 命中
  assert(d.hit === d.total && d.hit > 0,
    `解码应全部命中：hit=${d.hit} total=${d.total}`);

  // 长度不一致的行应被跳过而不是错配
  const r3 = mergeMap(['\uE000\uE001\uE002'], ['短'], loadMap(path.join(__dirname, 'no-such-map.json')));
  assert(Object.keys(r3.map.entries).length === 0 && r3.stats.skippedLengthMismatch === 1,
    '长度不一致的行必须跳过');

  if (fails.length) {
    console.error('SELF-TEST FAILED:\n - ' + fails.join('\n - '));
    process.exit(1);
  }
  console.log('SELF-TEST OK（合并 / 幂等 / 解码还原 / 错配防护 全部通过）');
}

function main() {
  const argv = process.argv.slice(2);
  const get = (k) => { const i = argv.indexOf(k); return i > -1 ? argv[i + 1] : null; };

  if (argv.includes('--self-test')) return selfTest();

  const mapFile = get('--map') || DEFAULT_MAP;
  const decodeFile = get('--decode');
  if (decodeFile) {
    const map = loadMap(mapFile);
    const { out, hit, total } = decode(fs.readFileSync(decodeFile, 'utf8'), map);
    console.log(out);
    console.error(`[decode] 命中 ${hit}/${total} 个汉字字形（未命中保留原字符）`);
    return;
  }

  const obfFile = get('--obfuscated'), plainFile = get('--plain');
  if (!obfFile || !plainFile) {
    console.error('用法：node scripts/fontmap-merge.mjs --obfuscated obf.txt --plain plain.txt [--map <file>] [--dry-run]\n' +
      '      node scripts/fontmap-merge.mjs --decode obf.txt\n' +
      '      node scripts/fontmap-merge.mjs --self-test');
    process.exit(2);
  }
  const map = loadMap(mapFile);
  const before = Object.keys(map.entries).length;
  const r = mergeMap(readLines(obfFile), readLines(plainFile), map);
  const after = Object.keys(r.map.entries).length;

  console.log(`[merge] 行对 ${r.stats.linePairs}（长度不一致跳过 ${r.stats.skippedLengthMismatch}）`);
  console.log(`[merge] 候选 ${r.stats.candidates}；新增 ${r.added}，已存在 ${r.updated}；映射总数 ${before} → ${after}`);
  if (r.conflicts.length) {
    console.log(`[merge] 冲突 ${r.conflicts.length} 条（已保留旧值，供人工复核）：`);
    for (const c of r.conflicts.slice(0, 10)) console.log('  ' + JSON.stringify(c));
  }
  if (argv.includes('--dry-run')) { console.log('[merge] dry-run，未写盘'); return; }
  fs.mkdirSync(path.dirname(mapFile), { recursive: true });
  fs.writeFileSync(mapFile, JSON.stringify(r.map, null, 2) + '\n');
  console.log(`[merge] 已写入 ${mapFile}`);
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1].endsWith('fontmap-merge.mjs')) main();
