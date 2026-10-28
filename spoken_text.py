# -*- coding: utf-8 -*-
"""소리로 읽을 글 다듬기 — Paseo 상태바 플러그인의 규칙을 그대로 옮긴 것 (2026-10-28 리규형님 지시).

기준: F:\\workspace\\EtcProject\\VsCodeExtentions\\claudeContextBar\\paseo-plugins\\claude-state-bar
      server/presentation/spokenText.ts (입구 makeSpokenText(text, lang)).
      소리 읽기를 쓰는 세 곳(Paseo 상태바 플러그인 · 이 앱 · 크롬 확장 read-aloud-hrg)이 같은 글을 같게 읽도록,
      기준 쪽이 바뀌면 여기도 같이 바꾼다. 시험 기대값도 기준 시험을 그대로 옮겼다(tests/test_spoken_text.py).
      예전 규칙(readaloud_text.make_spoken_text — 크롬 확장 spoken-text.js 이식: "쩜"·"슬래시"로 읽기, 영어 단어 목록)은
      더 이상 읽기에 쓰지 않는다.

하는 일(차례대로)
  1. 코드 울타리 줄·마크다운 그림/링크(글만)·URL("URL")
  2. 표 → 줄마다 "첫 칸, 머리글 값, …." 문장(table_to_sentences)
  3. 괄호 — 한글이 든 괄호는 안을 읽고, 파일명·경로가 들었거나 한글이 없는 괄호는 건너뛴다(drop_parens)
  4. 경로 → 끝 이름(shorten_paths)
  5. 한국어 음성만: 날짜·시각·판 번호·수식·단위·천 단위 숫자를 한국어 말로(read_numbers_ko)
  6. 마크다운 표시·기호를 지우거나 쉼표(잠깐 쉼)로, 영어 이름 안 기호는 띄움

JS 와 뜻을 맞춘 곳
  - JS 의 \\w·\\d 는 ASCII 뿐이다 → [A-Za-z0-9_]·[0-9]. JS \\s 는 readaloud_text 의 _WS 와 같은 공백(WS).
  - \\p{L}·\\p{N}·\\p{M}·\\p{Script=Hangul}·\\p{Extended_Pictographic} 은 node 로 뽑은 구간표(spoken_unicode.py).
  - JS 의 $(m 없음)는 글 끝 → \\Z. JS Math.round 는 .5 를 올림 → _js_round.
  - JS charAt 은 UTF-16 한 칸이라 보조 평면 글자 뒤의 판정이 아주 드물게 다를 수 있다(괄호 뒤 글자가 이모지·한자 확장일 때).
"""

import math
import re

import spoken_unicode as _U

__all__ = [
    "PAUSE", "make_spoken_text", "table_to_sentences", "keep_paren_content", "drop_parens", "shorten_paths",
    "korean_number", "read_numbers_ko", "speech_lang", "mask_urls",
]

REPEATED_CHARS_MAX = 3
PAUSE = ", "

# JS \s (readaloud_text._WS 와 같은 값 — 순환 import 를 피해 여기에 둔다)
WS = r"\t\n\x0b\x0c\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_S = "[" + WS + "]"
_W = "A-Za-z0-9_"            # JS \w
_LN = _U.L + _U.N            # \p{L}\p{N}
_HANGUL = re.compile("[" + _U.HANGUL + "]")
_LN_CHAR = re.compile("[" + _LN + "]")


def _js_trim(s):
    return s.strip(" \t\n\x0b\x0c\r\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
                   "\u2028\u2029\u202f\u205f\u3000\ufeff")


def _js_round(x):
    return math.floor(x + 0.5)


def speech_lang(voice_lang):
    """음성 언어("ko-KR") → 기준의 언어 이름("ko"). 기준은 ko·en·ja·zh·es·fr·ar 만 안다(그 밖은 앞 두 글자 그대로)."""
    return (voice_lang or "").lower().split("-")[0] or "ko"


# ── 표 ─────────────────────────────────────────────────────────────────
# 구분줄 — 칸마다 대시 하나 이상, 정렬 표시(:--·:-:·--:) 가능
_TABLE_RULE = re.compile(r"^" + _S + r"*\|?" + _S + r"*:?-+:?" + _S + r"*(?:\|" + _S + r"*:?-+:?" + _S + r"*)*\|?" + _S + r"*\Z")


