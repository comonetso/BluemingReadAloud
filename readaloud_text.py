# -*- coding: utf-8 -*-
"""읽기용 텍스트 로직 — 크롬 확장 read-aloud-hrg 의 "드래그 읽기" 순수 로직을 파이썬으로 옮긴 것.

GUI·재생·whisperer.py 연결은 없다(순수 함수만). 기준은 확장 저장소의 커밋 EXTENSION_BASE_COMMIT 이다.

드래그 읽기에서 원문이 음성까지 가는 길 (확장 기준 파일:줄)
  1. 줄마다 나누기            js/player.js:81          text.split(/\\s*\\r?\\n\\s*/)
  2. 반복 문자·URL 전처리      js/document.js:210-213   truncateRepeatedChars(3) + URL → "HTTP URL."
  3. 줄 끝 마침표              js/speech.js:11-12       구두점으로 안 끝나는 줄에 '.'
  4. "\\n\\n" 으로 잇기          js/speech.js:13
  5. 조각 나누기               js/speech.js:128         CharBreaker(750, 문장부호 규칙, 200, keepApart=True)
                                                        60바이트 이하 짧은 줄은 다음 줄과 합침(speech.js:444,484-491)
  6. 읽기용 변환               js/spoken-text.js        README → "read me", 화살표 → 마침표, 천 단위 쉼표 제거 등
                                                        (sourceIndex: 변환 뒤 글자 → 조각 안 위치)
  7. 조각 → 원문 오프셋        js/page-ui-host.js:635-792  1~5단계를 위치를 들고 다시 돌려 조각을 원문에 맞춤.
                                                        한 글자라도 어긋나면 None(형광펜만 포기, 읽기는 계속)

공개 함수: split_for_reading(source_text, lang, voice_lang=None, words=None)
  → [{"text": 음성에 보낼 글, "src_start": int|None, "src_end": int|None}, ...]
     src 는 source_text 기준 반열린 구간 [src_start, src_end). 파이썬 문자열 인덱스(코드 포인트) 단위.

JS 와의 차이를 흡수한 곳
  - 정규식의 \\s, \\w, \\d, $ 는 JS 의미로 맞췄다(_WS, [A-Za-z0-9_], [0-9], \\Z).
  - JS 문자열 길이(.length, 750자 한도)는 UTF-16 단위다. 한도 비교는 _u16len 으로 UTF-16 길이를 쓴다.
  - JS 의 charCodeAt 비교(반복 문자 줄이기)는 이모지 같은 보조 평면 글자를 "반복"으로 보지 않는다. 그대로 흉내 냈다.
  - \\p{Script=Latin} 은 node(Unicode 16.0)에서 뽑은 구간표(_LATIN_RANGES)를 쓴다.
  - \\p{L}, \\p{N} 은 unicodedata 분류(L*, N*)로 판정한다(파이썬 Unicode 버전에 따름).
알려진 차이(아주 드묾): 공백 없는 750(UTF-16)자 초과 덩어리를 글자 단위로 자를 때, 자르는 자리가
이모지(서로게이트 쌍) 한가운데이면 JS 는 쌍을 쪼개고 파이썬은 이모지를 통째로 다음 조각에 넘긴다.

확장과 똑같이 따라 한 버릇(고치지 않음 — 고치면 확장과 어긋난다)
  - 라틴 규칙(lang 이 zh/ko/ja 아님)에서 750자 넘는 구를 단어로 쪼갤 때 구 첫머리의 - / — 가 사라진다
    → 정렬 전체가 None (예: 750자 넘는 영어 불릿 줄 "- word word ...")
  - 동아시아 규칙에서 750자 넘는 구는 공백이 모두 빠진 채 음성으로 간다
  - 공백 없는 줄이 딱 750(UTF-16)자면 줄 끝에 붙인 '.' 하나가 따로 조각이 되고, 그 조각의 원문 구간은 None
  - 공백(탭·전각 공백 포함)도 반복 문자 규칙을 받는다(4개 이상 → 3개). 줄은 \\n 에서만 나뉜다(\\r 단독·U+2028 은 아님)
"""

import re
import unicodedata

__all__ = [
    "EXTENSION_BASE_COMMIT",
    "CHAR_LIMIT", "PARAGRAPH_COMBINE_THRESHOLD", "SHORT_LINE_BYTES", "REPEATED_CHARS_MAX", "URL_REPLACEMENT",
    "SPOKEN_ARROW_SPACE",
    "split_for_reading",
    "split_lines", "preprocess", "needs_period", "is_east_asian",
    "build_segments", "CharBreaker", "LatinPunctuator", "EastAsianPunctuator",
    "truncate_repeated_chars", "truncate_repeated_chars_tracked", "replace_urls_tracked",
    "align_segments_to_source", "Alignment",
    "make_spoken_text", "spoken_text", "SpokenText",
    "pauses_markup", "load_english_words",
]

# 이식 기준: F:\workspace\EtcProject\ChromeExtentions\read-aloud-hrg 의 HEAD
# (afae39a "fix(speech): 한국어 음성이 "VS Code"를 "대 코드"로 읽던 문제").
# 처음 옮길 때는 9751e0b 였고, 그 뒤 바뀐 것은 spoken-text.js 의 spelled·keptRun·두 글자 복수형뿐이다
# (speech.js·player.js·document.js·page-ui-host.js·truncateRepeatedChars 는 두 커밋이 같다)
EXTENSION_BASE_COMMIT = "afae39a"

