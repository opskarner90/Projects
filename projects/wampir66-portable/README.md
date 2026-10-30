# Wampir66 Monitor Portable

Aplikacja Python/Tkinter rozpoznaje widoczne alerty przez Tesseract OCR,
zapisuje sesje i zdarzenia w SQLite oraz tworzy raporty CSV i TXT.
OCR może pomylić lub pominąć kwoty i nicki; wyniki wymagają ręcznej kontroli
 i nie potwierdzają faktycznych płatności. Program nie pobiera historii YouTube.

## Windows 10/11 x64 — wersja portable

Gotowy plik powstaje dopiero po udanym buildzie na Windows. W środowisku
Codex/Linux sprawdzono kod i OCR, ale nie zbudowano jeszcze EXE dla Windows.

1. Wyślij tę gałąź do GitHub. Workflow `.github/workflows/build-windows.yml`
   uruchomi się po pushu na `wampir66-portable` lub `main`.
2. W Actions otwórz **Build Windows Portable EXE**. Po pomyślnym zakończeniu
   pobierz artefakt **Wampir66-Monitor-Portable-Windows**.
3. Rozpakuj go do folderu z prawem zapisu i uruchom
   `Wampir66_Monitor_Portable.exe` lub `URUCHOM.bat`.
4. Python i osobna instalacja Tesseract nie są potrzebne na komputerze docelowym.
   Dane są w `Dane/`, raporty w `Raporty/` obok EXE. Pierwszy start może potrwać.

Workflow instaluje Tesseract, dołącza modele pol/eng, testuje źródła,
buduje EXE i testuje **zbudowany EXE** z wyłączonym systemowym Tesseract w PATH.
Publikacja artefaktu wymaga przejścia testów. Wyniki są w artefakcie
`Windows-test-results`. SHA256 służy porównaniu pobranego pliku; aplikacja
nie jest podpisana certyfikatem wydawcy i Windows może wyświetlić SmartScreen.

## Budowanie lokalne na Windows

Zainstaluj Python 3.12 x64 i Tesseract OCR x64 (np. `choco install tesseract --yes`).
Uruchom `BUILD_EXE.bat` w katalogu aplikacji. Alternatywnie:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
# Gdy OCR zainstalowano gdzie indziej:
.\build-windows.ps1 -TesseractDir 'D:\Tesseract-OCR'
```

Skrypt tworzy `.venv-build`, pobiera modele z oficjalnego repozytorium,
dołącza silnik, modele i licencje, buduje jeden EXE oraz sprawdza go.
Wynik: `dist/Wampir66_Monitor_Portable.exe`. Nie wystarczy sama obecność pliku:
sprawdź pomyślny koniec skryptu i `exe-selftest.json` z `ok: true`.

## Codex / rozwój na Linux

Katalog: `/workspace/Projects/projects/wampir66-portable`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

GUI i testy funkcjonalne wymagają pulpitu lub Xvfb. W przygotowanym środowisku:

```bash
export PATH="/workspace/wampir66-tools/sysroot/usr/bin:$PATH"
export TESSDATA_PREFIX=/workspace/wampir66-tools/sysroot/usr/share/tesseract-ocr/5/tessdata
xvfb-run -a -s '-screen 0 1280x900x24 -nolisten tcp' .venv/bin/python -m unittest discover -s tests -v
xvfb-run -a -s '-screen 0 1280x900x24 -nolisten tcp' .venv/bin/python Wampir66_Monitor_Plus.py --self-test source-selftest.json
```

Test funkcjonalny korzysta z tymczasowej bazy i raportów. Sprawdza prawdziwy OCR
pol+eng, GUI, zrzut ekranu, SQLite i zawartość raportów. Bez pulpitu dwa testy
GUI są pomijane. Xvfb nie pokazuje ekranu ani transmisji użytkownika.
Do normalnego używania uruchom `.venv/bin/python Wampir66_Monitor_Plus.py`
na pulpicie z widoczną transmisją i wybierz obszar OCR.

## Naprawy

- Parsowanie walut i formatów kwot bez błędu wyrażenia regularnego.
- Raporty obejmują kwoty potrzebne do sumowania, zachowując sześć kolumn CSV.
- Osobne identyfikatory sesji w nazwach raportów zapobiegają nadpisaniu raportów różnych sesji.
- Wątek OCR nie wywołuje Tkintera; aktualizacje przechodzą przez kolejkę.
- Zakończenie sesji i raport następują po zakończeniu skanowania.
- Anulowanie zamykania pozostawia sesję aktywną; OCR ma limit czasu.
- Brakujące modele OCR są zgłaszane przed rozpoczęciem sesji.
- Launcher, lokalny build i workflow używają tej samej nazwy EXE.

Nie dodawaj do Git katalogów Dane, Raporty, vendor ani środowisk wirtualnych.
