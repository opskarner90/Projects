import os, re, sys, csv, json, time, sqlite3, threading, hashlib, subprocess, queue, math
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import mss
    from PIL import Image, ImageOps, ImageEnhance
    import pytesseract
except ImportError as e:
    raise SystemExit("Brakuje bibliotek. Zobacz INSTRUKCJA.txt.\n" + str(e))

APP = "Wampir66 Monitor Portable"
# PyInstaller extracts bundled OCR assets to _MEIPASS at launch.
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BUNDLED_TESS = BUNDLE / "tesseract" / "tesseract.exe"
if BUNDLED_TESS.is_file():
    pytesseract.pytesseract.tesseract_cmd = str(BUNDLED_TESS)
    os.environ["TESSDATA_PREFIX"] = str(BUNDLE / "tesseract" / "tessdata")

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
# Self-test uses isolated storage; normal portable data stays beside the EXE.
if "--self-test" in sys.argv:
    import tempfile
    _test_storage = tempfile.TemporaryDirectory(prefix="wampir66-selftest-")
    ROOT = Path(_test_storage.name)
DATA = ROOT / "Dane"
REPORTS = ROOT / "Raporty"
DATA.mkdir(exist_ok=True); REPORTS.mkdir(exist_ok=True)
DBFILE = DATA / "monitor.sqlite3"
CFGFILE = DATA / "ustawienia.json"
DEFAULT = {"region": None, "interval": 1.5, "tesseract": "", "language": "pol+eng",
           "duplicate_seconds": 150, "inactivity_minutes": 0}
try: CFG = {**DEFAULT, **json.loads(CFGFILE.read_text(encoding="utf-8"))}
except Exception: CFG = DEFAULT.copy()

