@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --windowed --onefile --name ViVi-Control ^
  --exclude-module numpy ^
  --exclude-module pygame ^
  --exclude-module scipy ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  --exclude-module IPython ^
  --exclude-module PyQt5 ^
  --exclude-module PySide6 ^
  --exclude-module cv2 ^
  --add-data "皮肤素材;皮肤素材" viviana_pet.py
echo.
echo Built: dist\ViVi-Control.exe
