import addonHandler
addonHandler.initTranslation()
import os, threading, subprocess, re, time, gc, json, wx, gui, globalPluginHandler, logHandler
from scriptHandler import script
log = logHandler.log

IS_SHUTTING_DOWN = False

def force_delete_file(path, retries=10, delay=0.15):
    if not path or not os.path.exists(path): return True
    try: os.chmod(path, 0o777)
    except: pass
    for _ in range(retries):
        try: os.remove(path); return True
        except: gc.collect(); time.sleep(delay)
    return False

def sanitize(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()[:80]

class CustomProgressDialog(wx.Dialog):
    def __init__(self, parent, title):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.cancelled=False; self.cancel_in_progress=False; self.last_announced=-1; self.silent_close=False
        sizer=wx.BoxSizer(wx.VERTICAL)
        self.phaseLabel=wx.StaticText(self, label=_("Phase: Initializing")); sizer.Add(self.phaseLabel,0,wx.ALL|wx.EXPAND,8)
        self.msgLabel=wx.StaticText(self, label=_("Starting...")); sizer.Add(self.msgLabel,0,wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.EXPAND,8)
        self.percentLabel=wx.StaticText(self, label=_("0 percent"))
        f=self.percentLabel.GetFont(); f.SetPointSize(13); f.SetWeight(wx.FONTWEIGHT_BOLD); self.percentLabel.SetFont(f)
        sizer.Add(self.percentLabel,0,wx.ALIGN_CENTER_HORIZONTAL,4)
        self.gauge=wx.Gauge(self, range=100, size=(500,26)); sizer.Add(self.gauge,0,wx.ALL|wx.EXPAND,10)
        self.detailLabel=wx.StaticText(self, label=""); sizer.Add(self.detailLabel,0,wx.LEFT|wx.RIGHT|wx.EXPAND,6)
        self.cancelBtn=wx.Button(self, label=_("&Cancel")); self.cancelBtn.Bind(wx.EVT_BUTTON, self.onCancel)
        sizer.Add(self.cancelBtn,0,wx.ALL|wx.ALIGN_CENTER,10)
        self.SetSizerAndFit(sizer); self.CenterOnParent()
        self.Bind(wx.EVT_CLOSE, self.onCloseWindow); self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
        wx.CallAfter(self.cancelBtn.SetFocus)
    def announce(self, txt):
        try: import ui; ui.message(txt)
        except: pass
    def Update(self, value, phase, text, detail=""):
        if self.cancelled or self.silent_close: return
        if wx.IsMainThread(): self._do(value,phase,text,detail)
        else: wx.CallAfter(self._do,value,phase,text,detail)
    def _do(self, value, phase, text, detail):
        try:
            if not self or not self.IsShown() or self.cancelled or self.silent_close: return
            self.phaseLabel.SetLabel(phase)
            if value>=0:
                c=max(0,min(100,int(value))); self.gauge.SetValue(c); self.percentLabel.SetLabel(_("{} percent").format(c)); self.msgLabel.SetLabel(text)
                if c%10==0 and c!=self.last_announced and c>0: self.last_announced=c; self.announce(_("{} percent").format(c))
            else:
                self.gauge.Pulse(); self.percentLabel.SetLabel(_("Processing...")); self.msgLabel.SetLabel(text)
            if detail: self.detailLabel.SetLabel(detail)
            self.Layout()
        except: pass
    def onCharHook(self, event):
        if event.GetKeyCode()==wx.WXK_ESCAPE: self.onCancel(None)
        else: event.Skip()
    def onCancel(self, event):
        global IS_SHUTTING_DOWN
        if IS_SHUTTING_DOWN or self.silent_close or self.cancel_in_progress:
            self.cancelled=True
            try:
                if self.IsModal(): self.EndModal(wx.ID_CANCEL)
                else: self.Destroy()
            except: pass
            return
        if self.cancel_in_progress: return
        self.cancel_in_progress=True
        try: self.cancelBtn.Disable(); self.phaseLabel.SetLabel(_("Cancelling...")); self.msgLabel.SetLabel(_("Please wait...")); self.gauge.Pulse()
        except: pass
        ans=wx.MessageBox(_("Are you sure you want to cancel?\nAll temp files will be deleted."), _("Confirm Cancel"), wx.YES_NO|wx.ICON_WARNING|wx.NO_DEFAULT, self)
        if ans==wx.YES:
            self.cancelled=True
            try:
                if self.IsModal(): self.EndModal(wx.ID_CANCEL)
                else: self.Close()
            except: pass
        else:
            self.cancel_in_progress=False
            try: self.cancelBtn.Enable(); self.cancelBtn.SetFocus()
            except: pass
    def onCloseWindow(self, event):
        global IS_SHUTTING_DOWN
        if IS_SHUTTING_DOWN or self.silent_close:
            self.silent_close=True; self.cancelled=True
            try: self.Destroy()
            except: pass
            return
        self.onCancel(None)
    def force_close_silent(self):
        self.silent_close=True; self.cancelled=True
        try:
            if self.IsModal(): self.EndModal(wx.ID_CANCEL)
            else: self.Destroy()
        except: pass

class DownloaderDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=_("Professional Media Downloader"))
        self.addon_dir=os.path.dirname(os.path.abspath(__file__))
        self.appdata_path=os.path.join(os.environ['APPDATA'],'Media Downloader')
        self.audio_path=os.path.join(self.appdata_path,'Audio'); self.video_path=os.path.join(self.appdata_path,'Video')
        for p in [self.appdata_path,self.audio_path,self.video_path]:
            try: os.makedirs(p, exist_ok=True)
            except: pass
        self.process=None; self.progressDlg=None; self.current_file_path=None; self.target_output_dir=None; self.total_duration=0; self.lock=threading.Lock(); self.was_cancelled=False
        mainSizer=wx.BoxSizer(wx.VERTICAL)
        mainSizer.Add(wx.StaticText(self, label=_("&Enter URL:")),0,wx.ALL|wx.EXPAND,8)
        self.urlInput=wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER); self.urlInput.Bind(wx.EVT_TEXT_ENTER, self.onDownload)
        mainSizer.Add(self.urlInput,0,wx.EXPAND|wx.LEFT|wx.RIGHT,8)
        self.pasteBtn=wx.Button(self, label=_("&Paste")); self.pasteBtn.Bind(wx.EVT_BUTTON, self.onPaste); mainSizer.Add(self.pasteBtn,0,wx.ALL,8)
        mainSizer.Add(wx.StaticText(self, label=_("Format:")),0,wx.ALL,8)
        self.formatCombo=wx.ComboBox(self, choices=['mp3','m4a','mp4','mkv','webm','wav','flac'], style=wx.CB_READONLY); self.formatCombo.SetSelection(0)
        mainSizer.Add(self.formatCombo,0,wx.EXPAND|wx.LEFT|wx.RIGHT,8)
        btnSizer=wx.BoxSizer(wx.HORIZONTAL)
        self.downloadBtn=wx.Button(self, label=_("&Download")); self.downloadBtn.Bind(wx.EVT_BUTTON, self.onDownload)
        self.folderBtn=wx.Button(self, label=_("&Open Folder")); self.folderBtn.Bind(wx.EVT_BUTTON, lambda e: os.startfile(self.appdata_path) if os.path.exists(self.appdata_path) else None)
        self.closeBtn=wx.Button(self, id=wx.ID_CANCEL, label=_("&Close"))
        btnSizer.Add(self.downloadBtn,0,wx.ALL,8); btnSizer.Add(self.folderBtn,0,wx.ALL,8); btnSizer.Add(self.closeBtn,0,wx.ALL,8)
        mainSizer.Add(btnSizer,0,wx.ALIGN_CENTER)
        self.SetSizerAndFit(mainSizer); self.CenterOnParent(); wx.CallAfter(self.urlInput.SetFocus); wx.CallAfter(self.auto_fetch)
    def auto_fetch(self):
        try:
            t=wx.TextDataObject()
            if wx.TheClipboard.Open():
                if wx.TheClipboard.GetData(t):
                    u=t.GetText().strip()
                    if u.startswith("http"): self.urlInput.SetValue(u)
                wx.TheClipboard.Close()
        except: pass
    def onPaste(self, event):
        try:
            t=wx.TextDataObject()
            if wx.TheClipboard.Open():
                if wx.TheClipboard.GetData(t): self.urlInput.SetValue(t.GetText().strip())
                wx.TheClipboard.Close()
        except: pass
    def onDownload(self, event):
        url=self.urlInput.GetValue().strip(); fmt=self.formatCombo.GetValue()
        if not url: wx.MessageBox(_("Please enter URL"),_("Error"),wx.OK|wx.ICON_ERROR); return
        self.downloadBtn.Disable(); self.current_file_path=None; self.total_duration=0; self.was_cancelled=False
        self.progressDlg=CustomProgressDialog(self, _("Professional Media Downloader"))
        threading.Thread(target=self.run_engine, args=(url,fmt), daemon=True).start()
        self.progressDlg.ShowModal()
    def get_duration(self, url, ytdlp):
        try:
            r=subprocess.run([ytdlp,"--no-playlist","--get-duration",url], capture_output=True, text=True, creationflags=0x08000000, timeout=15)
            out=r.stdout.strip().splitlines()[0].strip() if r.stdout else ""
            if out:
                if ":" in out:
                    p=list(map(float,out.split(":")))
                    if len(p)==3: return p[0]*3600+p[1]*60+p[2]
                    if len(p)==2: return p[0]*60+p[1]
                else:
                    try: return float(out)
                    except: pass
        except: pass
        try:
            r=subprocess.run([ytdlp,"--no-playlist","--dump-json",url], capture_output=True, text=True, creationflags=0x08000000, timeout=20)
            if r.stdout:
                for line in r.stdout.splitlines():
                    if line.strip():
                        try:
                            d=json.loads(line).get("duration")
                            if d: return float(d)
                        except: pass
        except: pass
        return 0.0
    def run_engine(self, url, fmt):
        ytdlp=os.path.join(self.addon_dir,"yt-dlp.exe"); ffmpeg_dir=self.addon_dir
        is_video=fmt in ['mp4','mkv','webm']; base=self.video_path if is_video else self.audio_path
        output_tmpl=os.path.join(base, "%(title)s.%(ext)s"); self.target_output_dir=base
        # duration pehle nikal lo - converting ke liye chahiye
        self.total_duration=self.get_duration(url, ytdlp)
        # IMPORTANT: --newline hatao mat, par progress parse \r aur \n dono se karo
        cmd=[ytdlp,"--ffmpeg-location",ffmpeg_dir,"-o",output_tmpl,"--no-mtime","--newline","--no-playlist"]
        if is_video:
            if fmt=='mp4': cmd.extend(["-f","bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"])
            else: cmd.extend(["-f","bestvideo+bestaudio/best","--remux-video",fmt])
        else: cmd.extend(["-x","--audio-format",fmt,"--audio-quality","0"])
        cmd.append(url)
        try:
            self.process=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=0x08000000)
            # FIX: buffer method jo \r aur \n dono handle kare
            buffer=""; last_percent=-1; converting=False; download_finished=False
            # Pehle downloading 0% dikhao
            if self.progressDlg: self.progressDlg.Update(0, _("Phase: Downloading"), _("Downloading: 0%"), _("Starting..."))
            while True:
                if self.progressDlg and self.progressDlg.cancelled:
                    self.was_cancelled=True; self.terminate(); break
                char=self.process.stdout.read(1)
                if not char:
                    if self.process.poll() is not None: break
                    continue
                if char in ('\r','\n'):
                    line=buffer.strip(); buffer=""
                    if not line: continue
                    # Destination file track
                    m=re.search(r'Destination:\s*(.+)', line)
                    if m:
                        p=m.group(1).strip().strip('"')
                        if os.path.isabs(p):
                            with self.lock: self.current_file_path=p
                    # Download percent - sabse important
                    # yt-dlp line jaise: [download]   5.2% of 10.00MiB at ...
                    if "[download]" in line and "%" in line and not converting:
                        dm=re.search(r'(\d+(?:\.\d+)?)%', line)
                        if dm:
                            try:
                                pct=float(dm.group(1))
                                pct_int=int(pct)
                                if pct_int!=last_percent:
                                    last_percent=pct_int
                                    # speed aur eta nikalne ki koshish
                                    detail=line
                                    if len(detail)>100: detail=detail[:100]
                                    if self.progressDlg:
                                        self.progressDlg.Update(pct, _("Phase: Downloading"), _("Downloading: {}%").format(pct_int), detail)
                                if pct>=100:
                                    download_finished=True
                            except: pass
                    # Conversion start tabhi jab download 100% ho chuka ho
                    if download_finished and any(k in line for k in ["[ExtractAudio]","[Merger]","Merging formats","Destination"]):
                        if not converting:
                            converting=True; last_percent=-1
                            if self.progressDlg:
                                self.progressDlg.Update(0, _("Phase: Converting"), _("Converting: 0%"), _("Starting conversion..."))
                    # FFmpeg time progress
                    tm=re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                    if tm and converting:
                        h,m,s=map(float,tm.groups()); cur=h*3600+m*60+s
                        if self.total_duration>0:
                            cp=int(cur/self.total_duration*100)
                            cp=max(0,min(99,cp))
                            if cp!=last_percent:
                                last_percent=cp
                                if self.progressDlg:
                                    self.progressDlg.Update(cp, _("Phase: Converting"), _("Converting: {}%").format(cp), _("Time {} / {} sec").format(int(cur), int(self.total_duration)))
                        else:
                            # Duration nahi to time dikhao pulse ke sath
                            if self.progressDlg:
                                # Har 1 sec me ek baar pulse update
                                if int(cur)!=last_percent:
                                    last_percent=int(cur)
                                    self.progressDlg.Update(-1, _("Phase: Converting"), _("Converting... Time {:02d}:{:02d}:{:02d}").format(int(h),int(m),int(s)), _("Please wait..."))
                else:
                    buffer+=char
            try: self.process.wait(timeout=2); rc=self.process.returncode
            except: rc=-999
            wx.CallAfter(self.close_progress)
            if self.was_cancelled or (self.progressDlg and self.progressDlg.cancelled):
                self.was_cancelled=True; self.nuclear_cleanup(); wx.CallAfter(self.finish,-999)
            else:
                wx.CallAfter(self.finish,rc)
        except Exception as e:
            log.error(f"Engine {e}"); self.terminate(); wx.CallAfter(self.close_progress)
            if self.was_cancelled: wx.CallAfter(self.finish,-999)
            else: wx.CallAfter(self.finish,1)
    def terminate(self):
        with self.lock: p=self.process
        if p:
            try:
                try: p.stdout.close()
                except: pass
                subprocess.run(["taskkill","/F","/T","/PID",str(p.pid)], capture_output=True, creationflags=0x08000000, timeout=3)
            except: pass
            try: p.kill()
            except: pass
            with self.lock: self.process=None
        gc.collect()
    def nuclear_cleanup(self):
        self.terminate(); time.sleep(0.3)
        try:
            with self.lock: bp=self.current_file_path; od=self.target_output_dir
            if bp:
                bd=os.path.dirname(bp)
                if os.path.exists(bd):
                    base=os.path.splitext(os.path.basename(bp))[0][:15]
                    for f in os.listdir(bd):
                        if base in f and any(f.endswith(x) for x in (".part",".ytdl",".temp")):
                            force_delete_file(os.path.join(bd,f))
                for ext in [".part",".ytdl",".temp.mp4",".temp.m4a"]: force_delete_file(bp+ext)
                force_delete_file(bp)
        except: pass
    def close_progress(self):
        if self.progressDlg:
            try:
                if self.progressDlg.IsShown():
                    try:
                        if self.progressDlg.IsModal(): self.progressDlg.EndModal(wx.ID_OK)
                        else: self.progressDlg.Destroy()
                    except: pass
            except: pass
            self.progressDlg=None
    def finish(self, code):
        try: self.downloadBtn.Enable(); self.urlInput.SetFocus()
        except: pass
        if self.was_cancelled or code==-999:
            try: import ui; ui.message(_("Cancelled"))
            except: pass
            wx.MessageBox(_("Cancelled - All temp files deleted."), _("Cancelled"), wx.OK|wx.ICON_WARNING)
            return
        if code==0:
            try: import ui; ui.message(_("Download complete"))
            except: pass
            wx.MessageBox(_("Download and conversion completed!"), _("Success"), wx.OK|wx.ICON_INFORMATION)
            self.urlInput.Clear()
        else:
            wx.MessageBox(_("Download failed. Check URL or internet."), _("Error"), wx.OK|wx.ICON_ERROR)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory=_("Professional Media Downloader")
    def __init__(self):
        super().__init__()
        self._menu_created=False
        try: wx.CallLater(1500, self.create_menu)
        except: pass
    def create_menu(self):
        global IS_SHUTTING_DOWN
        if IS_SHUTTING_DOWN: return
        try:
            if not hasattr(gui,'mainFrame') or not gui.mainFrame or not hasattr(gui.mainFrame,'sysTrayIcon') or not gui.mainFrame.sysTrayIcon:
                wx.CallLater(1500, self.create_menu); return
            if self._menu_created: return
            toolsMenu=gui.mainFrame.sysTrayIcon.toolsMenu
            self.subMenu=wx.Menu()
            item_open=self.subMenu.Append(wx.ID_ANY, _("&Open Downloader")); gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onOpenDialog, item_open)
            item_folder=self.subMenu.Append(wx.ID_ANY, _("Open &Downloads Folder")); gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onOpenFolder, item_folder)
            self.mainMenuItem=toolsMenu.AppendSubMenu(self.subMenu, _("Professional Media Downloader"))
            self._menu_created=True
        except Exception as e: log.error(f"menu {e}")
    def onOpenDialog(self, event):
        try: DownloaderDialog(gui.mainFrame).Show()
        except Exception as e: log.error(f"open {e}")
    def onOpenFolder(self, event):
        try:
            p=os.path.join(os.environ['APPDATA'],'Media Downloader')
            if os.path.exists(p): os.startfile(p)
        except: pass
    @script(description=_("Open Downloader"), gesture="kb:NVDA+shift+y")
    def script_openDownloader(self, gesture): self.onOpenDialog(None)
    def terminate(self):
        global IS_SHUTTING_DOWN
        IS_SHUTTING_DOWN=True
        try:
            for win in wx.GetTopLevelWindows():
                try:
                    if isinstance(win, CustomProgressDialog):
                        win.force_close_silent()
                    elif isinstance(win, DownloaderDialog):
                        try: win.Destroy()
                        except: pass
                except: pass
        except: pass
        try:
            if hasattr(self,'mainMenuItem') and self.mainMenuItem and hasattr(gui,'mainFrame') and gui.mainFrame and hasattr(gui.mainFrame,'sysTrayIcon') and gui.mainFrame.sysTrayIcon:
                try: gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self.mainMenuItem)
                except: pass
        except: pass
