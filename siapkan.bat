@echo off
REM Menyiapkan lingkungan Python baru di folder ini (hanya perlu SEKALI, dan hanya bila tidak memakai venv proyek lama).
cd /d "%~dp0"
python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Selesai. Jalankan aplikasi dengan jalankan.bat
pause >nul
