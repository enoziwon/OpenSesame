// 포스터 8번 칸 시안을 PNG·PDF·SVG(Figma 가져오기용)로 만든다.
//   node build.cjs <playwright 모듈 폴더> <section08.html> <출력 폴더>
// - 글꼴은 Google Fonts의 Noto Sans KR(재원 님 초안과 같은 글꼴)이라 인터넷이 필요하다.
// - SVG는 글자를 윤곽선이 아닌 글자(<text>)로 남긴다. 줄마다 글자 한 덩어리라 Figma에서 고칠 수 있다.
// - 마지막에 SVG를 다시 그려 PNG와 같은지 견준 그림(_svg확인.png)을 남긴다.
const path = require("path");
const fs = require("fs");

const [pwDir, htmlPath, outDir] = process.argv.slice(2);
if (!pwDir || !htmlPath || !outDir) {
  console.error("사용: node build.cjs <playwright 모듈 폴더> <section08.html> <출력 폴더>");
  process.exit(2);
}
const { chromium } = require(pwDir);
const FONT_LINK = '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=block" rel="stylesheet">';
const NAME = "08_효과및개선";

// 브라우저 안에서 돈다: #card를 SVG 글자로 옮긴다
function exportSVG() {
  const root = document.getElementById("card");
  const R = root.getBoundingClientRect();
  const ox = R.left, oy = R.top;
  const f = (n) => Math.round(n * 100) / 100;
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const toHex = (c) => {
    const m = /rgba?\(([^)]+)\)/.exec(c);
    if (!m) return null;
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    if (p.length > 3 && p[3] === 0) return null;
    return "#" + p.slice(0, 3).map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase();
  };

  // 1) 상자: 배경색이나 테두리가 있는 요소
  const shapes = [];
  for (const el of [root, ...root.querySelectorAll("*")]) {
    const cs = getComputedStyle(el);
    const fill = toHex(cs.backgroundColor);
    const bw = parseFloat(cs.borderTopWidth) || 0;
    const stroke = bw > 0 && cs.borderTopStyle !== "none" ? toHex(cs.borderTopColor) : null;
    if (!fill && !stroke) continue;
    const rects = cs.display === "inline" ? [...el.getClientRects()] : [el.getBoundingClientRect()];
    for (const r of rects) {
      if (r.width < 0.5 || r.height < 0.5) continue;
      const rad = Math.min(parseFloat(cs.borderTopLeftRadius) || 0, r.height / 2, r.width / 2);
      const inset = stroke ? bw / 2 : 0;   // CSS 테두리는 상자 안쪽, SVG 선은 가운데에 그려진다
      shapes.push(`<rect x="${f(r.left - ox + inset)}" y="${f(r.top - oy + inset)}" width="${f(r.width - 2 * inset)}" ` +
        `height="${f(r.height - 2 * inset)}" rx="${f(Math.max(0, rad - inset))}" fill="${fill || "none"}"` +
        (stroke ? ` stroke="${stroke}" stroke-width="${f(bw)}"` : "") + "/>");
    }
  }

  // 2) 기준선 위치: 글자 상자 위에서 기준선까지의 비율 (Noto Sans KR은 굵기와 관계없이 같다)
  const probe = document.createElement("div");
  probe.style.cssText = 'position:absolute;left:-9999px;top:0;font-family:"Noto Sans KR";font-size:100px';
  probe.innerHTML = '가<span style="display:inline-block;width:0;height:0;vertical-align:baseline"></span>';
  document.body.appendChild(probe);
  const pr = document.createRange();
  pr.setStart(probe.firstChild, 0);
  pr.setEnd(probe.firstChild, 1);
  const cr = pr.getClientRects()[0];
  const ratio = (probe.lastChild.getBoundingClientRect().top - cr.top) / cr.height;
  probe.remove();

  // 3) 글자 하나하나의 위치를 읽고, 같은 줄끼리 묶는다
  const blockOf = (n) => {
    let e = n.parentElement;
    while (e && getComputedStyle(e).display === "inline") e = e.parentElement;
    return e;
  };
  const chars = [];
  const range = document.createRange();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const cs = getComputedStyle(node.parentElement);
    const style = { size: parseFloat(cs.fontSize), weight: cs.fontWeight, fill: toHex(cs.color) };
    const block = blockOf(node);
    const t = node.textContent;
    for (let i = 0; i < t.length; i++) {
      range.setStart(node, i);
      range.setEnd(node, i + 1);
      const rs = range.getClientRects();
      if (!rs.length || rs[0].width < 0.01) continue;      // 접힌 공백
      const r = rs[0];
      chars.push({ ch: /\s/.test(t[i]) ? " " : t[i], l: r.left - ox, r: r.right - ox,
                   base: r.top - oy + ratio * r.height, style, block });
    }
  }
  const lines = [];
  let cur = null;
  for (const c of chars) {
    if (!cur || c.block !== cur.block || Math.abs(c.base - cur.base) > 2 || c.l < cur.last.r - 2) {
      cur = { block: c.block, base: c.base, chars: [], last: null };
      lines.push(cur);
    }
    cur.chars.push(c);
    cur.last = c;
  }
  const texts = [];
  for (const L of lines) {
    while (L.chars.length && L.chars[0].ch === " ") L.chars.shift();
    while (L.chars.length && L.chars[L.chars.length - 1].ch === " ") L.chars.pop();
    if (!L.chars.length) continue;
    const runs = [];
    let run = null, prev = null;
    for (const c of L.chars) {
      const key = `${c.style.size}|${c.style.weight}|${c.style.fill}`;
      const gap = prev ? c.l - prev.r : 0;
      if (!run || run.key !== key || gap > 1.5) {   // 굵기·색이 바뀌거나 여백(padding)이 끼면 새 조각
        // 위치는 줄 처음과 여백 뒤에만 고정한다. 나머지는 앞 조각에 이어 흐르게 해서 틈이 생기지 않게 한다
        run = { key, style: c.style, x: !prev || gap > 1.5 ? c.l : null, text: "" };
        runs.push(run);
      }
      run.text += c.ch;
      prev = c;
    }
    const spans = runs.map((r) => `<tspan${r.x === null ? "" : ` x="${f(r.x)}"`} font-size="${r.style.size}" ` +
      `font-weight="${r.style.weight}" fill="${r.style.fill}">${esc(r.text)}</tspan>`).join("");
    texts.push(`<text xml:space="preserve" font-family="Noto Sans KR" y="${f(L.chars[0].base)}">${spans}</text>`);
  }
  const W = f(R.width), H = f(R.height);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">\n` +
    `<g id="boxes">\n${shapes.join("\n")}\n</g>\n<g id="text">\n${texts.join("\n")}\n</g>\n</svg>\n`;
}

