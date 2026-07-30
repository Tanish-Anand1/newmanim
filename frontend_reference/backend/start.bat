@echo off
echo Starting Vivacity Backend...
echo.
echo Make sure you have set ANTHROPIC_API_KEY and OPENAI_API_KEY in .env
echo Backend will be available at: http://localhost:8000
echo.
cd /d "%~dp0"

REM Install dependencies if needed
pip install -r requirements.txt --quiet

REM Start the FastAPI server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
