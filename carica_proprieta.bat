@echo off
REM ============================================================
REM  Carica proprieta' su CaseVacanza.it e Booking.com
REM  Da eseguire con doppio click su Windows
REM ============================================================
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM Usa la cartella dello script come cartella di lavoro
cd /d "%~dp0"

echo.
echo ============================================================
echo   CARICAMENTO PROPRIETA' SU CASEVACANZA E BOOKING
echo ============================================================
echo.

REM ---- 1) Controlli preliminari ----
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRORE] Python non trovato.
    echo          Installa Python da https://www.python.org/downloads/
    echo          e seleziona "Add Python to PATH" durante l'installazione.
    echo.
    pause
    exit /b 1
)

REM ---- 2) Credenziali ----
if not defined CASEVACANZA_EMAIL (
    set /p CASEVACANZA_EMAIL="Email CaseVacanza: "
)
if not defined CASEVACANZA_PASSWORD (
    set /p CASEVACANZA_PASSWORD="Password CaseVacanza: "
)
if not defined BK_EMAIL (
    set /p BK_EMAIL="Email Booking: "
)
if not defined BK_PASSWORD (
    set /p BK_PASSWORD="Password Booking: "
)

REM ---- 3) File JSON proprieta' ----
echo.
set /p JSONFILE="Inserisci il nome del file JSON (es. Bilo_Le_Calette_DATI.json): "
if "%JSONFILE%"=="" (
    echo [ERRORE] Nome file non inserito.
    pause
    exit /b 1
)
if not exist "%JSONFILE%" (
    echo [ERRORE] File non trovato: %JSONFILE%
    echo          Verifica il nome e che il file sia nella stessa cartella di questo .bat
    pause
    exit /b 1
)
set PROPERTY_DATA=%JSONFILE%

REM ---- 4) Chiede se la proprieta' e' gia' su Booking ----
echo.
echo La proprieta' e' gia' registrata su Booking.com?
echo   [S] Si' (salta il wizard di creazione, ti serve HOTEL_ID)
echo   [N] No (esegue il wizard completo su Booking)
set /p BK_ESISTENTE="Scelta [S/N]: "

set SKIP_WIZARD=
set HOTEL_ID=
if /I "%BK_ESISTENTE%"=="S" (
    set SKIP_WIZARD=1
    set /p HOTEL_ID="HOTEL_ID Booking (lascia vuoto se non lo sai): "
)
set INTERACTIVE=1

REM ---- 5) CaseVacanza ----
echo.
echo ------------------------------------------------------------
echo   1/2 - Caricamento su CaseVacanza.it
echo ------------------------------------------------------------
python casevacanza_uploader.py
set CV_EXIT=!ERRORLEVEL!
if !CV_EXIT! NEQ 0 (
    echo.
    echo [ATTENZIONE] CaseVacanza ha restituito errori ^(codice !CV_EXIT!^).
    echo              Controlla la cartella "screenshots" per i dettagli.
    echo.
    set /p CONT="Vuoi comunque proseguire con Booking? [S/N]: "
    if /I not "!CONT!"=="S" (
        echo Caricamento interrotto dall'utente.
        pause
        exit /b !CV_EXIT!
    )
)

REM ---- 6) Booking ----
echo.
echo ------------------------------------------------------------
echo   2/2 - Caricamento su Booking.com
echo ------------------------------------------------------------
python booking_uploader.py
set BK_EXIT=!ERRORLEVEL!
if !BK_EXIT! NEQ 0 (
    echo.
    echo [ATTENZIONE] Booking ha restituito errori ^(codice !BK_EXIT!^).
    echo              Controlla la cartella "screenshots_booking" per i dettagli.
    pause
    exit /b !BK_EXIT!
)

echo.
echo ============================================================
echo   ✅ Caricamento completato su entrambi i portali
echo ============================================================
echo.
echo Ricorda di fare una verifica finale sui portali prima
echo dell'invio definitivo della proprieta'.
echo.
pause
endlocal
exit /b 0
