@echo off
REM Atalho clicavel: grava e publica uma reuniao usando o venv do faster-whisper.
REM
REM O `pause` no fim existe por um motivo concreto: em 03/09/2026 o gravador
REM passou a morrer num AssertionError do soundcard (microfone USB cujo mix
REM format nao e EXTENSIVEL), e como a janela fechava sozinha, o sintoma que
REM chegava era "o botao nao funciona" - sem erro, sem log, sem nada.
REM Janela que fecha engolindo o traceback transforma bug em misterio.
cd /d "%~dp0"
"C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe" run.py
set CODIGO=%ERRORLEVEL%

if %CODIGO% NEQ 0 (
  echo.
  echo ============================================================
  echo   A GRAVACAO FALHOU  ^(codigo %CODIGO%^)
  echo   O erro esta logo acima. Copie e mande para o Claude.
  echo ============================================================
  echo.
  pause
)
