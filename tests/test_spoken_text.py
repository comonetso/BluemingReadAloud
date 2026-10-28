# -*- coding: utf-8 -*-
"""spoken_text.make_spoken_text 시험 — Paseo 상태바 플러그인 시험의 기대값을 그대로 옮겼다(2026-10-28).

기준 시험(같은 PC, claudeContextBar 저장소)
  docs/paseo-plugin-tools/tests-261013/test_spoken_symbols.cjs   — 글 다듬기 사례(화면 쪽 joinSplitParens 3건·무음 1건은 Paseo 전용이라 뺐다)
  docs/paseo-plugin-tools/tests-261026/spoken_version/test_spoken_version.mjs — 판 번호 10건
기준 쪽 기대값이 바뀌면 여기도 같은 값으로 바꾼다. 기대값을 이 앱 사정에 맞춰 고치지 않는다(세 곳이 같게 읽는 것이 목적).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spoken_text import make_spoken_text, korean_number, speech_lang  # noqa: E402


def none(*signs):
    return lambda s: all(x not in s for x in signs)


SYMBOL_CASES = [
    # 기호를 소리로 읽지 않는다
    ("글머리 점", "• 바뀐 곳 두 군데", "바뀐 곳 두 군데"),
    ("가운뎃점은 나열 쉼", "제목·표 머리", "제목, 표 머리"),
    ("영어 이름 안 점·밑줄", "readaloud_text.py 를 고쳤다", "readaloud text py 를 고쳤다"),
    ("영어 이름 안 하이픈", "claude-state-bar 폴더", "claude state bar 폴더"),
    ("한글 슬래시", "읽기/쓰기 권한", "읽기 쓰기 권한"),
    ("영문 슬래시", "ko/en 둘 다", "ko en 둘 다"),
    ("긴 대시는 쉼", "가 — 나", "가, 나"),
    ("띄어 쓴 하이픈은 쉼", "가 - 나", "가, 나"),
    ("화살표는 쉼", "최성주택 → 대성주택", "최성주택, 대성주택"),
    ("콜론은 쉼", "참고: 내용", "참고, 내용"),
    ("따옴표는 지움", "\"전무\" 계정", "전무 계정"),
    ("그림 문자는 지움", "✅ 제목 정상", "제목 정상"),
    ("그 밖의 기호", "a + b = c #1 @x & [y] {z} ~w", none("+", "=", "#", "@", "&", "[", "]", "{", "}", "~")),
    ("쩜·슬래시·대시 소리 없음", "src/a-b_c.ts 와 x.y/z", none("쩜", "슬래시", "대시", "언더바")),
    # 괄호 — 한글이 든 괄호는 읽고, 파일명이 들었거나 한글이 없는 괄호는 건너뛴다
    ("한글 괄호는 읽는다", "1명(이 계정) 입니다", "1명 이 계정 입니다"),
    ("겹친 한글 괄호", "가 (나 (다) 라) 마", "가 나 다 라 마"),
    ("전각 한글 괄호", "가（나）다", "가 나다"),
    ("한글 없는 괄호는 건너뜀", "3대(DB)는 서버(PC)", "3대는 서버"),
    ("파일명 괄호는 건너뜀", "문의문 파일(ANTHROPIC_SEAT_INQUIRY.md) 받은 답", "문의문 파일 받은 답"),
    ("파일명 섞인 한글 괄호도 건너뜀", "규칙 초안(docs/MESA.md 7번)을 고쳤다", "규칙 초안을 고쳤다"),
    ("파일명 없는 섞인 괄호는 읽는다", "남았습니다(계획표 W5).", "남았습니다 계획표 W5."),
    ("한글 사이 빗금은 경로가 아니다", "권한(읽기/쓰기) 확인", "권한 읽기 쓰기 확인"),
    ("숫자 점은 파일명이 아니다", "버전(5.5 판)을 쓴다", "버전 5.5 판을 쓴다"),
    ("괄호 뒤 조사", "서버 3대(DB·IVR)는 올렸다", "서버 3대는 올렸다"),
    ("괄호 뒤 영어", "load(x)name 함수", "load name 함수"),
    ("짝 없는 괄호는 기호만", "1) 첫째 2) 둘째", lambda s: ")" not in s and "첫째" in s and "둘째" in s),
    ("한글 괄호만 있으면 읽는다", "(참고)", "참고"),
    ("파일명 괄호만 있으면 빈 글", "(work-cli.mjs)", ""),
    ("괄호 안쪽에 줄바꿈이 낀 경로는 읽지 않는다", "하나는 서버 설정 파일(\n\n~/.claude/settings.json\n\n)에 넣어 둔 목록",
     "하나는 서버 설정 파일에 넣어 둔 목록"),
    ("괄호 안쪽 줄바꿈 — 한글 괄호는 그대로 읽는다", "허용(\n사람 확인\n)을 받았다", "허용 사람 확인을 받았다"),
    ("괄호로 끝난 줄 뒤 다른 문단은 먹지 않는다", "설명(\n\n다음 문단입니다.", "설명 다음 문단입니다."),
    # 숫자는 깨지지 않게
    ("소수점", "1.5배 빠름", "1.5배 빠름"),
    ("주소 번호는 그대로", "127.0.0.1:6800 과 0.11.1", "127.0.0.1:6800 과 영 점 십일 점 일"),
    # 날짜·시각·수식은 말로 — 한국어 음성만
    ("시각", "19:41:11에 저장", "십구시 사십일분 십일초에 저장"),
    ("시각 — 시계 숫자 그대로", "18:13:02 · 06:05:02 · 9:05", "십팔시 십삼분 공이초, 공육시 공오분 공이초, 구시 공오분"),
    ("시각 0분은 뺀다", "리셋 09:00 · 16:24 · 09:00:30", "리셋 공구시, 십육시 이십사분, 공구시 공공분 삼십초"),
    ("숫자 두 개 날짜", "리셋 10/14 09:00", "리셋 10월 14일 공구시"),
    ("월·일 범위 밖은 날짜 아님", "44/44 통과 · 13/20", "44 44 통과, 13 20"),
    ("연도 붙은 날짜", "2026-10-14 · 2026/10/14 · 2026.10.14.", "2026년 10월 14일, 2026년 10월 14일, 2026년 10월 14일."),
    ("ISO 시각", "2026-10-13T06:51:51Z 실패", "2026년 10월 13일 공육시 오십일분 오십일초 UTC 실패"),
    ("하이픈 범위는 '에서' · 연도 없는 하이픈 날짜", "3-5초 · 10-13 결정", "3에서 5초, 10월 13일 결정"),
    ("수식 더하기·곱하기", "1+1=2, 3×4=12, 3 * 4 = 12", "1 더하기 1은 2, 3 곱하기 4는 12, 3 곱하기 4는 12"),
    ("등호 식의 빼기·나누기", "10-3=7, 6/2=3", "10 빼기 3은 7, 6 나누기 2는 3"),
    ("등호 앞 받침", "5+5=10, 2*2=4, 7-2=5", "5 더하기 5는 10, 2 곱하기 2는 4, 7 빼기 2는 5"),
    ("플러스마이너스·등호 없는 더하기", "50% ± 5%, 2+3", "50% 플러스 마이너스 5%, 2 더하기 3"),
    ("등호 없는 빼기는 아님", "010-1234-5678", "010 1234 5678"),
    ("굵게 별표는 곱하기 아님", "**3**배", "3배"),
    ("영어 음성은 그대로", "saved at 19:41 on 10/14, 1+1=2", "saved at 19:41 on 10 14, 1 1 2", "en"),
    ("천 단위 쉼표는 수사로", "1,000명", "천명"),
    # 10-19 읽기 전수조사
    ("연도 없는 하이픈 날짜", "10-10 에 바꿨습니다", "10월 10일 에 바꿨습니다"),
    ("연도 날짜 뒤 콜론", "2026-10-10: 기록", "2026년 10월 10일, 기록"),
    ("쉼표 숫자 물결 범위", "54,926~80,055 줄", "오만 사천구백이십육에서 팔만 오십오 줄"),
    ("쉼표 숫자", "80,055 원", "팔만 오십오 원"),
    ("수사 — 만·억·소수", "1,000,000 · 10,000 · 100,000,000 · 635,055 · 1,234.56",
     "백만, 만, 일억, 육십삼만 오천오십오, 천이백삼십사 점 오육"),
    ("날짜 범위", "10-18~10-25 사이", "10월 18일에서 10월 25일 사이"),
    ("시각 범위", "15:39~15:45 동안", "십오시 삼십구분에서 십오시 사십오분 동안"),
    ("시각 범위 — 공으로 시작", "05:39~06:45 · 공간~공부", "공오시 삼십구분에서 공육시 사십오분, 공간 공부"),
    ("숫자·퍼센트·소수 범위", "4~5개 · 60~80% · 0.25~0.7초", "4에서 5개, 60에서 80%, 0.25에서 0.7초"),
    ("끝자리 x 시각", "18:4x · 04:0x 무렵", "십팔시 사십분쯤, 공사시쯤 무렵"),
    ("k·M 접미와 부호", "+45.6k -5 · 1.5M · 2K", "플러스 사만 오천육백 마이너스 5, 백오십만, 이천"),
    ("배속·배수", "1.3x · 4x 속도", "1.3배, 4배 속도"),
    ("단위", "35ms · 19MB · 30px · 5h · 1,024MB · 25°C", "35밀리초, 19메가바이트, 30픽셀, 5시간, 천이십사메가바이트, 25도"),
    ("단위 붙은 곱하기", "30초×60 · 25ms×40", "30초 곱하기 60, 25밀리초 곱하기 40"),
    ("부호 숫자", "+9 · -30 바뀜", "플러스 9, 마이너스 30 바뀜"),
    ("그대로 — 범위 밖 하이픈·16진수·주소 번호", "0-2 절 · 13-20 · 0x1F · 0.11.4 판 · 127.0.0.1:6800",
     "0 2 절, 13 20, 0x1F, 영 점 십일 점 사 판, 127.0.0.1:6800"),
    ("그대로 — 목록 글머리·숫자 없는 물결", "- 30개 목록 · 안녕~ 잘 지내", "30개 목록, 안녕 잘 지내"),
    ("영어 음성은 숫자 규칙을 안 탄다", "54,926~80,055 lines, 10-10, 1.3x", "54,926 80,055 lines, 10 10, 1.3x", "en"),
    ("퍼센트", "사용률 50%입니다.", "사용률 50%입니다."),
    ("영어 낱말 안 작은따옴표", "don't stop", "don't stop", "en"),
    ("일본어 문장 부호는 둔다", "こんにちは。この声で文章を読み上げます。", "こんにちは。この声で文章を読み上げます。", "ja"),
    ("중국어 문장 부호는 둔다", "您好，我会用这个声音朗读文字。", "您好，我会用这个声音朗读文字。", "zh"),
    ("아랍어 문장 부호는 둔다", "مرحبا، كيف حالك؟", "مرحبا، كيف حالك؟", "ar"),
    # 표 — 한 덩어리, 줄마다 머리글과 짝지어
    ("마크다운 표", "\n".join([
        "| 상담원 구분 | 관리 등급 | 인원 | 키워드 등록 결과 |",
        "|---|---|---|---|",
        "| 일반 직급 | 0 | 5명 | 승인 대기로 정상 저장 |",
        "| 일반 직급 | 9 | 1명(이 계정) | 바로 승인됨 |",
    ]), "일반 직급, 관리 등급 0, 인원 5명, 키워드 등록 결과 승인 대기로 정상 저장. "
        "일반 직급, 관리 등급 9, 인원 1명 이 계정, 키워드 등록 결과 바로 승인됨."),
    ("표 빈 칸은 뺀다", "| a | b | c |\n|:--|:-:|--:|\n| x |  | z |", "x, c z."),
    ("표 앞뒤 글은 그대로", "앞 글\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n뒤 글", "앞 글\n\n1, b 2.\n\n뒤 글"),
    ("구분줄 없는 | 는 표가 아니다", "a | b", "a b"),
    # 경로는 끝 이름, URL 은 "URL"
    ("윈도우 긴 경로", "F:\\workspace\\EtcProject\\src\\extension.ts 를 고쳤습니다", "extension ts 를 고쳤습니다"),
    ("서버 절대 경로", "/root/paseo-plugins/claude-rc-relay/relay.mjs", "relay mjs"),
    ("홈 경로", "~/.claude/settings.json 에 있습니다", "settings json 에 있습니다"),
    ("상대 경로 + 줄 번호", "src/extension.ts:120 에서", "extension ts, 120 에서"),
    ("슬래시 명령", "/start 를 다시 돌리세요", "start 를 다시 돌리세요"),
    ("https URL", "토론은 https://github.com/getpaseo/paseo/discussions/6141 에 있습니다", "토론은 URL 에 있습니다"),
    ("마크다운 링크는 글만", "[가이드](https://a.b/c) 를 보세요", "가이드 를 보세요"),
    ("영어 음성", "See src/extension.ts and https://x.y/z", "See extension ts and URL", "en"),
    ("대문자 두 글자는 떼지 않는다", "DB 서버 PC OK", "DB 서버 PC OK"),
    ("일반 문장", "안녕하세요. CPU 사용률이 50%입니다 → 다음 단계로 **넘어갑니다**.",
     "안녕하세요. CPU 사용률이 50%입니다, 다음 단계로 넘어갑니다."),
]

VERSION_CASES = [
    ("확장 v1.17.2 를 게시했습니다.", "확장 버전 일 점 십칠 점 이 를 게시했습니다."),
    ("codex-rescue 1.18.1 판입니다.", "codex rescue 일 점 십팔 점 일 판입니다."),
    ("Paseo 0.13.0 으로 올렸습니다.", "Paseo 영 점 십삼 점 영 으로 올렸습니다."),
    ("끝판은 v2.0.10.", "끝판은 버전 이 점 영 점 십."),
    ("V1.2.3 대문자", "버전 일 점 이 점 삼 대문자"),
    ("browser-check 0.2.2 게시", "browser check 영 점 이 점 이 게시"),
    ("소수 1.5 배", "소수 1.5 배"),
    ("주소 127.0.0.1:6800", "주소 127.0.0.1:6800"),
    ("날짜 2026.10.14 기록", "날짜 2026년 10월 14일 기록"),
    ("네 마디 1.17.2.3 은", "네 마디 1.17.2.3 은"),
]


class SpokenSymbolsTest(unittest.TestCase):
    def test_cases(self):
        for case in SYMBOL_CASES:
            name, text, want = case[0], case[1], case[2]
            lang = case[3] if len(case) > 3 else "ko"
            with self.subTest(name=name):
                got = make_spoken_text(text, lang)
                if callable(want):
                    self.assertTrue(want(got), f"{name}: {got!r}")
                else:
                    self.assertEqual(got, want, name)

    def test_case_count(self):
        # 기준 시험 test_spoken_symbols.cjs 의 check() 사례 수와 같아야 한다(빠뜨림 방지)
        self.assertEqual(len(SYMBOL_CASES), 86)


class SpokenVersionTest(unittest.TestCase):
    def test_cases(self):
        for text, want in VERSION_CASES:
            with self.subTest(text=text):
                self.assertEqual(make_spoken_text(text, "ko"), want)


class HelpersTest(unittest.TestCase):
    def test_korean_number(self):
        self.assertEqual(korean_number("80055"), "팔만 오십오")
        self.assertEqual(korean_number("10000"), "만")
        self.assertEqual(korean_number("100000000"), "일억")
        self.assertEqual(korean_number("0"), "영")

    def test_speech_lang(self):
        self.assertEqual(speech_lang("ko-KR"), "ko")
        self.assertEqual(speech_lang("en-US"), "en")
        self.assertEqual(speech_lang(""), "ko")


class ParagraphSplitTest(unittest.TestCase):
    """readaloud_text 의 문단 단위 나누기(2026-10-28) — 문단 = 빈 줄, 한 요청 2000바이트 이하(기준 tts.ts splitInput)."""

    def setUp(self):
        import readaloud_text
        self.rt = readaloud_text

    def test_paragraphs_by_blank_lines_keep_offsets(self):
        text = "  첫 문단\n같은 문단\n\n둘째\r\n \r\n셋째\r\r넷째  "
        spans = self.rt.split_paragraphs(text)
        self.assertEqual([text[s:e] for s, e in spans], ["첫 문단\n같은 문단", "둘째", "셋째", "넷째"])
        self.assertEqual(self.rt.split_paragraphs("\n\n  \n"), [])

    def test_split_input_sentence_boundaries(self):
        s = "가나다라" * 75 + "."                      # 901바이트, 같은 글자 반복 없음
        chunks = self.rt.split_input(" ".join([s] * 5), "ko-KR", "Chirp3-HD")
        self.assertEqual([c.count(".") for c in chunks], [2, 2, 1])
        self.assertTrue(all(len(c.encode("utf-8")) <= 2000 for c in chunks))
        self.assertEqual(self.rt.split_input("짧은 글.", "ko-KR", "Chirp3-HD"), ["짧은 글."])
        self.assertEqual(self.rt.split_input("줄 하나\n줄 둘", "ko-KR", "Chirp3-HD"), ["줄 하나 줄 둘"])

    def test_split_input_long_sentence_cut_at_space(self):
        words = " ".join(["낱말"] * 600)               # 마침표 없는 3599바이트
        chunks = self.rt.split_input(words, "ko-KR", "Chirp3-HD")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c.encode("utf-8")) <= 2000 and not c.endswith(" ") for c in chunks))
        self.assertEqual(" ".join(chunks).split(), ["낱말"] * 600)

    def test_reading_pieces_and_translation_paragraph(self):
        text = "한국어 문단입니다.\n\nRead https://example.com/secret now.\n\n(work-cli.mjs)\n\n끝."
        pieces = self.rt.split_paragraphs_for_reading(text, "ko-KR", "Chirp3-HD",
                                                      keep_whole=lambda raw: "Read" in raw)
        self.assertEqual([p["para"] for p in pieces], [0, 1, 2])      # 다듬어 빈 문단(파일명 괄호뿐)은 조각이 없다
        self.assertEqual(pieces[1]["raw"], "Read URL now.")            # 번역 회사로 주소가 나가지 않게
        self.assertNotIn("raw", pieces[0])
        self.assertEqual(text[pieces[2]["src_start"]:pieces[2]["src_end"]], "끝.")


if __name__ == "__main__":
    unittest.main()
