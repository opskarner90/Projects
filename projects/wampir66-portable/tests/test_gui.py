import os
import sys
import time
import unittest
from unittest.mock import patch

import test_monitor


@unittest.skipUnless(os.environ.get('DISPLAY') or sys.platform == 'win32', 'Requires a desktop or Xvfb')
class SessionTests(unittest.TestCase):
    def setUp(self):
        fixture = test_monitor.MonitorTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.app = fixture.app
        self.gui = self.app.App()
        self.addCleanup(self.gui.destroy)

    def test_cancel_close_keeps_active_session(self):
        self.gui.active_session = 123
        with patch.object(self.app.messagebox, 'askyesno', return_value=False):
            self.gui.close()
        self.assertTrue(self.gui.winfo_exists())
        self.assertFalse(self.gui.stop_event.is_set())

    def test_stop_waits_for_worker_before_finishing_session(self):
        import threading
        release = threading.Event()
        def worker(*args): release.wait(3)
        self.app.CFG['region'] = {'left': 0, 'top': 0, 'width': 200, 'height': 100}
        with patch.object(self.gui, 'loop', worker), patch.object(self.app.pytesseract, 'get_languages', return_value=['pol', 'eng']):
            self.gui.start()
        sid = self.gui.active_session
        self.gui.stop()
        self.assertEqual(self.gui.active_session, sid)
        self.gui.start()  # A new session must not start while the old thread exits.
        self.assertEqual(self.gui.active_session, sid)
        release.set()
        deadline = time.monotonic() + 5
        while self.gui.active_session is not None and time.monotonic() < deadline:
            self.gui.update()
            time.sleep(.02)
        self.assertIsNone(self.gui.active_session)
        db = self.app.connect()
        try:
            self.assertEqual(db.execute('SELECT status FROM sessions WHERE id=?', (sid,)).fetchone()[0], 'ZAKOŃCZONA')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 1)
        finally: db.close()
        self.assertEqual(len(list(self.app.REPORTS.glob('*.txt'))), 1)
