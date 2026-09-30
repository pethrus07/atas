@echo off
REM Atas - abre a janela de gravacao (app.py) com o venv do faster-whisper.
REM
REM O console fica aberto atras da janela (minimizado) de proposito: se o Python
REM morrer antes de a janela subir, o traceback aparece aqui e o `pause` segura.
REM Em 03/09/2026 o gravador morria num AssertionError do soundcard e a janela
REM fechava sozinha - o sintoma que chegava era "o botao nao funciona".
REM Janela que fecha engolindo o traceback transforma bug em misterio.
REM
REM Plano B sem janela:  python atas.py gravar
cd /d "%~dp0"
"C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe" app.py
set CODIGO=%ERRORLEVEL%

if %CODIGO% NEQ 0 (
  echo.
  echo ============================================================
  echo   O ATAS FECHOU COM ERRO  ^(codigo %CODIGO%^)
  echo   O erro esta logo acima e em local\atas.log.
  echo   A gravacao, se havia, esta salva: abra o Atas de novo e
  echo   ele oferece gerar a ata com o que foi gravado.
  echo ============================================================
  echo.
  pause
)
