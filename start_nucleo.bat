@echo off
rem Nucleo de D.A.R.K. con la conversacion en API primero (Groq) y el modelo
rem local de respaldo. Rutas relativas al .bat: funciona en cualquier PC.
cd /d "%~dp0dark_python"
rem El venv vive en la raiz del proyecto, no dentro de dark_python
call "%~dp0.venv\Scripts\activate.bat"
set DARK_LLM_PROVIDER=conmutado
python -m nucleo.dark_nucleo