# ── 확장 코드에 있는 값 그대로 ────────────────────────────────────────────
CHAR_LIMIT = 750                    # speech.js:128  CharBreaker(750, ...)
PARAGRAPH_COMBINE_THRESHOLD = 200   # speech.js:128  CharBreaker(..., 200, ...) — keepApart 에선 쓰이지 않음
SHORT_LINE_BYTES = 60               # speech.js:444
REPEATED_CHARS_MAX = 3              # document.js:211  truncateRepeatedChars(text, 3)
URL_REPLACEMENT = "HTTP URL."       # document.js:212
SPOKEN_ARROW_SPACE = "\u2003"       # spoken-text.js:61  화살표 뒤 공백(em space)

# ── JS 정규식 문자 집합 ────────────────────────────────────────────────
# JS 의 \s (node 로 확인: 9-d 20 a0 1680 2000-200a 2028-2029 202f 205f 3000 feff)
_WS = r"\t\n\x0b\x0c\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_WS_SET = frozenset(
    "\t\n\x0b\x0c\r \u00a0\u1680\u2028\u2029\u202f\u205f\u3000\ufeff"
    + "".join(chr(c) for c in range(0x2000, 0x200B))
)

# \p{Script=Latin} — node v22(Unicode 16.0)의 /\p{Script=Latin}/u 로 뽑은 구간
_LATIN_RANGES = (
    (65, 90), (97, 122), (170, 170), (186, 186), (192, 214), (216, 246), (248, 696), (736, 740),
    (7424, 7461), (7468, 7516), (7522, 7525), (7531, 7543), (7545, 7614), (7680, 7935), (8305, 8305),
    (8319, 8319), (8336, 8348), (8490, 8491), (8498, 8498), (8526, 8526), (8544, 8584), (11360, 11391),
    (42786, 42887), (42891, 42957), (42960, 42961), (42963, 42963), (42965, 42972), (42994, 43007),
    (43824, 43866), (43868, 43876), (43878, 43881), (64256, 64262), (65313, 65338), (65345, 65370),
    (67456, 67461), (67463, 67504), (67506, 67514), (122624, 122654), (122661, 122666),
)
_LATIN_CLASS = "".join(
    "\\U%08x" % a if a == b else "\\U%08x-\\U%08x" % (a, b) for a, b in _LATIN_RANGES
)

# 구두점 (speech.js:11, spoken-text.js:56-57)
_PAUSE_CHARS = ".!?,;:\u2026\u3002\uff01\uff1f\u3001\uff0c\uff1b\uff1a"
_OPENING_CHARS = "([{<\u201c\u2018"


def _is_ws(c):
    return c is not None and c in _WS_SET


def _is_ascii_digit(c):
    return c is not None and "0" <= c <= "9"


def _u16len(s):
    """JS 의 string.length (UTF-16 코드 단위 수)."""
    n = len(s)
    for c in s:
        if ord(c) > 0xFFFF:
            n += 1
    return n


def _u16_prefix(s, limit):
    """UTF-16 길이가 limit 을 넘지 않는 가장 긴 앞부분의 글자 수(코드 포인트)."""
    units = 0
    for i, c in enumerate(s):
        units += 2 if ord(c) > 0xFFFF else 1
        if units > limit:
            return i
    return len(s)


# ════════════════════════════════════════════════════════════════════
# 1~4단계: 줄 나누기 · 전처리 · 줄 끝 마침표
# ════════════════════════════════════════════════════════════════════

# player.js:81 / page-ui-host.js:651  /\s*\r?\n\s*/
_LINE_SEPARATOR = re.compile("[" + _WS + "]*\r?\n[" + _WS + "]*")

# document.js:212 / page-ui-host.js:777  /https?:\/\/\S+/g
_URL = re.compile(r"https?://[^" + _WS + r"]+")

# speech.js:11 (splitParagraphs) / page-ui-host.js:660
_NEEDS_PERIOD = re.compile(r"[^" + _WS + _PAUSE_CHARS + r"]\Z")


def split_lines(source_text):
    """원문을 줄마다 나눈다. [(줄 글, 원문 안 시작 위치), ...]  (page-ui-host.js:650-658)"""
    lines = []
    last = 0
    for m in _LINE_SEPARATOR.finditer(source_text):
        lines.append((source_text[last:m.start()], last))
        last = m.end()
    lines.append((source_text[last:], last))
    return lines


def truncate_repeated_chars_tracked(text, src, max_count=REPEATED_CHARS_MAX):
    """같은 글자가 max_count 개를 넘게 이어지면 max_count 개만 남긴다. src 는 글자마다 원래 위치.

    defaults.js:646-662 / page-ui-host.js:750-772. 숫자는 줄이지 않는다.
    JS 는 UTF-16 코드 단위로 비교하므로 보조 평면 글자(이모지 등)는 반복으로 치지 않는다 — 같게 맞췄다.
    """
    out, out_src = [], []
    start = 0
    count = 1
    for i in range(1, len(text)):
        c = text[i]
        if c == text[i - 1] and ord(c) <= 0xFFFF and not _is_ascii_digit(c):
            count += 1
            if count == max_count:
                out.append(text[start:i + 1])
                out_src.extend(src[start:i + 1])
        else:
            if count >= max_count:
                start = i
            count = 1
    if count < max_count:
        out.append(text[start:])
        out_src.extend(src[start:])
    return "".join(out), out_src


