@echo off
echo Testing POST /tasks with enum as string...
curl -X POST http://localhost:5051/tasks -H "Content-Type: application/json" -d "{\"descripcion\":\"prueba diagnostico\",\"prioridad\":\"Alta\",\"modulo\":\"Nucleo\",\"pasos\":[]}" -v
echo.
echo Done.
pause