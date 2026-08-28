@echo off
echo Starting PranaAI development environment...

REM Start the backend Flask server in a new window
echo Starting backend server (Flask) on http://127.0.0.1:5000 ...
start cmd /k "python api/agent.py"

REM Start the frontend server (Vite) in a new window
echo Starting frontend server (Vite) on http://localhost:5173 ...
cd frontend
start cmd /k "npm run dev"

echo Both servers started!
pause
