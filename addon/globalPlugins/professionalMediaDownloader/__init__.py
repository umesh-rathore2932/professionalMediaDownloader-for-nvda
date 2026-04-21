# Professional Media Downloader
# Author: Umesh Rathore
# Description: High-quality media downloader for NVDA with 1000+ sites support
# Version: 2.0

import addonHandler
addonHandler.initTranslation()
import os
import threading
import subprocess
import wx
import gui
import globalPluginHandler
import logHandler
from scriptHandler import script

log = logHandler.log

class DownloaderDialog(wx.Dialog):
	def __init__(self, parent):
		super(DownloaderDialog, self).__init__(parent, title=_("Professional Media Downloader v1.1"))
		
		self.addon_dir = os.path.dirname(os.path.abspath(__file__))
		self.appdata_path = os.path.join(os.environ['APPDATA'], 'Media Downloader')
		self.audio_path = os.path.join(self.appdata_path, 'Audio')
		self.video_path = os.path.join(self.appdata_path, 'Video')
		
		for p in [self.appdata_path, self.audio_path, self.video_path]:
			os.makedirs(p, exist_ok=True)

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		# URL Input
		lbl_url = wx.StaticText(self, label=_("&Enter URL:"))
		self.urlInput = wx.TextCtrl(self)
		mainSizer.Add(lbl_url, 0, wx.ALL | wx.EXPAND, 10)
		mainSizer.Add(self.urlInput, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
		
		# Formats - Updated for Version 1.1 (Added aac, ogg, opus)
		lbl_fmt = wx.StaticText(self, label=_("Select &Format:"))
		formats = ['mp3', 'm4a', 'aac', 'ogg', 'opus', 'wav', 'flac', 'mp4', 'mkv', 'webm']
		self.formatCombo = wx.ComboBox(self, choices=formats, style=wx.CB_READONLY)
		self.formatCombo.SetSelection(0)
		mainSizer.Add(lbl_fmt, 0, wx.ALL, 10)
		mainSizer.Add(self.formatCombo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
		
		# Action Buttons
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.downloadBtn = wx.Button(self, label=_("&Download"))
		self.downloadBtn.Bind(wx.EVT_BUTTON, self.onDownload)
		self.downloadBtn.SetDefault()
		
		self.folderBtn = wx.Button(self, label=_("&Open Downloads"))
		self.folderBtn.Bind(wx.EVT_BUTTON, lambda e: os.startfile(self.appdata_path))
		
		self.closeBtn = wx.Button(self, id=wx.ID_CANCEL, label=_("&Close"))
		
		btnSizer.Add(self.downloadBtn, 0, wx.ALL, 10)
		btnSizer.Add(self.folderBtn, 0, wx.ALL, 10)
		btnSizer.Add(self.closeBtn, 0, wx.ALL, 10)
		mainSizer.Add(btnSizer, 0, wx.ALIGN_CENTER)
		
		self.SetSizerAndFit(mainSizer)
		self.CenterOnParent()

	def onDownload(self, event):
		url = self.urlInput.GetValue().strip()
		fmt = self.formatCombo.GetValue()
		if not url:
			wx.MessageBox(_("Please enter a URL."), _("Error"), wx.OK | wx.ICON_ERROR)
			return
			
		self.pd = wx.ProgressDialog(_("Downloading"), _("Please wait, processing your request..."), parent=self, style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
		self.pd.Pulse()
		self.downloadBtn.Disable()
		threading.Thread(target=self.run_engine, args=(url, fmt), daemon=True).start()

	def run_engine(self, url, fmt):
		# Note: Ensure yt-dlp.exe and ffmpeg are in the addon folder
		ytdlp_exe = os.path.join(self.addon_dir, "yt-dlp.exe")
		ffmpeg_dir = self.addon_dir 
		
		is_video = fmt in ['mp4', 'mkv', 'webm']
		out_dir = self.video_path if is_video else self.audio_path
		output_tmpl = os.path.join(out_dir, "%(title)s.%(ext)s")
		
		cmd = [ytdlp_exe, "--ffmpeg-location", ffmpeg_dir, "-o", output_tmpl, "--no-playlist", "--no-mtime"]
		
		if is_video:
			cmd.extend(["-f", "bestvideo+bestaudio/best"])
		else:
			cmd.extend(["-x", "--audio-format", fmt, "--audio-quality", "0"])
		
		cmd.append(url)

		try:
			# CREATE_NO_WINDOW flag used for silent background process
			proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000)
			proc.communicate()
			wx.CallAfter(self.finish_download, proc.returncode)
		except Exception as e:
			log.error(f"Downloader Error: {e}")
			wx.CallAfter(self.finish_download, 1)

	def finish_download(self, code):
		if hasattr(self, 'pd'): self.pd.Destroy()
		self.downloadBtn.Enable()
		if code == 0:
			wx.MessageBox(_("Download Completed Successfully!"), _("Finished"), wx.OK)
			self.urlInput.Clear()
		else:
			wx.MessageBox(_("Download Failed. Check your URL and Internet."), _("Error"), wx.OK | wx.ICON_ERROR)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("Professional Media Downloader")

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self.create_menu()

	def create_menu(self):
		toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self.subMenu = wx.Menu()
		
		item_open = self.subMenu.Append(wx.ID_ANY, _("&Open Downloader"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onOpenDialog, item_open)
		
		item_folder = self.subMenu.Append(wx.ID_ANY, _("Open &Downloads Folder"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onOpenFolder, item_folder)
		
		item_help = self.subMenu.Append(wx.ID_ANY, _("&Help"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onHelp, item_help)
		
		self.mainMenuItem = toolsMenu.AppendSubMenu(self.subMenu, _("Professional Media Downloader"))

	def onOpenDialog(self, event):
		dlg = DownloaderDialog(gui.mainFrame)
		dlg.Show()

	def onOpenFolder(self, event):
		path = os.path.join(os.environ['APPDATA'], 'Media Downloader')
		if os.path.exists(path): os.startfile(path)

	def onHelp(self, event):
		# Documentation link
		doc_path = os.path.join(os.path.dirname(__file__), "..", "..", "doc", "en", "readme.html")
		if os.path.exists(doc_path): os.startfile(doc_path)

	@script(description=_("Opens the Media Downloader dialog."), gesture="kb:NVDA+shift+y")
	def script_openDownloader(self, gesture):
		self.onOpenDialog(None)

	def terminate(self):
		if hasattr(self, 'mainMenuItem') and self.mainMenuItem:
			try:
				gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self.mainMenuItem)
			except: pass