def truncate_repeated_chars(text, max_count=REPEATED_CHARS_MAX):
    return truncate_repeated_chars_tracked(text, list(range(len(text))), max_count)[0]


def replace_urls_tracked(text, src):
    """URL 을 "HTTP URL." 로 바꾼다. 바꾼 글의 첫·끝 글자는 URL 의 양 끝을 가리킨다(page-ui-host.js:774-792)."""
    out, out_src = [], []
    last = 0
    n = len(URL_REPLACEMENT)
    for m in _URL.finditer(text):
        out.append(text[last:m.start()])
        out_src.extend(src[last:m.start()])
        out.append(URL_REPLACEMENT)
        for k in range(n):
            if k == 0:
                out_src.append(src[m.start()])
            elif k == n - 1:
                out_src.append(src[m.end() - 1])
            else:
                out_src.append(-1)
        last = m.end()
    out.append(text[last:])
    out_src.extend(src[last:])
    return "".join(out), out_src


def preprocess(text):
    """document.js:210-213 preprocess()."""
    return _URL.sub(URL_REPLACEMENT, truncate_repeated_chars(text, REPEATED_CHARS_MAX))


def needs_period(text):
    """드래그 읽기에서 줄 끝에 '.' 을 붙일지 (speech.js:11 splitParagraphs 규칙)."""
    return _NEEDS_PERIOD.search(text) is not None


def is_east_asian(lang):
    """speech.js:116  /^zh|ko|ja/.test(options.lang) — 정규식 우선순위까지 그대로(ko·ja 는 어디든 있으면 참)."""
    return re.search(r"^zh|ko|ja", str(lang or "")) is not None


# ════════════════════════════════════════════════════════════════════
# 5단계: 조각 나누기 (speech.js:440-555)
# ════════════════════════════════════════════════════════════════════

def _recombine_latin(tokens, non_punc=None):
    result = []
    for i in range(0, len(tokens), 2):
        part = tokens[i] + tokens[i + 1] if i + 1 < len(tokens) else tokens[i]
        if part:
            if non_punc is not None and result and non_punc.search(result[-1]):
                result[-1] += part
            else:
                result.append(part)
    return result


def _recombine_ea(tokens):
    result = []
    for i in range(0, len(tokens), 2):
        if i + 1 < len(tokens):
            result.append(tokens[i] + tokens[i + 1])
        elif tokens[i]:
            result.append(tokens[i])
    return result


_PARAGRAPHS = re.compile("((?:\r?\n[" + _WS + "]*){2,})")


class LatinPunctuator:
    """speech.js:499-532."""
    _SENTENCES = re.compile(r"([.!?]+[" + _WS + r"\u200b]+)")
    _NON_PUNC = re.compile(
        r"\b(\w|[A-Z][a-z]|Assn|Ave|Capt|Col|Comdr|Corp|Cpl|Gen|Gov|Hon|Inc|Lieut|Ltd|Rev|Univ"
        r"|Jan|Feb|Mar|Apr|Aug|Sept|Oct|Nov|Dec|dept|ed|est|vol|vs)\.[" + _WS + r"]+\Z",
        re.ASCII,
    )
    _PHRASES = re.compile(r"([,;:][" + _WS + r"]+|[" + _WS + r"]-+[" + _WS + r"]+|\u2014[" + _WS + r"]*)")
    _WORDS = re.compile(r"([~@#%^*_+=<>]|[" + _WS + r"\-\u2014/]+|\.(?=[A-Za-z0-9_]{2,})|,(?=[0-9]))")
    _WORD_SIGN = re.compile(r"[~@#%^*_+=<>]")

    def get_paragraphs(self, text):
        return _recombine_latin(_PARAGRAPHS.split(text))

    def get_sentences(self, text):
        return _recombine_latin(self._SENTENCES.split(text), self._NON_PUNC)

    def get_phrases(self, sentence):
        return _recombine_latin(self._PHRASES.split(sentence))

    def get_words(self, sentence):
        tokens = self._WORDS.split(sentence)
        result = []
        for i in range(0, len(tokens), 2):
            if tokens[i]:
                result.append(tokens[i])
            if i + 1 < len(tokens):
                if self._WORD_SIGN.fullmatch(tokens[i + 1]):
                    result.append(tokens[i + 1])
                elif result:
                    result[-1] += tokens[i + 1]
        return result


class EastAsianPunctuator:
    """speech.js:534-555. 단어 = 공백을 뺀 글자 하나하나."""
    _SENTENCES = re.compile(r"([.!?]+[" + _WS + r"\u200b]+|[\u3002\uff01]+)")
    _PHRASES = re.compile(r"([,;:][" + _WS + r"]+|[\u2025\u2026\u3000\u3001\uff0c\uff1b]+)")
    _SPACES = re.compile("[" + _WS + "]+")

    def get_paragraphs(self, text):
        return _recombine_ea(_PARAGRAPHS.split(text))

    def get_sentences(self, text):
        return _recombine_ea(self._SENTENCES.split(text))

    def get_phrases(self, sentence):
        return _recombine_ea(self._PHRASES.split(sentence))

    def get_words(self, sentence):
        return list(self._SPACES.sub("", sentence))


