#!/bin/bash

# Port cleanup
echo "Cleaning up existing processes..."
lsof -ti :8000,3000 | xargs kill -9 2>/dev/null

# Start Backend
echo "Starting Backend Studio..."
cd backend && ./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload &

# Start Frontend
echo "Starting Frontend Dashboard..."
cd frontend && export PATH=/usr/local/bin:$PATH && npm run dev -- -p 3000
