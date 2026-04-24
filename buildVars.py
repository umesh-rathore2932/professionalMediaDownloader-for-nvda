from site_scons.site_tools.NVDATool.typings import AddonInfo, BrailleTables, SymbolDictionaries
from site_scons.site_tools.NVDATool.utils import _

addon_info = AddonInfo(
	addon_name="professionalMediaDownloader",
	addon_summary=_("Professional Media Downloader"),
	addon_description=_("A professional tool to download high-quality audio and video from over 1000 websites with auto-clipboard fetch and multi-language support."),
	    addon_changelog=_("Initial 2.0 release with multi-language support."), # Ye line jodein
	addon_version="2.0",
	addon_author="Umesh Rathore",
	addon_url="https://github.com/umesh-rathore2932/professionalMediaDownloader-for-nvda",
	addon_docFileName="readme.html",
	addon_minimumNVDAVersion="2021.1",
	addon_lastTestedNVDAVersion="2025.3.3",
	addon_updateChannel=None,
)

# Python sources updated to include all files in your plugin directory
pythonSources = ["addon/globalPlugins/professionalMediaDownloader/*.py"]

# i18nSources helps scons find all strings for translation
i18nSources = pythonSources + ["addon/manifest.ini", "buildVars.py"]

excludedFiles = []
baseLanguage = "en"
# Markdown extensions for readme processing
markdownExtensions = ["nl2br", "tables"]
brailleTables: BrailleTables = {}
symbolDictionaries: SymbolDictionaries = {}