_SPACES = re.compile("[" + _WS + "]+")
_TRAILING_DOT = re.compile(r"\.\Z")


class CharBreaker:
    """speech.js:440-497. 단락 → 문장 → 구 → 단어 순으로, char_limit 을 넘는 것만 더 잘게 쪼갠다.

    keep_paragraphs_apart(드래그 읽기): 줄마다 따로 읽되, 공백을 뺀 UTF-8 60바이트 이하(줄 끝 '.' 은 안 셈)의
    짧은 줄은 다음 줄과 합친다.
    """

    def __init__(self, char_limit, punctuator, paragraph_combine_threshold=None, keep_paragraphs_apart=False):
        self.char_limit = char_limit
        self.punctuator = punctuator
        self.paragraph_combine_threshold = paragraph_combine_threshold
        self.keep_paragraphs_apart = keep_paragraphs_apart

    def break_text(self, text):
        return self._merge(self.punctuator.get_paragraphs(text), self._break_paragraph,
                           self.paragraph_combine_threshold, self.keep_paragraphs_apart)

    def _break_paragraph(self, text):
        return self._merge(self.punctuator.get_sentences(text), self._break_sentence)

    def _break_sentence(self, sentence):
        return self._merge(self.punctuator.get_phrases(sentence), self._break_phrase)

    def _break_phrase(self, phrase):
        return self._merge(self.punctuator.get_words(phrase), self._break_word)

    def _break_word(self, word):
        # JS: word.slice(0, charLimit) — UTF-16 단위. 이모지 한가운데서 끊기는 경우만 다르다(모듈 설명 참조)
        result = []
        while word:
            cut = _u16_prefix(word, self.char_limit) or 1
            result.append(word[:cut])
            word = word[cut:]
        return result

    def _merge(self, parts, break_part, combine_threshold=None, keep_apart=False):
        result = []
        group = []
        char_count = 0
        spoken_bytes = 0
        for part in parts:
            count = _u16len(part)
            if count > self.char_limit:
                if group:
                    result.append("".join(group))
                    group, char_count, spoken_bytes = [], 0, 0
                result.extend(break_part(part))
            else:
                if keep_apart:
                    full = spoken_bytes > SHORT_LINE_BYTES or char_count + count > self.char_limit
                else:
                    full = char_count + count > (combine_threshold or self.char_limit)
                if full and group:
                    result.append("".join(group))
                    group, char_count, spoken_bytes = [], 0, 0
                group.append(part)
                char_count += count
                # 줄 끝 '.' 은 세지 않는다: Speech() 가 구두점 없는 줄에 붙인 것 (speech.js:490-491)
                if keep_apart:
                    squeezed = _TRAILING_DOT.sub("", _SPACES.sub("", part))
                    spoken_bytes += len(squeezed.encode("utf-8", "surrogatepass"))
        if group:
            result.append("".join(group))
        return result


def build_segments(source_text, lang):
    """드래그 읽기 원문 → 음성 엔진이 한 번에 읽는 조각(읽기용 변환 전) 목록.

    player.js:81 → document.js:182,210-213 → speech.js:11-13,128 (Chirp3-HD 등 구글 클라우드 음성 경로).
    lang: 확장의 options.lang (문장부호 규칙 선택: zh/ko/ja 면 동아시아).
    """
    texts = [preprocess(t) for t in _LINE_SEPARATOR.split(source_text)]
    texts = [t + "." if needs_period(t) else t for t in texts]
    if not texts:
        return []
    punctuator = EastAsianPunctuator() if is_east_asian(lang) else LatinPunctuator()
    breaker = CharBreaker(CHAR_LIMIT, punctuator, PARAGRAPH_COMBINE_THRESHOLD, True)
    return breaker.break_text("\n\n".join(texts))


# ════════════════════════════════════════════════════════════════════
# 7단계: 조각 → 원문 오프셋 (page-ui-host.js:635-747)
# ════════════════════════════════════════════════════════════════════

_WORD_END = frozenset(".,!?;:\"'()[]{}\u3001\u3002\uff0c\uff01\uff1f") | _WS_SET


class Alignment:
    """조각마다 글자별 원문 위치표(-1 = 끼워 넣은 글자)."""

    def __init__(self, seg_texts, maps):
        self.seg_texts = list(seg_texts)
        self.maps = maps

    def segment_range(self, index):
        """조각 index 가 원문에서 차지하는 [start, end). 원문 글자가 하나도 없으면 None."""
        if not (0 <= index < len(self.maps)):
            return None
        m = self.maps[index]
        return _span_of(m, 0, len(m))

    def word_range(self, index, char_index, length=None):
        """조각 안 단어(char_index, length)의 원문 [start, end). length 가 없으면 공백·구두점까지 늘린다."""
        if not (0 <= index < len(self.maps)):
            return None
        m = self.maps[index]
        seg = self.seg_texts[index]
        if char_index is None or not (char_index >= 0) or char_index >= len(seg):
            return None
        has_length = length is not None and length > 0
        end = char_index + length if has_length else char_index
        if not has_length:
            while end < len(seg) and seg[end] not in _WORD_END:
                end += 1
        return _span_of(m, char_index, max(end, char_index + 1))