def _table_cells(line):
    t = re.sub(r"\|\Z", "", re.sub(r"^\|", "", _js_trim(line)))
    return [_js_trim(c) for c in t.split("|")]


def table_to_sentences(text):
    """마크다운 표(머리줄 + 구분줄 + 줄들)를 줄마다 "첫 칸, 머리글 값, 머리글 값." 문장으로. 첫 칸은 머리글 없이 값만, 빈 칸은 뺀다."""
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if "|" not in lines[i] or not _TABLE_RULE.match(nxt):
            out.append(lines[i])
            i += 1
            continue
        head = _table_cells(lines[i])
        sentences = []
        j = i + 2
        while j < len(lines) and "|" in lines[j]:
            parts = []
            for k, cell in enumerate(_table_cells(lines[j])):
                if not cell:
                    continue
                h = head[k] if k < len(head) else ""
                parts.append(cell if k == 0 or not h else f"{h} {cell}")
            if parts:
                sentences.append(PAUSE.join(parts) + ".")
            j += 1
        out.append(" ".join(sentences))
        i = j
    return "\n".join(out)


# ── 괄호 ────────────────────────────────────────────────────────────────
# 파일명 판단 = 확장자 붙은 이름(work-cli.mjs) 또는 구분자가 붙은 경로(docs/x · C:\ · ~/). 영문·숫자 이름만 본다
_FILE_NAME = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z][A-Za-z0-9]{0,5}(?![A-Za-z0-9])|[A-Za-z0-9_.~-]*[\\/][A-Za-z0-9_.-]+|[A-Za-z]:[\\/]")
_PAREN = re.compile(r"\(([^()\n]*)\)|（([^（）\n]*)）")


def keep_paren_content(inner):
    """괄호 안을 읽을지 — 한글이 들었고 파일명·경로가 없을 때만."""
    return bool(_HANGUL.search(inner)) and not _FILE_NAME.search(inner)


def drop_parens(text):
    """읽을 괄호는 기호만 빼고 안을 남기고, 아닌 괄호는 통째로 지운다. 겹친 괄호는 안쪽부터. 짝 없는 괄호는 기호만 지운다.

    통째로 지울 때 뒤가 한글·빈칸·부호·끝이면 빈칸 없이("3대(DB)는" → "3대는"), 뒤가 영어·숫자면 빈칸을 둔다.
    """
    while True:
        prev = text

        def repl(m, all_text=prev):
            inner = m.group(1) if m.group(1) is not None else (m.group(2) or "")
            nxt = all_text[m.end():m.end() + 1]
            space_after = " " if nxt and _LN_CHAR.match(nxt) and not _HANGUL.match(nxt) else ""
            if keep_paren_content(inner):
                return f" {inner}{space_after}"
            return space_after

        text = _PAREN.sub(repl, prev)
        if text == prev:
            break
    return re.sub(r"[()（）]", " ", text)


# ── 경로·URL ────────────────────────────────────────────────────────────
# http 뿐 아니라 ssh://·ws://·file:// 같은 주소 형식 전부 → "URL". JS \b 는 ASCII 단어 경계
_URL = re.compile(r"(?<![" + _W + r"])[a-z][a-z0-9+.-]*://[^" + WS + r"<>()`]+", re.I)
# 시작이 분명한 경로(C:\ · ~/ · ./ · ../ · /root/x)는 길이와 상관없이 끝 이름만. 선행 / 는 뒤에 구분자가 하나 더 있어야 경로
_NAME_CH = "[" + _LN + r"_.@+\-]"
_ANCHORED_PATH = re.compile(
    r"(?<![" + _LN + r"_.~@+\-:/\\])(?:[A-Za-z]:[\\/]|~[\\/]|\.{1,2}[\\/]|[\\/](?=" + _NAME_CH + r"+[\\/]))"
    r"(?:" + _NAME_CH + r"+[\\/])*" + _NAME_CH + "*")
