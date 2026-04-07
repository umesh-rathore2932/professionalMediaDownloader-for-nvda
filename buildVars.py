from site_scons.site_tools.NVDATool.typings import AddonInfo, BrailleTables, SymbolDictionaries
from site_scons.site_tools.NVDATool.utils import _

addon_info = AddonInfo(
	addon_name="professionalMediaDownloader",
	addon_summary=_("Professional Media Downloader"),
	addon_description=_("A professional tool to download high-quality audio and video from over 1000 websites."),
	addon_version="1.0",
	addon_changelog=_("Initial release."),
	addon_author="Umesh Rathore",
	addon_url=None,
	addon_docFileName="readme.html",
	addon_minimumNVDAVersion="2021.1",
	addon_lastTestedNVDAVersion="2026.1",
	addon_updateChannel=None,
)

pythonSources = ["addon/globalPlugins/professionalMediaDownloader/*.py"]
i18nSources = pythonSources + ["buildVars.py"]
excludedFiles = []
baseLanguage = "en"
markdownExtensions = []
brailleTables: BrailleTables = {}
symbolDictionaries: SymbolDictionaries = {}