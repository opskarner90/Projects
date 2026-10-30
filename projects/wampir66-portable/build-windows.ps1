param([string]$TesseractDir = "$env:ProgramFiles\Tesseract-OCR")
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path "$TesseractDir\tesseract.exe")) {
    throw 'Zainstaluj Tesseract OCR x64, np. choco install tesseract --yes, albo podaj -TesseractDir.'
}
if (!(Test-Path '.venv-build\Scripts\python.exe')) {
    py -3.12 -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Wymagany Python 3.12 x64.' }
}
$python = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Instalacja zaleznosci nie powiodla sie.' }
& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Testy regresji nie przeszly.' }
New-Item -ItemType Directory -Force 'vendor\tesseract' | Out-Null
Copy-Item "$TesseractDir\*" 'vendor\tesseract' -Recurse -Force
foreach ($lang in @('pol','eng')) {
    Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/$lang.traineddata" -OutFile "vendor\tesseract\tessdata\$lang.traineddata"
    if ((Get-Item "vendor\tesseract\tessdata\$lang.traineddata").Length -lt 100000) { throw "Nieprawidlowy model: $lang" }
}
Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tesseract/5.5.0/LICENSE' -OutFile 'vendor\tesseract\LICENSE-Tesseract.txt'
Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/LICENSE' -OutFile 'vendor\tesseract\LICENSE-models.txt'
$env:TESSDATA_PREFIX = Join-Path $PSScriptRoot 'vendor\tesseract\tessdata'
$env:PATH = "$(Join-Path $PSScriptRoot 'vendor\tesseract');$env:PATH"
& $python Wampir66_Monitor_Plus.py --self-test source-selftest.json
if ($LASTEXITCODE -ne 0) { throw 'Test funkcjonalny zrodel nie przeszedl.' }
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name Wampir66_Monitor_Portable --add-data 'vendor\tesseract;tesseract' --add-binary 'vendor\tesseract\tesseract.exe;tesseract' Wampir66_Monitor_Plus.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller zakonczyl sie bledem.' }
$exe = Join-Path $PSScriptRoot 'dist\Wampir66_Monitor_Portable.exe'
if (!(Test-Path $exe)) { throw 'Brak pliku EXE.' }
# Avoid masking missing bundled files with the installed engine/models.
Remove-Item Env:TESSDATA_PREFIX -ErrorAction SilentlyContinue
$env:PATH = "$env:SystemRoot\system32;$env:SystemRoot"
$result = Join-Path $PSScriptRoot 'exe-selftest.json'
Remove-Item $result -ErrorAction SilentlyContinue
$process = Start-Process -FilePath $exe -ArgumentList @('--self-test', ('"' + $result + '"')) -Wait -PassThru
if ($process.ExitCode -ne 0 -or !(Test-Path $result)) { throw 'Test EXE nie przeszedl; sprawdz exe-selftest.json.' }
if (!(Get-Content $result -Raw | ConvertFrom-Json).ok) { throw 'Test EXE zglosil blad.' }
Copy-Item URUCHOM.bat, PORTABLE_INSTRUKCJA.txt -Destination dist
Get-FileHash $exe -Algorithm SHA256 | Format-List | Out-File dist\SHA256.txt
Write-Host "Gotowe i przetestowane: $exe"