# 상대 경로는 영문 이름만, 끝이 확장자 있는 파일 · 폴더 둘 이상 · 끝이 구분자일 때만 경로로 본다
_RELATIVE_PATH = re.compile(
    r"(?<![" + _W + r".~@+\-:/\\])[" + _W + r".@+-]+(?:[\\/][" + _W + r".@+-]+)+[\\/]?(?![" + _W + r".@+\-\\/])")
_FILE_EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}\Z")


def mask_urls(text):
    """주소(http·ssh·file 등)를 "URL" 로 — 번역할 글을 보내기 전에 쓴다(주소가 번역 회사로 나가지 않게)."""
    return _URL.sub("URL", text)


def _last_name(path):
    parts = [p for p in re.split(r"[\\/]", path)
             if p and p not in ("~", ".", "..") and not re.fullmatch(r"[A-Za-z]:", p)]
    return parts[-1] if parts else None


def _relative(m):
    path = m.group(0)
    parts = [p for p in re.split(r"[\\/]", path) if p]
    name = parts[-1]
    if not re.search(r"[A-Za-z]", name):
        return path
    is_path = len(parts) >= 3 or _FILE_EXTENSION.search(name) or re.search(r"[\\/]\Z", path)
    return name if is_path else path


def shorten_paths(text):
    """경로는 끝 이름(파일명·마지막 폴더)만 남긴다."""
    text = _ANCHORED_PATH.sub(lambda m: _last_name(m.group(0)) or m.group(0), text)
    return _RELATIVE_PATH.sub(_relative, text)