CURRENCY_PATTERNS = [
    ("PLN", r"(?:PLN|zł|zl)"),
    ("USD", r"(?:USD|\$)"),
    ("EUR", r"(?:EUR|€)"),
    ("GBP", r"(?:GBP|£)"),
    ("CZK", r"CZK"),
    ("HUF", r"HUF"),
]
def nowstr(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def save_cfg(): CFGFILE.write_text(json.dumps(CFG, ensure_ascii=False, indent=2), encoding="utf-8")
def connect():
    c = sqlite3.connect(DBFILE, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL,
        started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL DEFAULT 'ACTIVE')""")
    c.execute("""CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER,
        detected_at TEXT NOT NULL, donor TEXT, amount_text TEXT, amount_value REAL,
        currency TEXT, message TEXT, raw_text TEXT, fingerprint TEXT UNIQUE,
        FOREIGN KEY(session_id) REFERENCES sessions(id))""")
    c.commit()
    return c

def parse_money(text):
    # Find amount + currency in either order; return only visible, OCR-derived information.
    number = r"([0-9]+(?:[ \u00a0][0-9]{3})*(?:[.,][0-9]+)*)"
    for cur, token in CURRENCY_PATTERNS:
        patterns = [token + r"\s*" + number, number + r"\s*" + token]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                num = m.group(1).strip().replace(" ", "").replace("\u00a0", "")
                if "," in num and "." in num:
                    if num.rfind(",") > num.rfind("."): num = num.replace(".","").replace(",",".")
                    else: num = num.replace(",","")
                elif "," in num or "." in num:
                    sep = "," if "," in num else "."
                    parts = num.split(sep)
                    if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
                        num = "".join(parts)
                    else:
                        num = num.replace(sep, ".")
                try: val = float(num)
                except ValueError: val = None
                return m.group(0).strip(), cur, val
    return "", "", None

def clean_lines(raw):
    return [re.sub(r"\s+", " ", x).strip(" |:;,.") for x in raw.splitlines() if x.strip()]

def donor_guess(lines, amount_text):
    # Heuristic only: OCR layout varies by browser/theme/overlay.
    skip = re.compile(r"super\s*chat|super\s*sticker|super\s*thanks|dziękuj|dołączył|subskryb|wampir66|youtube|złoty|cel\s:", re.IGNORECASE)
    for line in lines:
        if amount_text and amount_text.lower() in line.lower():
            line = re.sub(re.escape(amount_text), " ", line, flags=re.IGNORECASE)
        line = re.sub(r"\s+", " ", line).strip(" |:;,.")
        if not line or skip.search(line) or len(line) > 42: continue
        if re.search(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", line) and not re.fullmatch(r"[\W\d_]+", line):
            # Avoid interpreting a sentence as a name.
            if len(line.split()) <= 4: return line
    return "Nie rozpoznano"

def make_fingerprint(donor, amount, currency, message):
    s = re.sub(r"\s+", " ", f"{donor}|{amount}|{currency}|{message}".lower()).strip()
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def open_path(path):
    try:
        if sys.platform == "win32": os.startfile(str(path))
        elif sys.platform == "darwin": subprocess.Popen(["open", str(path)])
        else: subprocess.Popen(["xdg-open", str(path)])
    except Exception as e: messagebox.showerror(APP, str(e))

class SelectRegion(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master); self.cb=callback; self.attributes("-fullscreen",True)
        self.attributes("-alpha",0.28); self.configure(bg="black")
        self.cv=tk.Canvas(self,bg="black",cursor="cross",highlightthickness=0); self.cv.pack(fill="both",expand=True)
        self.cv.create_text(25,25,anchor="nw",fill="white",
            text="Przeciągnij prostokąt wokół alertów / czatu z wpłatami. ESC — anuluj",
            font=("Segoe UI",16,"bold"))
        self.start=None; self.rect=None
        self.cv.bind("<ButtonPress-1>",self.down); self.cv.bind("<B1-Motion>",self.move); self.cv.bind("<ButtonRelease-1>",self.up)
        self.bind("<Escape>",lambda e:self.destroy()); self.grab_set()
    def down(self,e):
        self.start=(e.x_root,e.y_root); self.rect=self.cv.create_rectangle(e.x,e.y,e.x,e.y,outline="yellow",width=3)
    def move(self,e):
        if self.start and self.rect:
            x,y=self.start; self.cv.coords(self.rect,x-self.winfo_rootx(),y-self.winfo_rooty(),e.x,e.y)
    def up(self,e):
        if self.start:
            x,y=self.start; x2,y2=e.x_root,e.y_root
            r={"left":min(x,x2),"top":min(y,y2),"width":abs(x2-x),"height":abs(y2-y)}
            if r["width"]>40 and r["height"]>25: self.cb(r)
            self.destroy()

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP); self.geometry("1120x760"); self.minsize(900,620)
        self.stop_event=threading.Event(); self.active_session=None; self.worker=None
        self.updates=queue.Queue(); self.stopping=False; self.closing=False
        self.label=tk.StringVar(value="Wampir66 LIVE"); self.interval=tk.StringVar(value=str(CFG["interval"]))
        self.status=tk.StringVar(value="Gotowy — otwórz LIVE i wybierz obszar wpłat.")
        self.region_text=tk.StringVar(value=self.region_label())
        self._style(); self._ui()
        if CFG.get("tesseract") and not BUNDLED_TESS.is_file(): pytesseract.pytesseract.tesseract_cmd=CFG["tesseract"]
        self.refresh_all()
        self.after(100, self._poll_worker)
    def _style(self):
        s=ttk.Style(self)
        try:s.theme_use("clam")
        except:pass
    def _ui(self):
        head=ttk.Frame(self,padding=12);head.pack(fill="x")
        ttk.Label(head,text="WAMPIR66 MONITOR PLUS",font=("Segoe UI",19,"bold")).pack(side="left")
        ttk.Label(head,text="OCR • raporty LIVE • ranking",foreground="#357").pack(side="left",padx=16)
        box=ttk.LabelFrame(self,text="Sesja i monitorowanie",padding=10);box.pack(fill="x",padx=12,pady=5)
        ttk.Label(box,text="Nazwa transmisji").grid(row=0,column=0,sticky="w")
        ttk.Entry(box,textvariable=self.label,width=32).grid(row=0,column=1,padx=6)
        ttk.Label(box,text="Interwał (sek.)").grid(row=0,column=2,padx=(12,0))
        ttk.Entry(box,textvariable=self.interval,width=7).grid(row=0,column=3,padx=6)
        ttk.Button(box,text="Zaznacz obszar OCR",command=self.pick).grid(row=0,column=4,padx=6)
        ttk.Label(box,textvariable=self.region_text).grid(row=1,column=0,columnspan=4,sticky="w",pady=(8,0))
        self.start_btn=ttk.Button(box,text="▶ Rozpocznij LIVE",command=self.start);self.start_btn.grid(row=1,column=4,pady=(8,0))
        self.stop_btn=ttk.Button(box,text="■ Zakończ LIVE i zapisz raport",command=self.stop,state="disabled");self.stop_btn.grid(row=1,column=5,padx=6,pady=(8,0))
        ttk.Label(self,textvariable=self.status,padding=(14,8),foreground="#17633b").pack(fill="x")
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill="both",expand=True,padx=12,pady=6)
        self.events_tab=ttk.Frame(self.tabs,padding=8);self.tabs.add(self.events_tab,text="Wykryte wpłaty")
        self.summary_tab=ttk.Frame(self.tabs,padding=8);self.tabs.add(self.summary_tab,text="Podsumowanie sesji")
        self.rank_tab=ttk.Frame(self.tabs,padding=8);self.tabs.add(self.rank_tab,text="Ranking wpłacających")
        self.history_tab=ttk.Frame(self.tabs,padding=8);self.tabs.add(self.history_tab,text="Historia transmisji")
        cols=("time","donor","amount","currency","message")
        self.events=ttk.Treeview(self.events_tab,columns=cols,show="headings")
        for c,t,w in [("time","Wykryto",150),("donor","Nadawca (OCR)",160),("amount","Kwota",100),("currency","Waluta",80),("message","Widoczny tekst OCR",500)]:
            self.events.heading(c,text=t);self.events.column(c,width=w)
        self.events.pack(fill="both",expand=True)
        self.events.bind("<Double-1>",self.show_event)
        self.summary_text=tk.Text(self.summary_tab,wrap="word",height=18);self.summary_text.pack(fill="both",expand=True)
        self.rank=ttk.Treeview(self.rank_tab,columns=("donor","currency","total","count"),show="headings")
        for c,t,w in [("donor","Nadawca",250),("currency","Waluta",100),("total","Suma rozpoznanych kwot",200),("count","Liczba wykryć",150)]:
            self.rank.heading(c,text=t);self.rank.column(c,width=w)
        self.rank.pack(fill="both",expand=True)
        self.history=ttk.Treeview(self.history_tab,columns=("name","start","end","count","state"),show="headings")
        for c,t,w in [("name","Transmisja",260),("start","Początek sesji",170),("end","Koniec sesji",170),("count","Wykrycia",100),("state","Status",100)]:
            self.history.heading(c,text=t);self.history.column(c,width=w)
        self.history.pack(fill="both",expand=True)
        foot=ttk.Frame(self,padding=12);foot.pack(fill="x")
        ttk.Button(foot,text="Eksportuj historię CSV",command=self.export_all).pack(side="left")
        ttk.Button(foot,text="Otwórz folder raportów",command=lambda:open_path(REPORTS)).pack(side="left",padx=8)
        ttk.Button(foot,text="Ustaw Tesseract OCR",command=self.set_tess).pack(side="left",padx=8)
        ttk.Label(self,text="OCR może błędnie odczytać kwotę lub nick. Wyniki należy zweryfikować; wykrycie nie jest potwierdzeniem płatności.",
                  foreground="#8a4b00",padding=(14,0,14,10)).pack(anchor="w")
    def region_label(self):
        r=CFG.get("region")
        return "Nie wybrano obszaru OCR." if not r else f"Obszar: {r['width']}×{r['height']} px • x={r['left']} y={r['top']}"
    def pick(self):
        self.iconify();self.after(450,lambda:SelectRegion(self,self.set_region))
    def set_region(self,r):
        CFG["region"]=r;save_cfg();self.region_text.set(self.region_label());self.deiconify()
    def set_tess(self):
        p=filedialog.askopenfilename(title="Wybierz tesseract.exe",filetypes=[("Tesseract","tesseract.exe"),("EXE","*.exe")])
        if p:
            CFG["tesseract"]=p;save_cfg();pytesseract.pytesseract.tesseract_cmd=p
            messagebox.showinfo(APP,"Zapisano ścieżkę do Tesseract.")
    def start(self):
        if self.active_session is not None or (self.worker and self.worker.is_alive()): return
        if not CFG.get("region"):messagebox.showwarning(APP,"Najpierw zaznacz obszar OCR.");return
        try:iv=max(0.8,float(self.interval.get().replace(",",".")))
        except (ValueError, OverflowError):messagebox.showerror(APP,"Nieprawidłowy interwał.");return
        if not math.isfinite(float(self.interval.get().replace(",", "."))):
            messagebox.showerror(APP,"Interwał musi być skończoną liczbą.");return
        try:
            languages = pytesseract.get_languages(config="")
            missing = set(CFG["language"].split("+")) - set(languages)
            if missing: raise RuntimeError("Brak modeli OCR: " + ", ".join(sorted(missing)))
        except Exception as error:
            messagebox.showerror(APP, "Nie można uruchomić OCR: " + str(error));return
        CFG["interval"]=iv;save_cfg()
        c=connect();cur=c.execute("INSERT INTO sessions(label,started_at,status) VALUES(?,?,?)",(self.label.get().strip() or "Wampir66 LIVE",nowstr(),"ACTIVE"))
        self.active_session=cur.lastrowid;c.commit();c.close()
        self.stop_event.clear();self.start_btn.config(state="disabled");self.stop_btn.config(state="normal")
        self.status.set("Trwa obserwacja. Nie minimalizuj okna transmisji; alert musi być widoczny.")
        self.worker=threading.Thread(target=self.loop,args=(self.active_session, dict(CFG["region"])),daemon=True);self.worker.start();self.refresh_all()
    def loop(self, session_id, r):
        last={}
        while not self.stop_event.is_set():
            try:
                with mss.MSS() as s:
                    shot=s.grab(r);im=Image.frombytes("RGB",shot.size,shot.rgb)
                im=ImageOps.grayscale(im);im=ImageEnhance.Contrast(im).enhance(2.1)
                im=im.resize((im.width*2,im.height*2))
                raw=pytesseract.image_to_string(im,lang=CFG["language"],config="--psm 6",timeout=15)
                if self.stop_event.is_set(): break
                lines=clean_lines(raw);amt,cur,val=parse_money(raw)
                if amt:
                    donor=donor_guess(lines,amt);msg=" | ".join(lines[:7])[:700]
                    fp=make_fingerprint(donor,amt,cur,msg)
                    # A persistent UNIQUE fingerprint must not suppress a legitimate
                    # repeat donation in a later session or later time window.
                    persistent_fp = f"{session_id}:{fp}:{int(time.time() // max(1, CFG['duplicate_seconds']))}"
                    if fp not in last or time.time()-last[fp]>CFG["duplicate_seconds"]:
                        last[fp]=time.time();c=connect()
                        try:
                            c.execute("""INSERT OR IGNORE INTO events(session_id,detected_at,donor,amount_text,amount_value,currency,message,raw_text,fingerprint)
                            VALUES(?,?,?,?,?,?,?,?,?)""",(session_id,nowstr(),donor,amt,val,cur,msg,raw,persistent_fp));c.commit()
                        finally:c.close()
                        self.updates.put(("refresh", None))
                self.updates.put(("status", "OCR aktywny • ostatni skan " + datetime.now().strftime("%H:%M:%S")))
            except Exception as e:self.updates.put(("status", "Błąd OCR: " + str(e)[:200]))
            self.stop_event.wait(CFG["interval"])
    def _poll_worker(self):
        while True:
            try: kind, value = self.updates.get_nowait()
            except queue.Empty: break
            if kind == "refresh": self.refresh_all()
            elif not self.stopping: self.status.set(value)
        if self.stopping and (not self.worker or not self.worker.is_alive()):
            self._finished()
            if self.closing: return
        if self.winfo_exists(): self.after(100, self._poll_worker)
    def stop(self):
        if self.active_session is None or self.stopping: return
        self.stopping=True; self.stop_event.set()
        self.stop_btn.config(state="disabled")
        self.status.set("Kończenie skanowania i zapisywanie raportu…")
    def _finished(self):
        sid=self.active_session
        if sid is None: return
        c=connect()
        try:
            c.execute("UPDATE sessions SET ended_at=?,status='ZAKOŃCZONA' WHERE id=?",(nowstr(),sid));c.commit()
        finally: c.close()
        self.active_session=None; self.stopping=False; self.worker=None
        try:
            path=self.make_session_report(sid)
            self.status.set("Sesja zakończona. Raport zapisano: "+str(path))
        except Exception as error:
            self.status.set("Dane sesji zachowano w bazie. Błąd raportu: " + str(error))
            messagebox.showerror(APP, self.status.get())
        self.start_btn.config(state="normal");self.stop_btn.config(state="disabled")
        self.refresh_all()
        if self.closing: self.destroy()
    def make_session_report(self,sid):
        c=connect();s=c.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()
        rows=c.execute("SELECT detected_at,donor,amount_text,currency,message,raw_text,amount_value FROM events WHERE session_id=? ORDER BY id",(sid,)).fetchall();c.close()
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
        safe=re.sub(r"[^A-Za-z0-9_-]+","_",s["label"])[:35] or "LIVE"
        path=REPORTS/f"{safe}_{sid}_{stamp}.csv"
        with path.open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f,delimiter=";");w.writerow(["Czas wykrycia","Nadawca OCR","Kwota","Waluta","Tekst OCR","Surowy OCR"])
            for x in rows:w.writerow(list(x)[:6])
        # Human-readable summary, totals are separated by currency.
        sums={}
        for x in rows:
            if x["amount_value"] is not None and x["currency"]:
                sums[x["currency"]]=sums.get(x["currency"],0)+x["amount_value"]
        txt=path.with_suffix(".txt")
        with txt.open("w",encoding="utf-8") as f:
            f.write(f"RAPORT SESJI: {s['label']}\nStart: {s['started_at']}\nKoniec: {s['ended_at'] or nowstr()}\nWykryte zdarzenia: {len(rows)}\n\n")
            f.write("Sumy rozpoznane przez OCR (nie są potwierdzeniem płatności):\n")
            for k,v in sorted(sums.items()):f.write(f"{k}: {v:.2f}\n")
            f.write("\nRanking OCR:\n")
            ranking={}
            for x in rows:
                if x["amount_value"] is not None and x["currency"]:
                    key=(x["donor"],x["currency"]);ranking[key]=ranking.get(key,0)+x["amount_value"]
            for (d,k),v in sorted(ranking.items(),key=lambda z:z[1],reverse=True)[:10]:f.write(f"{d} — {v:.2f} {k}\n")
            f.write("\nUwaga: automatyczne odczyty OCR mogą zawierać błędy.\n")
        return path
    def show_event(self,event):
        sel=self.events.selection()
        if not sel:return
        vals=self.events.item(sel[0],"values")
        messagebox.showinfo("Szczegóły wykrycia","\n".join(str(x) for x in vals))
    def refresh_all(self):
        c=connect()
        for tree in (self.events,self.rank,self.history):
            for i in tree.get_children():tree.delete(i)
        rows=c.execute("SELECT detected_at,donor,amount_text,currency,message FROM events ORDER BY id DESC LIMIT 500").fetchall()
        for r in rows:self.events.insert("","end",values=tuple(r))
        ranks=c.execute("""SELECT donor,currency,SUM(amount_value),COUNT(*) FROM events
            WHERE amount_value IS NOT NULL GROUP BY donor,currency ORDER BY SUM(amount_value) DESC""").fetchall()
        for r in ranks:self.rank.insert("","end",values=(r[0],r[1],f"{r[2]:.2f}",r[3]))
        hist=c.execute("""SELECT s.id,s.label,s.started_at,s.ended_at,s.status,COUNT(e.id)
            FROM sessions s LEFT JOIN events e ON e.session_id=s.id GROUP BY s.id ORDER BY s.id DESC""").fetchall()
        for r in hist:self.history.insert("","end",values=(r[1],r[2],r[3] or "—",r[5],r[4]))
        self.summary_text.delete("1.0","end")
        if self.active_session:
            ss=c.execute("SELECT * FROM sessions WHERE id=?",(self.active_session,)).fetchone()
            rr=c.execute("SELECT COUNT(*),COUNT(DISTINCT donor) FROM events WHERE session_id=?",(self.active_session,)).fetchone()
            self.summary_text.insert("end",f"AKTYWNA SESJA: {ss['label']}\nRozpoczęto: {ss['started_at']}\nWykryte zdarzenia: {rr[0]}\nRóżni nadawcy rozpoznani przez OCR: {rr[1]}\n\nPo kliknięciu „Zakończ LIVE” program zapisze raport CSV i TXT.\n")
        else:self.summary_text.insert("end","Brak aktywnej sesji. Rozpocznij obserwację, aby utworzyć raport dla transmisji.\n")
        c.close()
    def export_all(self):
        p=REPORTS/("Wampir66_historia_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".csv")
        c=connect();rows=c.execute("""SELECT s.label,e.detected_at,e.donor,e.amount_text,e.currency,e.message,e.raw_text
            FROM events e LEFT JOIN sessions s ON s.id=e.session_id ORDER BY e.id""").fetchall();c.close()
        with p.open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f,delimiter=";");w.writerow(["Transmisja","Czas","Nadawca OCR","Kwota","Waluta","Tekst OCR","Surowy OCR"])
            for r in rows:w.writerow(list(r))
        messagebox.showinfo(APP,"Zapisano:\n"+str(p))
    def close(self):
        if self.active_session is not None:
            if not messagebox.askyesno(APP,"Zakończyć aktywną sesję i zapisać raport?"): return
            self.closing=True; self.stop(); return
        self.destroy()

if __name__=="__main__":
    if "--self-test" in sys.argv:
        from portable_selftest import run
        run(sys.argv, sys.modules[__name__])
    else:
        app=App();app.protocol("WM_DELETE_WINDOW",app.close);app.mainloop()
