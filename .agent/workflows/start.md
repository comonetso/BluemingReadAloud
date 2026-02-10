---
description: 세션 시작 시 프로젝트 상태 점검 및 준비
---

# 여기엔 STT 타이퍼 - 세션 시작 워크플로우

- 에이전트는 첫 응답에 반드시 **"여기엔 STT 타이퍼 - (작업주제)"**를 머리말로 포함한다.

## 1. KI (Knowledge Items) 점검
세션 시작 시 제공된 KI 요약을 먼저 확인한다.
관련 KI가 있으면 아티팩트를 읽어서 기존 작업 맥락을 파악한다.

## 2. 프로젝트 문서 확인

### 필수 확인 문서
// turbo
```bash
cat AGENTS.md
```

### 최근 세션 로그 확인 (있다면)
// turbo
```bash
if (Test-Path docs/session_logs) { Get-ChildItem docs/session_logs -Name | Select-Object -Last 5 }
```

## 3. 프로젝트 상태 점검

### Git 상태 확인
// turbo
```bash
git status --short && git log -3 --oneline
```

### 실행 환경 확인 (최초 세션 시)
// turbo
```bash
py --version
```

## 4. 반드시 준수할 규칙

- 코드 수정 전 반드시 한글로 상세히 설명하고 사용자 동의를 받는다. 설명 없이 수정 절대 금지.
- 모든 문서, Plan, Todo, 설명은 한글로 친절하게 작성한다.
- 사용자 대면 메시지 추가 시 messages.py의 ko/en 양쪽에 동시 추가한다.
- 대규모 수정은 작은 단위로 나누어 단계별 진행 + 중간 커밋.
- 테스트 파일은 시스템 %TEMP% 에 작성하고 테스트 후 반드시 삭제한다.

## 5. 절대 하지 말아야 할 것

- 금지: API 키, 서비스 계정 JSON 경로를 코드에 하드코딩
- 금지: google_credentials.json, whisperer_settings.json을 Git에 커밋
- 금지: whisperer.py에 직접 한국어/영어 문자열 하드코딩 (messages.py 사용)
- 금지: 개발 중 PyInstaller 빌드 실행 (최종 마무리 시에만)
- 금지: recordings/, logs/ 폴더의 사용자 데이터 임의 삭제

## 6. 작업 준비 완료

사용자의 요청을 받을 준비가 되면:
- 프로젝트 컨텍스트 파악 완료
- 관련 규칙 숙지 완료
- 작업 진행 가능 상태

---

**참고:** 이 워크플로우는 `/start` 명령으로 실행한다.
