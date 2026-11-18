@echo off
REM Menjalankan aplikasi Gudang Scanner.
REM Pemakaian biasa:      jalankan.bat
REM Memakai Python lain:  jalankan.bat "E:\jalur\ke\venv\Scripts\python.exe"   (mis. venv proyek lama, supaya tidak perlu memasang ulang paket)
cd /d "%~dp0"
set PY=python
if exist "venv\Scripts\python.exe" set PY=venv\Scripts\python.exe
if not "%~1"=="" set PY=%~1
"%PY%" app.py
echo.
echo Aplikasi berhenti. Tekan tombol apa saja untuk menutup.
pause >nul
