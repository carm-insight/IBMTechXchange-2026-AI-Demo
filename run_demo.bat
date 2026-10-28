@echo off
REM IBM watsonx Governed Agent Demo launcher
cd /d "%~dp0"
title IBM watsonx Governed Agent Demo

REM Use the Intel Arc iGPU through Ollama's Vulkan backend (about 1.5-2x faster than CPU on this laptop)
set OLLAMA_VULKAN=1
set OLLAMA_IGPU_ENABLE=1

REM Start Ollama if it is not already answering
curl -s http://localhost:11434/api/version >nul 2>&1
if errorlevel 1 (
  echo Starting Ollama...
  if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    start "" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
  ) else (
    start "" /min ollama serve
  )
  timeout /t 4 /nobreak >nul
)

echo Launching demo at http://localhost:8501 ...
python -m streamlit run app.py
