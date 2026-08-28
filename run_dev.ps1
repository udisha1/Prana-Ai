Write-Host "Starting PranaAI development environment..." -ForegroundColor Green

# Start the backend Flask server in a new window
Write-Host "Starting backend server (Flask) on http://127.0.0.1:5000 ..." -ForegroundColor Cyan
Start-Process cmd -ArgumentList "/k python api/agent.py"

# Start the frontend server (Vite) in a new window
Write-Host "Starting frontend server (Vite) on http://localhost:5173 ..." -ForegroundColor Cyan
Start-Process cmd -ArgumentList "/k cd frontend && npm run dev"

Write-Host "Both servers launched!" -ForegroundColor Green
