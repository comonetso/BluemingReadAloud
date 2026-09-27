@echo off
title BluemingReadAloud 콘솔
chcp 65001
echo === BluemingReadAloud 콘솔 ===
echo 이 창을 닫아도 프로그램은 계속 실행됩니다.
echo.
echo 로그 출력을 시작합니다...
echo.
echo > whisperer_console.log
echo 키 입력 감지 및 읽기 상태를 모니터링합니다...
echo.
powershell -command "Get-Content -Path whisperer_console.log -Wait -Encoding UTF8"
