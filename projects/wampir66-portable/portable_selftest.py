"""Functional checks shared by source runs and the bundled Windows executable."""
import csv
import json
from pathlib import Path
import sys
import traceback


def check(app):
    from PIL import Image, ImageDraw, ImageFont
    import mss
    import pytesseract

    cases = [('20,50 zł', 'PLN', 20.5), ('$12.50', 'USD', 12.5),
             ('1.234,56 EUR', 'EUR', 1234.56), ('GBP 10', 'GBP', 10),
             ('1 250 CZK', 'CZK', 1250), ('HUF 1,000', 'HUF', 1000)]
    for text, cur, value in cases:
        assert app.parse_money(text)[1:] == (cur, value), text
    assert {'pol', 'eng'} <= set(pytesseract.get_languages(config=''))
    image = Image.new('RGB', (800, 160), 'white')
    ImageDraw.Draw(image).text((20, 30), 'Jan 25.00 PLN', font=ImageFont.load_default(size=48), fill='black')
    raw = pytesseract.image_to_string(image, lang='pol+eng', config='--psm 6', timeout=20)
    assert app.parse_money(raw)[1:] == ('PLN', 25.0), raw
    gui = app.App()
    try:
        gui.update()
        with mss.MSS() as capture:
            assert capture.grab({'left': 0, 'top': 0, 'width': 200, 'height': 100}).size.width == 200
        db = app.connect()
        try:
            sid = db.execute('INSERT INTO sessions(label,started_at,status) VALUES(?,?,?)',
                             ('Self test', app.nowstr(), 'ZAKOŃCZONA')).lastrowid
            db.execute('INSERT INTO events(session_id,detected_at,donor,amount_text,amount_value,currency,message,raw_text,fingerprint) VALUES(?,?,?,?,?,?,?,?,?)',
                       (sid, app.nowstr(), 'Jan', '25 PLN', 25, 'PLN', 'Test', raw, 'selftest'))
            db.commit()
        finally:
            db.close()
        gui.refresh_all()
        assert len(gui.events.get_children()) == 1
        report = gui.make_session_report(sid)
        with report.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream, delimiter=';'))
        assert len(rows) == 2 and len(rows[0]) == len(rows[1]) == 6
        assert 'PLN: 25.00' in report.with_suffix('.txt').read_text(encoding='utf-8')
    finally:
        gui.destroy()
    return ['currency parsing', 'pol+eng OCR', 'GUI', 'screen capture', 'SQLite', 'CSV/TXT reports']


def run(argv, app):
    # File output also works in PyInstaller --windowed mode (no stdout).
    output = Path(argv[argv.index('--self-test') + 1]).resolve()
    try:
        result = {'ok': True, 'checks': check(app)}
        code = 0
    except Exception:
        result = {'ok': False, 'error': traceback.format_exc()}
        code = 1
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)
