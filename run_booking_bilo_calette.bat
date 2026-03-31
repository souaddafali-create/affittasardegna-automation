@echo off
REM ============================================================
REM  Lancia booking_uploader.py per BILO LE CALETTE (Palau)
REM  Esecuzione locale Windows — browser visibile
REM ============================================================

set BK_EMAIL=info@affittasardegna.it
set /p BK_PASSWORD="Inserisci la password di Booking.com: "
set PROPERTY_DATA=Bilo_Le_Calette_DATI.json
set INTERACTIVE=1

echo.
echo Avvio inserimento BILO LE CALETTE su Booking.com...
echo Il browser si aprira' visibile.
echo Se appare un CAPTCHA, risolvilo nel browser e premi INVIO nel terminale.
echo Se Booking chiede un codice email, inseriscilo qui quando richiesto.
echo.

python booking_uploader.py

echo.
echo Script terminato. Controlla la cartella screenshots_booking\ per le verifiche.
pause