def _span_of(m, start, end):
    lo, hi = None, -1
    for j in range(start, min(end, len(m))):
        v = m[j]
        if v >= 0:
            if lo is None or v < lo:
                lo = v
            if v > hi:
                hi = v
    return (lo, hi + 1) if hi >= 0 else None


def align_segments_to_source(source_text, seg_texts):
    """조각(build_segments 결과)을 원문 오프셋에 맞춘다. 어긋나면 None (page-ui-host.js:649-661, 682-747).

    조각은 이어 붙인 글 위에서 앞에서부터 차례로 맞춘다. 공백은 건너뛰고, 공백 아닌 글자가 어긋나면 None.
    """
    joined, joined_src = [], []
    for i, (original, base) in enumerate(split_lines(source_text)):
        src = list(range(base, base + len(original)))
        text, src = truncate_repeated_chars_tracked(original, src, REPEATED_CHARS_MAX)
        text, src = replace_urls_tracked(text, src)
        # document.js preprocess() 와 반드시 같아야 한다
        if text != preprocess(original):
            return None
        if needs_period(text):
            text += "."
            src.append(-1)
        if i > 0:
            joined.extend("\n\n")
            joined_src.extend((-1, -1))
        joined.extend(text)
        joined_src.extend(src)

    maps = []
    pos = 0
    total = len(joined)
    for seg in seg_texts:
        m = [-1] * len(seg)
        for j, c in enumerate(seg):
            while pos < total and joined[pos] != c and joined[pos] in _WS_SET:
                pos += 1
            if pos < total and joined[pos] == c:
                m[j] = joined_src[pos]
                pos += 1
            elif c not in _WS_SET:
                return None
        maps.append(m)
    return Alignment(seg_texts, maps)


# ════════════════════════════════════════════════════════════════════
# 6단계: 읽기용 변환 (spoken-text.js)
# ════════════════════════════════════════════════════════════════════

# spoken-text.js:27-29 — 대문자 단어 사이에서 단어로 읽는 두 글자 단어
SPOKEN_SHORT_WORDS = frozenset([
    "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is", "me", "my", "of", "on", "or", "so", "to",
    "up", "we",
])
# spoken-text.js:32
SPOKEN_CODE_SHORT_WORDS = SPOKEN_SHORT_WORDS | {"no"}
# spoken-text.js:35-38
SPOKEN_SIGNS = {
    "ko": {".": "쩜", "-": "대시", "_": "언더바", "/": "슬래시"},
    "en": {".": "dot", "-": "dash", "_": "underscore", "/": "slash"},
}
# spoken-text.js:41
SPOKEN_LONGEST_WORD = 32

_LATIN_OR_DIGIT = "[" + _LATIN_CLASS + "0-9]"
# spoken-text.js:46  (?<=^|[...]) 는 파이썬에서 (?<![^...]) 로 바꿨다(뜻 같음)
_SPOKEN_TOKEN = re.compile(
    r"(?<!" + _LATIN_OR_DIGIT + r")"
    r"(?:(?<![^" + _WS + r"(\[{<\"'`\u201c\u2018=:~])[./]{1,3}(?=[A-Za-z]))?"
    r"[A-Za-z0-9]+(?:['\u2019][A-Za-z]+)?"
    r"(?:[._\-/][A-Za-z0-9]+(?:['\u2019][A-Za-z]+)?)*"
    r"(?!" + _LATIN_OR_DIGIT + r")"
)
# spoken-text.js:49
_SPOKEN_THOUSANDS = re.compile(r"(?<![0-9,.])[0-9]{1,3}(?:,[0-9]{3})+(?![0-9]|,[0-9])")
# spoken-text.js:53
_ARROWS = r"\u2192\u21d2\u21e8\u21fe\u27f6\u27f9\u2794\u279c\u279d\u279e\u27a1\u2b95"
_SPOKEN_MARKS = re.compile(
    r"([" + _WS + r"]*(?:[" + _ARROWS + r"]\ufe0f?|(?<![^" + _WS + r"])-{1,2}>(?=[" + _WS + r"]|\Z))["
    + _WS + r"]*)"
    r"|(\*{2,})"
    r"|([" + _WS + r"]*/+[" + _WS + r"]*)"
)
_CAMEL_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")
_CAPITAL_WORD = re.compile(r"[A-Z]+(?:['\u2019][A-Z]+)?")
_APOSTROPHE_WORD = re.compile(r"([A-Za-z0-9]+)(['\u2019][A-Za-z]+)")
_ALL_CAPS = re.compile(r"[A-Z]+")
_PLURAL_ABBR = re.compile(r"([A-Z]{2,})s")
_VOWEL = re.compile(r"[aeiouy]")
_ASCII_LETTER = re.compile(r"[A-Za-z]")
_ASCII_DIGIT = re.compile(r"[0-9]")
_SIGN_SPLIT = re.compile(r"([._\-/])")
_TWO_CAPITALS = re.compile(r"[A-Z]{2}")


