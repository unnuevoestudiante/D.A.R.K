@echo off
rem Rutas relativas al .bat: funciona en cualquier PC (antes apuntaba a C:\Users\samue\...)
cd /d "%~dp0dark_python"
rem El venv vive en la raiz del proyecto, no dentro de dark_python
call "%~dp0.venv\Scripts\activate.bat"
python -m modulos.hive.coordinador --host 0.0.0.0 --port 8766