# ── 한국어 숫자 말 ─────────────────────────────────────────────────────
KO_DIGITS = ["영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
KO_SMALL = ["", "십", "백", "천"]
KO_BIG = ["", "만", "억", "조", "경"]


def korean_number(digits):
    """정수(숫자 글자)를 한자어 수사로 — 80055 → 팔만 오십오 · 10000 → 만 · 100000000 → 일억. 경을 넘으면 그대로."""
    n = re.sub(r"^0+(?=[0-9])", "", digits)
    if not re.fullmatch(r"[0-9]+", n):
        return digits
    if re.fullmatch(r"0+", n):
        return "영"
    if len(n) > 20:
        return n
    groups = []
    end = len(n)
    while end > 0:
        groups.insert(0, n[max(0, end - 4):end])
        end -= 4
    words = []
    for gi, group in enumerate(groups):
        big = KO_BIG[len(groups) - 1 - gi]
        padded = group.rjust(4, "0")
        word = ""
        for i in range(4):
            d = int(padded[i])
            if not d:
                continue
            unit = KO_SMALL[3 - i]
            word += ("" if d == 1 and unit else KO_DIGITS[d]) + unit
        if not word:
            continue
        if word == "일" and big == "만":
            word = ""
        words.append(word + big)
    return " ".join(words)


def _korean_fraction(frac):
    return " 점 " + "".join(KO_DIGITS[int(d)] for d in frac)


def _clock_number(digits):
    """시각의 시·분·초 — 시계 숫자 그대로(02 → 공이 · 00 → 공공 · 18 → 십팔)."""
    if len(digits) == 2 and digits[0] == "0":
        return "공" + ("공" if digits[1] == "0" else KO_DIGITS[int(digits[1])])
    return korean_number(digits)


def _valid_month_day(month, day):
    return 1 <= int(month) <= 12 and 1 <= int(day) <= 31


_MATH_NUMBER = r"[0-9]+(?:[.,][0-9]+)*%?"
_MATH_OPERATOR = _S + r"*(?:\*(?!\*)|[-−+×÷±=/])" + _S + "*"
_MATH = re.compile(r"(?<![" + _W + r".,])" + _MATH_NUMBER + r"(?:" + _MATH_OPERATOR + _MATH_NUMBER + r")+(?![" + _W + r"])")
_MATH_OPERATOR_RE = re.compile(_MATH_OPERATOR)

UNIT_WORDS = {
    "ms": "밀리초", "sec": "초", "min": "분", "s": "초", "h": "시간", "px": "픽셀", "fps": "프레임",
    "KiB": "키비바이트", "MiB": "메비바이트", "GiB": "기비바이트", "TiB": "테비바이트", "KB": "킬로바이트", "kB": "킬로바이트",
    "MB": "메가바이트", "GB": "기가바이트", "TB": "테라바이트",
    "kHz": "킬로헤르츠", "MHz": "메가헤르츠", "GHz": "기가헤르츠", "Hz": "헤르츠", "km": "킬로미터", "kg": "킬로그램",
    "°C": "도", "℃": "도",
}
_UNIT_NAMES = "|".join(re.escape(k) for k in sorted(UNIT_WORDS, key=len, reverse=True))
_RANGE_UNIT = "초|분|시간|일|주|개월|달|년|명|개|번|회|배|대|건|줄|쪽|장|마리|권|차|단계|가지|글자|자|살|원|위|곳|층|호|퍼센트|%"

_RE_YEAR_DATE = re.compile(r"(?<![0-9.:/-])([0-9]{4})([-/.])([0-9]{1,2})\2([0-9]{1,2})(?![0-9/-]|[.:][0-9])(T(?=[0-9]{1,2}:[0-9]{2}))?")
_RE_VERSION = re.compile(r"(?<![" + _W + r".])([vV](?=[0-9]))?([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,4})(?![" + _W + r"]|\.[0-9])")
_RE_CLOCK_X = re.compile(r"(?<![0-9.:])([01]?[0-9]|2[0-3]):([0-5])x(?![A-Za-z0-9])")
_RE_CLOCK = re.compile(r"(?<![0-9.:])([01]?[0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]))?(Z(?![A-Za-z0-9]))?(?![0-9:]|\.[0-9])")
_RE_RANGE_UNIT = re.compile(r"(?<![" + _W + r".:/-])([0-9]+(?:\.[0-9]+)?)-([0-9]+(?:\.[0-9]+)?)(?=(?:" + _RANGE_UNIT + r"))")
_RE_HYPHEN_DATE = re.compile(r"(?<![" + _W + r".:/=+×*÷±-])([0-9]{1,2})-([0-9]{1,2})(?![0-9./-]|:[0-9]|" + _S + r"*[=+×*÷±])")
_RE_SLASH_DATE = re.compile(r"(?<![0-9./:-])([0-9]{1,2})/([0-9]{1,2})(?![0-9/]|\.[0-9])")
_RE_SIGN = re.compile(r"(^|[" + WS + r"(（,])([+−-])(?=[0-9])", re.M)
_RE_KILO = re.compile(r"(?<![" + _W + r".,])([0-9]+(?:\.[0-9]+)?)([kKM])(?![A-Za-z0-9])")
_RE_TIMES = re.compile(r"(?<![" + _W + r".,])([0-9]+(?:\.[0-9]+)?)x(?![A-Za-z0-9])")
_RE_UNIT = re.compile(r"(?<![" + _W + r".,])([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:\.[0-9]+)?)" + _S + r"?(" + _UNIT_NAMES + r")(?![A-Za-z0-9])")
_RE_THOUSANDS = re.compile(r"(?<![0-9.,])([0-9]{1,3}(?:,[0-9]{3})+)(?:\.([0-9]+))?(?![0-9,])")
_RE_LEFT_TIMES = re.compile(_S + r"*×" + _S + r"*(?=[0-9])")
_RE_TILDE = re.compile(r"([0-9%가-힣A-Za-z])[ \t]*~[ \t]*(?=[0-9일이삼사오육칠팔구십백천만억조영]|공[공영일이삼사오육칠팔구])")


def _year_date(m):
    year, month, day, iso = m.group(1), m.group(3), m.group(4), m.group(5)
    if not _valid_month_day(month, day):
        return m.group(0)
    return f"{year}년 {int(month)}월 {int(day)}일" + (" " if iso else "")


def _version(m):
    v, a, b, c = m.groups()
    return ("버전 " if v else "") + f"{korean_number(a)} 점 {korean_number(b)} 점 {korean_number(c)}"


def _clock_x(m):
    hour, tens = m.group(1), m.group(2)
    if int(tens):
        return f"{_clock_number(hour)}시 {korean_number(tens + '0')}분쯤"
    return f"{_clock_number(hour)}시쯤"


def _clock(m):
    hour, minute, second, utc = m.groups()
    parts = [f"{_clock_number(hour)}시"]
    if int(minute) or (second and int(second)):
        parts.append(f"{_clock_number(minute)}분")
    if second and int(second):
        parts.append(f"{_clock_number(second)}초")
    if utc:
        parts.append("UTC")
    return " ".join(parts)


def _month_day(m):
    month, day = m.group(1), m.group(2)
    return f"{int(month)}월 {int(day)}일" if _valid_month_day(month, day) else m.group(0)


def _math(m):
    expr = m.group(0)
    equation = "=" in expr

    def op_repl(om):
        op = om.group(0)
        sym = _js_trim(op)
        if sym == "+":
            return " 더하기 "
        if sym in ("*", "×"):
            return " 곱하기 "
        if sym == "÷":
            return " 나누기 "
        if sym == "±":
            return " 플러스 마이너스 "
        if sym in ("-", "−"):
            return " 빼기 " if equation else op
        if sym == "/":
            return " 나누기 " if equation else op
        before = expr[:om.start()]
        return ("는" if re.search(r"[2459%]" + _S + r"*\Z", before) else "은") + " "   # =

    return _MATH_OPERATOR_RE.sub(op_repl, expr)


def _kilo(m):
    value, suffix = m.group(1), m.group(2)
    return korean_number(str(_js_round(float(value) * (1_000_000 if suffix == "M" else 1000))))


def _thousands(m):
    whole, frac = m.group(1), m.group(2)
    return korean_number(whole.replace(",", "")) + (_korean_fraction(frac) if frac else "")


def read_numbers_ko(text):
    """날짜·시각·판 번호·수식·단위·천 단위 숫자를 한국어 말로 — 한국어 음성만. 기호를 지우기 전에 부른다."""
    text = _RE_YEAR_DATE.sub(_year_date, text)
    text = _RE_VERSION.sub(_version, text)
    text = _RE_CLOCK_X.sub(_clock_x, text)
    text = _RE_CLOCK.sub(_clock, text)
    text = _RE_RANGE_UNIT.sub(r"\1에서 \2", text)
    text = _RE_HYPHEN_DATE.sub(_month_day, text)
    text = _MATH.sub(_math, text)
    text = _RE_SLASH_DATE.sub(_month_day, text)
    text = _RE_SIGN.sub(lambda m: m.group(1) + ("플러스" if m.group(2) == "+" else "마이너스") + " ", text)
    text = _RE_KILO.sub(_kilo, text)
    text = _RE_TIMES.sub(r"\1배", text)
    text = _RE_UNIT.sub(lambda m: m.group(1) + UNIT_WORDS[m.group(2)], text)
    text = _RE_THOUSANDS.sub(_thousands, text)
    text = _RE_LEFT_TIMES.sub(" 곱하기 ", text)
    return _RE_TILDE.sub(r"\1에서 ", text)


# ── 입구 ───────────────────────────────────────────────────────────────
_RE_FENCE = re.compile(r"^" + _S + r"*(`{3,}|~{3,})[^\n]*$", re.M)
_RE_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_RE_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_PAREN_OPEN_NL = re.compile(r"([(（])[ \t]*\n" + _S + "*")
_RE_PAREN_CLOSE_NL = re.compile(_S + r"*\n[ \t]*([)）])")
_RE_LINE_MARK = re.compile(r"^" + _S + r"{0,3}(?:#{1,6}" + _S + r"+|>" + _S + r"*|[-+*]" + _S + r"+(?:\[[ xX]\]" + _S + r"*)?|[0-9]+[.)]" + _S + r"+)", re.M)
_RE_EMPHASIS = re.compile(r"(^|[" + WS + r"(])[*_]([^*_\n]+)[*_](?=\Z|[" + WS + r").,!?:;])")
_RE_RULE_LINE = re.compile(r"^" + _S + r"*[-*_]{3,}" + _S + r"*$", re.M)
_RE_ARROW = re.compile(r"→|⇒|->|=>|←|⇐|<-")
_RE_REPEAT = re.compile(r"([^0-9" + WS + r"])\1{3,}")
_RE_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:[./\\-][A-Za-z0-9_]+)*")
_RE_BULLET = re.compile(r"[•◦▪▫▸▹►▶●○■□◆◇★☆※]")
_RE_LIST_PAUSE = re.compile(r"[·‧∙…]")
_RE_COLON = re.compile(r"(?<![0-9]):|:(?![0-9])|;")
_RE_DASH = re.compile(r"[–—―]|(?<=[" + WS + r"])-(?=[" + WS + r"])")
_RE_PICTO = re.compile(r"[" + _U.PICTO + r"]|[\ufe0f\u200d\u20e3]")
_RE_QUOTE = re.compile(r"(?<![A-Za-z])['’]|['’](?![A-Za-z])")
_RE_OTHER = re.compile(r"[^" + _LN + _U.M + WS + r".,:?!%'’。、，！？：；،؛؟]")
_RE_SPACE_BEFORE_MARK = re.compile(r"[ \t\u00a0]+([.,?!])")
_RE_COMMA_AFTER_STOP = re.compile(r"([.?!]),+")
_RE_COMMAS = re.compile(r",(?:[ \t\u00a0]*,)+")
_RE_LINE_HEAD_MARK = re.compile(r"^[ \t\u00a0]*[,.]+", re.M)