class SpokenText:
    """음성에 넘길 글과, 그 글자마다 조각 안 원래 위치(src)."""

    def __init__(self, text, src, source_length, identity=False):
        self.text = text
        self.src = src
        self._source_length = source_length
        self._identity = identity

    def source_index(self, i):
        """변환 뒤 i 번째 글자가 조각의 몇 번째 글자에서 왔는지 (i == len(text) 면 조각 끝)."""
        if self._identity:  # speech.js:111 실패 시 {sourceIndex: i => i}
            return i
        return self.src[i] if 0 <= i < len(self.src) else self._source_length


def _letter_or_number(s):
    # /[\p{L}\p{N}]/u
    for c in s:
        if unicodedata.category(c)[0] in "LN":
            return True
    return False


def make_spoken_text(text, lang, words=None):
    """spoken-text.js:64-351 makeSpokenText(). words: 영어 단어 → SCOWL 레벨 (load_english_words).

    words 가 None 이면 빈 목록으로 본다: 대문자 영어 단어를 소문자로 읽히게 하는 규칙(README → read me)이 안 걸린다.
    """
    words = {} if words is None else words
    language = re.match(r"(ko|en)(?![a-z])", str(lang or ""), re.I)
    signs = SPOKEN_SIGNS[language.group(1).lower()] if language else None
    out = []
    src = []

    # ── 조각(글, 위치표) 만들기 ──
    def keep(s, at):
        return s, list(range(at, at + len(s)))

    def lowered(s, at):
        return s.lower(), list(range(at, at + len(s)))

    def capitals(s, at):
        return s.upper(), list(range(at, at + len(s)))

    def inserted(s, at):
        return s, [at] * len(s)

    def spelled(s, at):
        # spoken-text.js:167-171 (afae39a) — 한국어 음성에는 두 글자 대문자를 떼어 준다(VS → "V S")
        up = capitals(s, at)
        if signs is not SPOKEN_SIGNS["ko"] or len(s) != 2:
            return up
        return join([(up[0][0], [at]), inserted(" ", at + 1), (up[0][1], [at + 1])])

    def join(pieces):
        t, s = [], []
        for piece in pieces:
            t.append(piece[0])
            s.extend(piece[1])
        return "".join(t), s

    def spaced(parts, at):
        pieces = []
        for part in parts:
            if pieces:
                pieces.append(inserted(" ", at))
            pieces.append(lowered(part, at))
            at += len(part)
        return join(pieces)

    def put(piece):
        out.append(piece[0])
        src.extend(piece[1])

    # ── 규칙 ──
    def speak_token(token):
        tok, at, in_capital_run = token["text"], token["at"], token["in_capital_run"]
        if not _ASCII_LETTER.search(tok):
            return keep(tok, at)
        lead = re.match(r"[./]*", tok).group(0)
        body, body_at = tok[len(lead):], at + len(lead)
        parts = _SIGN_SPLIT.split(body)
        if len(parts) == 1 and not lead:
            return speak_word(body, body_at, False, in_capital_run)

        def number(p):
            return _ASCII_DIGIT.match(p) is not None

        def letter(p):
            return re.fullmatch(r"[A-Za-z]", p) is not None

        said = []
        for k in range(1, len(parts), 2):
            sign, left, right = parts[k], parts[k - 1], parts[k + 1]
            if (number(left) and number(right)) or (letter(left) and letter(right)):
                said.append(False)
            elif sign == "_":
                said.append(True)
            elif letter(left) or letter(right):
                said.append(False)
            elif sign != "/" and (number(left) or number(right)):
                said.append(False)
            elif sign == ".":
                said.append(True)
            elif sign == "-" and len(left) <= 2 and len(right) <= 2:
                said.append(False)
            else:
                said.append(None)
        code_name = bool(lead) or (True in said) or parts.count("/") >= 2
        for k in range(len(said)):
            if said[k] is None:
                said[k] = code_name or (parts[2 * k + 1] == "-" and signs is SPOKEN_SIGNS["ko"])

        runs = []
        run_start, run_at = 0, body_at
        for k in range(len(said) + 1):
            if k < len(said) and not said[k]:
                continue
            run = "".join(parts[run_start:2 * k + 1])
            runs.append({"text": run, "at": run_at, "single": run_start == 2 * k,
                         "sign": parts[2 * k + 1] if k < len(said) else None})
            run_start = 2 * k + 2
            run_at += len(run) + 1
        capital_name = (
            all(r["single"] and _ALL_CAPS.fullmatch(r["text"]) for r in runs)
            and any(len(r["text"]) > 2 and speak_capitals(r["text"], r["at"], False)[0] != r["text"] for r in runs)
        )

        pieces = []
        for k, ch in enumerate(lead):
            pieces.append(inserted(signs[ch] + " ", at + k))
        for r in runs:
            if r["single"]:
                pieces.append(speak_word(r["text"], r["at"], True, capital_name or in_capital_run))
            else:
                pieces.append(kept_run(r["text"], r["at"]))
            if r["sign"]:
                pieces.append(inserted(" " + signs[r["sign"]] + " ", r["at"] + len(r["text"])))
        return join(pieces)

    def kept_run(run, at):
        # spoken-text.js:248-255 (afae39a) — 말하지 않는 기호로 이어진 덩어리(UI/UX, GPT-4)는 그대로 두되
        # 두 글자 대문자 부분만 spelled
        pieces = []
        for part in _SIGN_SPLIT.split(run):
            pieces.append(spelled(part, at) if _TWO_CAPITALS.fullmatch(part) else keep(part, at))
            at += len(part)
        return join(pieces)

    def speak_word(word, at, in_code, in_capital_run):
        if "'" in word or "\u2019" in word:
            return speak_apostrophe(word, at, in_capital_run)
        if not _ASCII_LETTER.search(word) or _ASCII_DIGIT.search(word):
            return keep(word, at)
        plural = _PLURAL_ABBR.fullmatch(word)
        if plural:
            if len(plural.group(1)) <= 2:  # spoken-text.js:266 (afae39a) — PCs, IDs 는 그대로
                return keep(word, at)
            stem = speak_capitals(plural.group(1), at, in_capital_run)
            if stem[0] == plural.group(1):
                return keep(word, at)
            return join([stem, keep("s", at + len(plural.group(1)))])
        camel = _CAMEL_PARTS.findall(word)
        if len(camel) > 1:
            pieces = []
            part_at = at
            for part in camel:
                spoken = speak_part(part, part_at, True)
                if spoken is None:
                    return keep(word, at)
                if pieces:
                    pieces.append(inserted(" ", part_at))
                pieces.append(spoken)
                part_at += len(part)
            return join(pieces)
        if word == word.upper():
            return speak_capitals(word, at, in_capital_run)
        if in_code:
            spoken = speak_part(word, at, False)
            if spoken is not None:
                return spoken
        return keep(word, at)

    def speak_apostrophe(word, at, in_capital_run):
        m = _APOSTROPHE_WORD.fullmatch(word)
        if not m or _ASCII_DIGIT.search(m.group(1)) or m.group(1) != m.group(1).upper():
            return keep(word, at)
        stem, tail = m.group(1), m.group(2)
        if word == word.upper() and word.lower().replace("\u2019", "'") in words:
            return lowered(word, at)
        if not re.fullmatch(r"['\u2019]s", tail, re.I):
            return keep(word, at)
        spoken = speak_capitals(stem, at, in_capital_run)
        tail_at = at + len(stem)
        return join([spoken, keep(tail, tail_at) if spoken[0] == stem else lowered(tail, tail_at)])

    def speak_part(part, at, in_camel):
        if len(part) > 2 and part == part.upper():
            return speak_capitals(part, at, False)
        lower = part.lower()
        if len(part) <= 2:
            if lower in SPOKEN_CODE_SHORT_WORDS:
                return keep(part, at)
            return None if in_camel else spelled(part, at)
        if not _VOWEL.search(lower):
            return capitals(part, at)
        return keep(part, at) if lower in words else None

    def speak_capitals(word, at, in_capital_run):
        lower = word.lower()
        if len(word) <= 2:
            return lowered(word, at) if in_capital_run and lower in SPOKEN_SHORT_WORDS else spelled(word, at)
        if not _VOWEL.search(lower):
            return keep(word, at)
        if lower in words:
            return lowered(word, at)
        run = split_into_words(lower)
        return spaced(run, at) if run else keep(word, at)

    def split_into_words(w):
        best = {0: (None, 0, 0)}  # i → (from, count, level)
        for i in range(2, len(w) + 1):
            for j in range(max(0, i - SPOKEN_LONGEST_WORD), i - 1):
                if j not in best:
                    continue
                part = w[j:i]
                if len(part) > 2:
                    level = words.get(part)
                else:
                    level = 0 if part in SPOKEN_SHORT_WORDS else None
                if level is None:
                    continue
                count = best[j][1] + 1
                total = best[j][2] + level
                cur = best.get(i)
                if cur is None or count < cur[1] or (count == cur[1] and total < cur[2]):
                    best[i] = (j, count, total)
        if len(w) not in best or best[len(w)][1] < 2:
            return None
        parts = []
        i = len(w)
        while i > 0:
            parts.insert(0, w[best[i][0]:i])
            i = best[i][0]
        return parts

    def mark_capital_runs(tokens):
        def lowers(token):
            return len(token["text"]) > 2 and speak_word(token["text"], token["at"], False, False)[0] != token["text"]

        run = []

        def flush():
            if any(lowers(t) for t in run):
                for t in run:
                    t["in_capital_run"] = True
            run.clear()

        for k, token in enumerate(tokens):
            if not _CAPITAL_WORD.fullmatch(token["text"]):
                flush()
                continue
            if run:
                prev = tokens[k - 1]
                if _letter_or_number(text[prev["at"] + len(prev["text"]):token["at"]]):
                    flush()
            run.append(token)
        flush()

    def say_marks():
        # 화살표 → 마침표, 슬래시 → 쉼표, 별표 → 없음. 숫자 사이의 슬래시·별표(9/27, 2**3)는 그대로
        cur = "".join(out).replace(SPOKEN_ARROW_SPACE, " ")
        cur_src = list(src)
        kept, kept_src = [], []
        last = 0
        for m in _SPOKEN_MARKS.finditer(cur):
            marks, arrow, stars = m.group(0), m.group(1), m.group(2)
            at, end = m.start(), m.end()
            after = cur[end] if end < len(cur) else None
            before_mark = cur[at - 1] if at > 0 else None
            if (arrow is None and _is_ascii_digit(before_mark) and _is_ascii_digit(after)
                    and not any(ch in _WS_SET for ch in marks)):
                continue
            kept.extend(cur[last:at])
            kept_src.extend(cur_src[last:at])
            last = end
            if stars is not None:
                continue
            while kept and kept[-1] in _WS_SET:
                kept.pop()
                kept_src.pop()
            before = kept[-1] if kept else None
            if before is None or (after is None and arrow is None) or (after is not None and after in _PAUSE_CHARS):
                continue
            if before in _OPENING_CHARS:
                said = ""
            else:
                said = ("" if before in _PAUSE_CHARS else "." if arrow is not None else ",") + (
                    "" if after is None else SPOKEN_ARROW_SPACE if arrow is not None else " ")
            first = next(k for k, ch in enumerate(marks) if ch not in _WS_SET)
            origin = cur_src[at + first]
            kept.extend(said)
            kept_src.extend([origin] * len(said))
        kept.extend(cur[last:])
        kept_src.extend(cur_src[last:])
        return "".join(kept), kept_src

    def drop_thousands_separators(cur, cur_src):
        drop = set()
        for m in _SPOKEN_THOUSANDS.finditer(cur):
            for k, ch in enumerate(m.group(0)):
                if ch == ",":
                    drop.add(m.start() + k)
        if not drop:
            return cur, cur_src
        kept, kept_src = [], []
        for i, ch in enumerate(cur):
            if i in drop:
                continue
            kept.append(ch)
            kept_src.append(cur_src[i])
        return "".join(kept), kept_src

    if signs is not None:
        tokens = [{"text": m.group(0), "at": m.start(), "in_capital_run": False}
                  for m in _SPOKEN_TOKEN.finditer(text)]
        mark_capital_runs(tokens)
        last = 0
        for token in tokens:
            put(keep(text[last:token["at"]], last))
            put(speak_token(token))
            last = token["at"] + len(token["text"])
        put(keep(text[last:], last))
        result, result_src = say_marks()
        if signs is SPOKEN_SIGNS["ko"]:
            result, result_src = drop_thousands_separators(result, result_src)
    else:
        result, result_src = text, list(range(len(text)))
    return SpokenText(result, result_src, len(text))