async function fontsReady(page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  const ok = await page.evaluate(() => ["400", "500", "700"].every((w) => document.fonts.check(`${w} 20px "Noto Sans KR"`)));
  if (!ok) throw new Error("Noto Sans KR을 불러오지 못했다. 인터넷 연결을 확인할 것");
}

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 2500, height: 1600 }, deviceScaleFactor: 1 });
    await page.goto("file://" + path.resolve(htmlPath));
    await fontsReady(page);
    const card = await page.$("#card");
    const box = await card.boundingBox();
    const png = path.join(outDir, `${NAME}_시안.png`);
    await card.screenshot({ path: png });

    const svg = await page.evaluate(exportSVG);
    const svgPath = path.join(outDir, `${NAME}_figma.svg`);
    fs.writeFileSync(svgPath, svg, "utf8");

    const W = Math.ceil(box.width), H = Math.ceil(box.height);
    await page.setViewportSize({ width: W, height: H });
    await page.pdf({ path: path.join(outDir, `${NAME}_시안.pdf`), width: `${W}px`, height: `${H}px`, printBackground: true });

    // SVG를 같은 글꼴로 다시 그려 견줄 그림을 남긴다
    const check = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    await check.setContent(`<!doctype html><html><head><meta charset="utf-8">${FONT_LINK}</head>` +
      `<body style="margin:0;background:#FFFCF8">${svg}</body></html>`);
    await fontsReady(check);
    await (await check.$("svg")).screenshot({ path: path.join(path.dirname(path.resolve(htmlPath)), "_svg확인.png") });
    console.log(`크기 ${W}x${H}px, 글자 줄 ${(svg.match(/<text /g) || []).length}개, 상자 ${(svg.match(/<rect /g) || []).length}개`);
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error("실패:", e.message);
  process.exit(1);
});
