import csv
import importlib.util
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'Wampir66_Monitor_Plus.py'


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        source = Path(self.tmp.name) / SOURCE.name
        source.write_bytes(SOURCE.read_bytes())
        spec = importlib.util.spec_from_file_location('monitor_test', source)
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)

    def test_currencies_and_number_formats(self):
        cases = [('20,50 zł', 'PLN', 20.5), ('pln 1 234,56', 'PLN', 1234.56),
                 ('$12.50', 'USD', 12.5), ('EUR 1.234,56', 'EUR', 1234.56),
                 ('1,234.56 USD', 'USD', 1234.56), ('GBP 10', 'GBP', 10),
                 ('1\u00a0250 CZK', 'CZK', 1250), ('HUF 1,000', 'HUF', 1000),
                 ('brak kwoty', '', None), ('0 zł', 'PLN', 0)]
        for text, cur, value in cases:
            with self.subTest(text=text):
                self.assertEqual(self.app.parse_money(text)[1:], (cur, value))

    def test_donor_case_insensitive(self):
        self.assertEqual(self.app.donor_guess(['SUPER CHAT', 'Jan 20 PLN'], '20 pln'), 'Jan')

    def test_reports_with_events_and_empty_session(self):
        for events in ([], [('Jan', 25, 'PLN'), ('Jan', 5, 'PLN'), ('Anna', 10, 'EUR')]):
            db = self.app.connect()
            try:
                sid = db.execute('INSERT INTO sessions(label,started_at) VALUES(?,?)', ('Test', self.app.nowstr())).lastrowid
                for i, (donor, value, cur) in enumerate(events):
                    db.execute('INSERT INTO events(session_id,detected_at,donor,amount_text,amount_value,currency,message,raw_text,fingerprint) VALUES(?,?,?,?,?,?,?,?,?)',
                               (sid, self.app.nowstr(), donor, str(value), value, cur, 'message', 'raw', f'{sid}:{i}'))
                db.commit()
            finally:
                db.close()
            path = self.app.App.make_session_report(None, sid)
            with path.open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.reader(f, delimiter=';'))
            self.assertEqual(len(rows), len(events)+1)
            self.assertTrue(all(len(row) == 6 for row in rows))
            txt = path.with_suffix('.txt').read_text(encoding='utf-8')
            if events:
                self.assertIn('PLN: 30.00', txt)
                self.assertIn('EUR: 10.00', txt)

    def test_worker_does_not_save_late_result_after_stop(self):
        import queue
        entered = threading.Event()
        release = threading.Event()
        worker = object.__new__(self.app.App)
        worker.stop_event = threading.Event()
        worker.updates = queue.Queue()
        def ocr(*args, **kwargs):
            entered.set()
            release.wait(3)
            return 'Jan 25 PLN'
        class Capture:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def grab(self, region):
                from types import SimpleNamespace
                return SimpleNamespace(size=(10, 10), rgb=b'\xff' * 300)
        with patch.object(self.app.mss, 'MSS', Capture), patch.object(self.app.pytesseract, 'image_to_string', ocr):
            thread = threading.Thread(target=worker.loop, args=(123, {}))
            thread.start()
            try:
                self.assertTrue(entered.wait(3))
                worker.stop_event.set()
            finally:
                release.set()
                thread.join(4)
            self.assertFalse(thread.is_alive())
        db = self.app.connect()
        try: self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
        finally: db.close()


if __name__ == '__main__':
    unittest.main()
