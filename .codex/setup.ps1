$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if ((Test-Path requirements.txt) -or (Test-Path pyproject.toml)) {
  if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv .venv } else { python -m venv .venv }
  $python = '.venv\Scripts\python.exe'
  & $python -m pip install --upgrade pip
  if (Test-Path requirements.txt) { & $python -m pip install -r requirements.txt }
  if (Test-Path pyproject.toml) { & $python -m pip install -e . }
  if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
}
if (Test-Path package.json) {
  if (Test-Path package-lock.json) { npm ci } else { npm install }
  if ($LASTEXITCODE -ne 0) { throw 'npm dependency installation failed' }
}
Write-Host 'Codex environment setup complete'
