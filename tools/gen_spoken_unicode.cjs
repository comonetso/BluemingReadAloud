// spoken_unicode.py 를 만든다 — spoken_text.py(Paseo 상태바 플러그인 spokenText.ts 이식)가 쓰는 유니코드 분류 구간표.
// 파이썬 표준 re 에는 \p{...} 가 없어서, 기준과 같은 결과가 나오게 node 의 정규식으로 구간을 뽑아 둔다(2026-10-28).
// 실행: node tools/gen_spoken_unicode.cjs > spoken_unicode.py
const PROPS = [
  ["L", /\p{L}/u, "\\p{L} 문자"],
  ["N", /\p{N}/u, "\\p{N} 숫자"],
  ["M", /\p{M}/u, "\\p{M} 결합 문자"],
  ["HANGUL", /\p{Script=Hangul}/u, "\\p{Script=Hangul} 한글"],
  ["PICTO", /\p{Extended_Pictographic}/u, "\\p{Extended_Pictographic} 그림 문자"],
];

function esc(cp) {
  return cp <= 0xffff ? "\\u" + cp.toString(16).padStart(4, "0") : "\\U" + cp.toString(16).padStart(8, "0");
}

function ranges(re) {
  const out = [];
  let start = -1;
  for (let cp = 0; cp <= 0x110000; cp++) {
    const hit = cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff) && re.test(String.fromCodePoint(cp));
    if (hit && start < 0) start = cp;
    if (!hit && start >= 0) {
      out.push(start === cp - 1 ? esc(start) : esc(start) + "-" + esc(cp - 1));
      start = -1;
    }
  }
  return out;
}

const lines = [
  "# -*- coding: utf-8 -*-",
  `# 자동 생성 — node tools/gen_spoken_unicode.cjs > spoken_unicode.py (node ${process.version}, Unicode ${process.versions.unicode}).`,
  "# 손으로 고치지 말 것. 값은 정규식 문자 클래스 [...] 안에 넣는 글(대괄호 없음, \\u·\\U 이스케이프는 re 가 푼다).",
  "",
];
for (const [name, re, label] of PROPS) {
  const parts = ranges(re);
  lines.push(`# ${label} — 구간 ${parts.length}개`);
  lines.push(`${name} = (`);
  for (let i = 0; i < parts.length; i += 8) lines.push(`    r"${parts.slice(i, i + 8).join("")}"`);
  lines.push(")");
  lines.push("");
}
process.stdout.write(lines.join("\n"));