def spoken_text(text, lang, words=None):
    """speech.js:104-113 — 변환이 실패하면 글을 그대로 읽는다(읽지 않는 것보다 낫다)."""
    try:
        return make_spoken_text(text, lang, words)
    except Exception:
        return SpokenText(text, list(range(len(text))), len(text), identity=True)


def pauses_markup(text, voice_lang, voice_type):
    """tts-engines.js:542-550 — 한국어 Chirp3-HD 에 쉼표·화살표 자리 쉼을 요청하는 markup. 해당 없으면 None.

    확장은 이 markup 으로 먼저 요청하고 거절되면 평문(text)으로 다시 요청한다(tts-engines.js:530-535).
    """
    if (voice_type != "Chirp3-HD" or not re.match(r"ko", str(voice_lang or ""), re.I)
            or not re.search(r",[" + _WS + r"]|\u2003", text)):
        return None
    t = text.replace("[", "(").replace("]", ")")
    t = re.sub(r",(?=[" + _WS + r"])", ", [pause short]", t)
    return t.replace("\u2003", " [pause] ")


def load_english_words(path):
    """확장의 js/english-words.js 형식(레벨: "단어 단어 ...")을 읽어 {단어: 레벨} 로 돌려준다.

    JS 의 for-in 순서(정수 키 오름차순)대로 넣으므로, 겹치는 단어는 높은 레벨이 남는다(english-words.js:268-269).
    """
    with open(path, encoding="utf-8") as f:
        content = f.read()
    body = content[content.find("const englishWords"):] if "const englishWords" in content else content
    levels = re.findall(r'^[ \t]*(\d+):[ \t]*"([^"]*)"', body, re.M)
    words = {}
    for level, joined in sorted(levels, key=lambda item: int(item[0])):
        for word in joined.split(" "):
            words[word] = int(level)
    return words