def _token(m):
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", m.group(0))
    t = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", t)
    return re.sub(r"[._/\\-]+", " ", t)


def make_spoken_text(text, lang):
    """화면 글 → 음성에 보낼 글. lang = "ko"·"en"·… (speech_lang). 숫자를 말로 바꾸는 것은 "ko" 만."""
    spoken = _RE_FENCE.sub("", text)
    spoken = _RE_IMAGE.sub(r"\1", spoken)
    spoken = _RE_LINK.sub(r"\1", spoken)
    spoken = _URL.sub("URL", spoken)
    # 괄호 바로 안쪽의 줄바꿈은 먼저 없앤다(괄호 판정은 줄을 넘지 않는다)
    spoken = _RE_PAREN_CLOSE_NL.sub(r"\1", _RE_PAREN_OPEN_NL.sub(r"\1", spoken))
    # 표를 먼저 문장으로(칸 구분 | 가 지워지기 전에), 그다음 괄호
    spoken = drop_parens(table_to_sentences(spoken))
    spoken = shorten_paths(spoken)
    if lang == "ko":
        spoken = read_numbers_ko(spoken)
    spoken = _RE_LINE_MARK.sub("", spoken)
    spoken = re.sub(r"`+", "", spoken)
    spoken = re.sub(r"\*\*|__|~~", "", spoken)
    spoken = _RE_EMPHASIS.sub(r"\1\2", spoken)
    spoken = _RE_RULE_LINE.sub("", spoken)
    spoken = spoken.replace("|", " ")
    spoken = _RE_ARROW.sub(PAUSE, spoken)
    spoken = _RE_REPEAT.sub(lambda m: m.group(1) * REPEATED_CHARS_MAX, spoken)
    # 영어 이름 안 기호는 소리로 읽지 않고 띄운다(readaloud_text.py → "readaloud text py"). 대문자 두 글자(PC·OK)는 떼지 않는다
    spoken = _RE_TOKEN.sub(_token, spoken)
    # 남은 기호 — 숫자 안 점·콜론·쉼표와 %, 영어 낱말 안 작은따옴표, 문장 끝 부호만 둔다
    spoken = _RE_BULLET.sub(" ", spoken)
    spoken = _RE_LIST_PAUSE.sub(PAUSE, spoken)
    spoken = _RE_COLON.sub(PAUSE, spoken)
    spoken = _RE_DASH.sub(PAUSE, spoken)
    spoken = _RE_PICTO.sub(" ", spoken)
    spoken = _RE_QUOTE.sub(" ", spoken)
    spoken = _RE_OTHER.sub(" ", spoken)
    spoken = _RE_SPACE_BEFORE_MARK.sub(r"\1", spoken)
    spoken = _RE_COMMA_AFTER_STOP.sub(r"\1", spoken)
    spoken = _RE_COMMAS.sub(",", spoken)
    spoken = _RE_LINE_HEAD_MARK.sub("", spoken)
    spoken = re.sub(r"[ \t\u00a0]+", " ", spoken)
    spoken = re.sub(r" +\n", "\n", spoken)
    spoken = re.sub(r"\n{3,}", "\n\n", spoken)
    return _js_trim(spoken)
