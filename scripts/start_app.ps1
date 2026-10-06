$ErrorActionPreference = 'Stop'
$taskProject = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskProject '.venv\Scripts\python.exe'
Set-Location -LiteralPath $taskProject
& $taskPython -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