# ════════════════════════════════════════════════════════════════════
# 공개 함수
# ════════════════════════════════════════════════════════════════════

def split_for_reading(source_text, lang, voice_lang=None, words=None):
    """원문 → 읽을 조각 목록 [{"text", "src_start", "src_end"}].

    text: 음성에 보낼 글(읽기용 변환 뒤). src_start/src_end: 원문 기준 반열린 구간.
    원문에 맞추지 못하면 src_start/src_end 가 None 이다(확장처럼 형광펜만 포기하고 읽기는 계속).
    lang: 조각 나누기 규칙용 언어(확장 options.lang). voice_lang: 읽기용 변환용 음성 언어(없으면 lang).
    words: 영어 단어 목록(load_english_words). 없으면 영어 단어 규칙이 꺼진다.
    """
    if not source_text:
        return []
    segments = build_segments(source_text, lang)
    try:
        alignment = align_segments_to_source(source_text, segments)
    except Exception:  # page-ui-host.js:317-324 — 맞추다 실패해도 읽기는 계속
        alignment = None
    spoken_lang = voice_lang or lang
    result = []
    for i, seg in enumerate(segments):
        span = alignment.segment_range(i) if alignment is not None else None
        result.append({
            "text": spoken_text(seg, spoken_lang, words).text,
            "src_start": span[0] if span else None,
            "src_end": span[1] if span else None,
        })
    return result
