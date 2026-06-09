# -*- coding: utf-8 -*-
import os
import re
import urllib.request
import urllib.parse
import subprocess
import socket
import threading
import json
import ssl
from Screens.InfoBar import MoviePlayer
from enigma import eServiceReference
from urllib.parse import unquote
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.FileList import FileList
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Plugins.Plugin import PluginDescriptor
from enigma import eTimer
from Tools.LoadPixmap import LoadPixmap
from twisted.internet import reactor

# Import naših modula
from .CiefpSettings import CiefpSettings
from .TMDBInfoScreen import TMDBInfoScreen
from .OpenDirectoryBrowser import OpenDirectoryBrowser
from .CiefpFTPBrowser import CiefpFTPBrowser
from .WebcamPlayer import WebcamPlayer

# Putanje
PLUGIN_NAME = "CiefpVideoPlayer"
PLUGIN_VERSION = "1.5"
PLUGIN_PATH = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer"
PLACEHOLDER = os.path.join(PLUGIN_PATH, "background.png")
GITHUB_URL = "https://github.com/ciefp/CiefpIPTV"
GITHUB_RAW = "https://raw.githubusercontent.com/ciefp/CiefpIPTV/main/"
GITHUB_API_TV = "https://api.github.com/repos/ciefp/CiefpIPTV/contents/"  # Za .tv fajlove
GITHUB_API_M3U = "https://api.github.com/repos/ciefp/CiefpIPTV/contents/M3U"  # Za M3U fajlove
NETWORK_MOUNT = "/media/network"

# Konfiguracija - učitaj API ključ iz CiefpSettings
CONFIG_FILE = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer/config.json"

def get_api_key():
    """Učitava API ključ iz config.json"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('tmdb_api_key', '')
        except:
            pass
    return ""

def get_cache_dir():
    """Učitava cache folder iz config.json"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('cache_dir', '/tmp/ciefp_cache')
        except:
            pass
    return "/tmp/ciefp_cache"

CACHE_DIR = get_cache_dir()
# Kreiraj cache folder ako ne postoji
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)


class CiefpVideoPlayerMain(Screen):
    skin = """
        <screen position="0,0" size="1920,1080" title="CiefpVideoPlayer FHD" backgroundColor="#00240e" flags="wfNoBorder">
            <eLabel position="0,0" size="1920,100" backgroundColor="#1a1a1a" zPosition="-1" />
            <eLabel text="..:: CiefpVideoPlayer ::.." position="60,25" size="600,50" font="Regular;40" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" />
            
            <widget name="main_list" position="60,150" size="1000,750" scrollbarMode="showAlways" itemHeight="50" font="Regular;32" transparent="1" />
            <widget name="online_list" position="60,150" size="1000,750" scrollbarMode="showAlways" itemHeight="50" font="Regular;32" transparent="1" />
            
            <widget name="status" position="60,910" size="560,45" font="Regular;32" foregroundColor="#ffffff" backgroundColor="transparent" transparent="1" zPosition="2"/>
            <widget name="time" position="1650,25" size="200,50" font="Regular;36" halign="right" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="1"/>

            <widget name="poster_placeholder" position="1150,150" size="700,750" alphatest="blend" zPosition="1" />
            <widget name="selection_info" position="1150,910" size="700,50" font="Regular;30" halign="center" foregroundColor="#00FF00" transparent="1" />
            
            <eLabel position="0,980" size="1920,100" backgroundColor="#1a1a1a" zPosition="1" />
            <eLabel position="60,1015" size="30,30" backgroundColor="red" zPosition="2" />
            <eLabel text="Exit" position="105,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
            <eLabel position="300,1015" size="30,30" backgroundColor="green" zPosition="2" />
            <eLabel text="Local" position="345,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
            <eLabel position="510,1015" size="30,30" backgroundColor="yellow" zPosition="2" />
            <eLabel text="Network" position="555,1010" size="200,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
            <eLabel position="755,1015" size="30,30" backgroundColor="blue" zPosition="2" />
            <eLabel text="Online" position="795,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
            <eLabel position="1000,1015" size="30,30" backgroundColor="white" zPosition="2" />
            <eLabel text="Menu" position="1045,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.mode = "LOCAL"
        self.current_online_items = []
        self["main_list"] = FileList("/media/hdd/", showDirectories=True, showFiles=True, matchingPattern="(?i)^.*\.(mp4|mkv|avi|ts|mov|srt)")
        self["online_list"] = MenuList([])
        self["online_list"].hide()
        
        self["status"] = Label("CiefpVideoPlayer v" + PLUGIN_VERSION)
        self["time"] = Label("")
        self["poster_placeholder"] = Pixmap()
        self["selection_info"] = Label("Local Storage")
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MenuActions"], {
            "ok": self.handleOk,
            "cancel": self.close,
            "red": self.close,
            "green": self.openFileBrowser,
            "yellow": self.openNetworkMenu,
            "blue": self.openOnlineMenu,
            "up": self.moveUp,
            "down": self.moveDown,
            "menu": self.showInfoMenu,
        }, -1)

        self.timer = eTimer()
        self.timer.callback.append(self.updateTime)
        self.timer.start(1000, False)

        self.onLayoutFinish.append(self.showDefaultImage)

    def updateTime(self):
        import time
        self["time"].setText(time.strftime("%H:%M:%S"))

    def showDefaultImage(self):
        if os.path.exists(PLACEHOLDER):
            self["poster_placeholder"].instance.setPixmap(LoadPixmap(PLACEHOLDER))

    def moveUp(self):
        if self.mode == "ONLINE":
            self["online_list"].up()
        else:
            self["main_list"].up()

    def moveDown(self):
        if self.mode == "ONLINE":
            self["online_list"].down()
        else:
            self["main_list"].down()

    def openWebcamPlayer(self, bouquet_file, bouquet_name):
        """Otvara WebcamPlayer za dati bouquet"""
        try:
            from .WebcamPlayer import WebcamPlayer
            self.session.open(WebcamPlayer, bouquet_file, bouquet_name)
        except Exception as e:
            self.session.open(MessageBox, f"Error opening WebcamPlayer: {str(e)}", MessageBox.TYPE_ERROR)

    # === GLAVNI MENI ===
    def showInfoMenu(self):
        """Prikazuje glavni MENU"""
        current_name = None
        file_selected = False

        if self.mode == "ONLINE":
            idx = self["online_list"].getSelectedIndex()
            if idx >= 0 and idx < len(self.current_online_items):
                current_name = self.current_online_items[idx]["name"]
                file_selected = True
        else:
            filename = self["main_list"].getFilename()
            if filename:
                current_name = os.path.basename(filename)
                file_selected = True

        menu_items = []
        
        if file_selected and current_name:
            menu_items.append(("Movie Info (TMDB)", "movie"))
            menu_items.append(("TV Show Info (TMDB)", "tv"))
            menu_items.append(("─" * 30, "separator"))

        menu_items.append(("Settings", "settings"))
        menu_items.append(("Cache Info", "cache_info"))
        menu_items.append(("Clear Cache (TMP)", "clear_cache"))
        menu_items.append(("Clear Cache (USB/HDD)", "clear_external_cache"))  # NOVA OPCIJA
        menu_items.append(("About", "about"))
        menu_items.append(("Close", "cancel"))
        
        if file_selected and current_name:
            title = f"CiefpVideoPlayer MENU - Selected: {current_name[:40]}"
        else:
            title = "CiefpVideoPlayer MENU"
        
        self.session.openWithCallback(
            self.main_menu_selected,
            ChoiceBox,
            title=title,
            list=menu_items
        )
    
    def main_menu_selected(self, choice):
        if not choice or choice[1] == "cancel":
            return
        
        action = choice[1]
        
        if action == "settings":
            self.session.open(CiefpSettings)
        elif action == "about":
            about_text = "CiefpVideoPlayer v1.5\n\nVideo Player with TMDB Info\nLocal | Network | Online | FTP Android Phone\n\n© 2026 Ciefp"
            self.session.open(MessageBox, about_text, MessageBox.TYPE_INFO)
        elif action == "cache_info":
            self.show_cache_info()
        elif action == "clear_cache":
            self.clear_cache()
        elif action == "clear_external_cache":  # DODATO
            self.clear_external_storage_cache()
        elif action in ("movie", "tv"):
            self.show_tmdb_info(action)
    
    def show_cache_info(self):
        """Prikazuje informacije o kešu"""
        cache_dir = get_cache_dir()
        cache_size = 0
        cache_file_count = 0
        
        if os.path.exists(cache_dir):
            for dirpath, dirnames, filenames in os.walk(cache_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        cache_size += os.path.getsize(fp)
                        cache_file_count += 1
        
        size_mb = cache_size / (1024 * 1024)
        
        info_text = f"Cache Directory: {cache_dir}\n"
        info_text += f"Files: {cache_file_count}\n"
        info_text += f"Size: {size_mb:.2f} MB"
        
        self.session.open(MessageBox, info_text, MessageBox.TYPE_INFO)
    
    def clear_cache(self):
        """Briše keš folder"""
        cache_dir = get_cache_dir()
        
        if not os.path.exists(cache_dir):
            self.session.open(MessageBox, "Cache directory does not exist.", MessageBox.TYPE_INFO)
            return
        
        try:
            import shutil
            for item in os.listdir(cache_dir):
                item_path = os.path.join(cache_dir, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            
            self.session.open(MessageBox, "Cache cleared successfully!", MessageBox.TYPE_INFO)
            self["status"].setText("Cache cleared")
        except Exception as e:
            self.session.open(MessageBox, f"Error clearing cache:\n{str(e)}", MessageBox.TYPE_ERROR)

    def clear_external_storage_cache(self):
        """Pretražuje i briše zaostale video i cuts fajlove na eksternim diskovima"""
        paths_to_check = ["/media/usb/", "/media/hdd/", "/tmp/"]
        extensions_to_delete = [".cuts", ".ap", ".sc", ".meta", ".reappeard"]
        deleted_count = 0

        try:
            for path in paths_to_check:
                if os.path.exists(path) and os.path.isdir(path):
                    for filename in os.listdir(path):
                        # Brišemo zaostale privremene video fajlove
                        if filename.startswith("video-") and filename.endswith(".mp4"):
                            os.remove(os.path.join(path, filename))
                            deleted_count += 1

                        # Brišemo sve pomoćne fajlove (cuts, ap, itd.)
                        for ext in extensions_to_delete:
                            if filename.endswith(ext):
                                os.remove(os.path.join(path, filename))
                                deleted_count += 1

            self.session.open(MessageBox, f"Cleanup finished!\nRemoved {deleted_count} cache files from USB/HDD.",
                              MessageBox.TYPE_INFO)
            self["status"].setText(f"Cleaned {deleted_count} files")
        except Exception as e:
            self.session.open(MessageBox, f"Cleanup error: {str(e)}", MessageBox.TYPE_ERROR)

    # === TMDB INFO ===
    def parse_filename_for_media(self, filename):
        """Returns (title, year, season, episode, is_tv) — highly robust for real IPTV filenames"""
        name = os.path.basename(filename)

        # Remove any brackets first
        name = re.sub(r'\[.*?\]|\(.*?\)|\{.*?\}', '', name)
        # Normalize all separators to spaces
        name = re.sub(r'[_\.\-]+', ' ', name)

        # Detect TV pattern *before* cleaning
        tv_match = re.search(r'[Ss](\d{1,2})[Ee](\d{1,2})', name)
        season = episode = None
        is_tv = False
        if tv_match:
            season = int(tv_match.group(1))
            episode = int(tv_match.group(2))
            is_tv = True

            # Aggressively remove episode title blocks
            name = re.sub(r'\s*-\s*[Ss]\d{1,2}[Ee]\d{1,2}\s*-\s*[^\.]*', ' ', name, flags=re.IGNORECASE)
            name = re.sub(r'[Ss]\d{1,2}[Ee]\d{1,2}', ' ', name, flags=re.IGNORECASE)
            name = re.sub(r'[Ss]\d{1,2}', ' ', name, flags=re.IGNORECASE)
            name = re.sub(r'[Ee]\d{1,2}', ' ', name, flags=re.IGNORECASE)

        # Remove ALL common noise (case-insensitive) - DODAJ HDTS, CAM, TS, itd.
        noise = r'\b\d{3,4}p\b|\b1080i\b|\bHDRip\b|\bWEB[ -]?DL(Rip)?\b|\bBDRip\b|\bBluRay\b|\bHDTV\b|\bBRRip\b|\bx264\b|\bx265\b|\bh264\b|\bh265\b|\bHEVC\b|\bAAC\b|\bDDP5\.1\b|\bDD5\.1\b|\bAC3\b|\b6CH\b|\b5\.1\b|\b7\.1\b|\bSoftSub\b|\bHardSub\b|\bSubbed\b|\bDubbed\b|\bDualAudio\b|\bEng\b|\bEnglish\b|\bSerbian\b|\bFarsi\b|\bPersian\b|\bnetpaak\.com\b|\bYTS\b|\bChapter\b|\bTape\b|\bSide\b|\bVol\b|\bPart\b|\bThe Original\b|\bGood News\b|\bSanctuary\b|\bPilot\b|\bDDN\b|\bHDTS\b|\bCAM\b|\bTS\b|\bHDCAM\b|\bSCR\b|\bDVDScr\b|\bR5\b|\bLINE\b|\bTELESYNC\b'
        name = re.sub(noise, '', name, flags=re.IGNORECASE)

        # Remove file extension LAST
        name = re.sub(r'\.\w{2,4}$', '', name)

        # Clean extra spaces
        name = re.sub(r'\s+', ' ', name).strip()

        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', name)
        year = year_match.group(0) if year_match else ""
        if year:
            name = name[:year_match.start()].strip()

        # Keep ONLY first 1–2 words to avoid episode titles & noise
        words = [w for w in name.split() if w]
        clean_words = []
        for i, w in enumerate(words):
            if i >= 2:
                break
            if w.islower() and len(w) <= 5:
                break
            clean_words.append(w.capitalize())
        title = " ".join(clean_words).replace("Iii", "III").replace("Ii", "II")

        # Debug ispis
        print(f"[DEBUG PARSE] '{filename}' → title='{title}', year='{year}', is_tv={is_tv}")

        return title, year, season, episode, is_tv

    def search_tmdb_movie(self, title, year=None):
        """Pretražuje TMDB za film - kopirano iz CiefpMovieInfoIPTV"""
        api_key = get_api_key()
        if not api_key or not title:
            return None, None
        try:
            params = {"api_key": api_key, "query": title}
            if year:
                params["year"] = year
            url = "https://api.themoviedb.org/3/search/movie?" + urllib.parse.urlencode(params)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            results = data.get("results", [])
            return (results[0], "movie") if results else (None, None)
        except Exception as e:
            print(f"[TMDB] Search movie error: {e}")
            return None, None

    def search_tmdb_tv(self, title, year=None):
        """Pretražuje TMDB za seriju - kopirano iz CiefpMovieInfoIPTV"""
        api_key = get_api_key()
        if not api_key or not title:
            return None, None
        try:
            params = {"api_key": api_key, "query": title}
            if year:
                params["first_air_date_year"] = year
            url = "https://api.themoviedb.org/3/search/tv?" + urllib.parse.urlencode(params)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            results = data.get("results", [])
            return (results[0], "tv") if results else (None, None)
        except Exception as e:
            print(f"[TMDB] Search TV error: {e}")
            return None, None

    def get_tmdb_details(self, media_id, media_type):
        """Dohvata detalje filma/serije"""
        api_key = get_api_key()
        if not api_key:
            return None
        
        try:
            url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={api_key}&append_to_response=credits"
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except Exception as e:
            print(f"[TMDB] Details error: {e}")
            return None

    def show_tmdb_info(self, search_type):
        """Prikazuje TMDB info za selektovani fajl - pojednostavljeno"""
        filename = None

        if self.mode == "ONLINE":
            idx = self["online_list"].getSelectedIndex()
            if idx >= 0 and idx < len(self.current_online_items):
                filename = self.current_online_items[idx]["name"]
        else:
            filename = self["main_list"].getFilename()
            if filename:
                filename = os.path.basename(filename)

        if not filename:
            return

        api_key = get_api_key()
        if not api_key:
            self.session.open(MessageBox, "TMDB API Key not set!\nGo to Menu -> Settings -> TMDB API Key Setup",
                              MessageBox.TYPE_INFO)
            return

        self["status"].setText(f"Searching TMDB for: {filename}...")

        title, year, season, episode, is_tv = self.parse_filename_for_media(filename)

        print(f"[DEBUG PARSE] '{filename}' → title='{title}', year='{year}', is_tv={is_tv}")

        if not title:
            self.session.open(MessageBox, f"Cannot parse filename:\n{filename}", MessageBox.TYPE_INFO)
            return

        # Pretraga
        match, media_type = None, None

        if is_tv or search_type == "tv":
            match, media_type = self.search_tmdb_tv(title, year)
            if not match and search_type == "tv":
                match, media_type = self.search_tmdb_movie(title, year)
        else:
            match, media_type = self.search_tmdb_movie(title, year)
            if not match:
                match, media_type = self.search_tmdb_tv(title, year)

        if not match:
            self.session.open(MessageBox, f"No results found for:\n{title} {year if year else ''}",
                              MessageBox.TYPE_INFO)
            self["status"].setText("No results")
            return

        details = self.get_tmdb_details(match['id'], media_type)
        if not details:
            self.session.open(MessageBox, "Cannot fetch details!", MessageBox.TYPE_ERROR)
            return

        self.session.open(TMDBInfoScreen, filename, title)
        self["status"].setText("Ready")

    # === LOKALNI SADRŽAJ ===
    def loadLocalContent(self):
        self.mode = "LOCAL"
        self["main_list"].show()
        self["online_list"].hide()
        self["selection_info"].setText("Local Storage")
        self["main_list"].changeDir("/media/hdd/")

    def openFileBrowser(self):
        self.session.openWithCallback(
            self.browserLocationSelected,
            ChoiceBox,
            title="Choose a location:",
            list=[
                ("HDD", "/media/hdd"),
                ("MEDIA", "/media"),
                ("USB", "/media/usb"),
                ("USB2", "/media/usb2"),
                ("Root", "/"),
                ("Userbouquets (IPTV Lists)", "userbouquets"),
                ("🎥 Webcam Player", "webcam_player"),  # NOVA OPCIJA
                ("Network (Laptop)", "network_manual")
            ]
        )

    def browserLocationSelected(self, choice):
        if choice:
            if choice[1] == "network_manual":
                self.openNetworkMenu()
            elif choice[1] == "userbouquets":
                self.openUserbouquetBrowser()
            elif choice[1] == "webcam_player":  # NOVA OPCIJA
                self.openWebcamPlayerMenu()
            else:
                self.loadFolderContent(choice[1])

    def loadFolderContent(self, path):
        self.mode = "NETWORK"
        self["online_list"].hide()
        self["main_list"].show()
        self["main_list"].changeDir(path)
        self["selection_info"].setText("Mreža: " + os.path.basename(path))

    def openUserbouquetBrowser(self):
        """Prikazuje samo userbouquet.ciefpsettings fajlove iz /etc/enigma2"""
        enigma2_dir = "/etc/enigma2"

        if not os.path.exists(enigma2_dir):
            self.session.open(MessageBox, "Directory /etc/enigma2 not found!", MessageBox.TYPE_ERROR)
            return

        # Pronađi sve relevantne fajlove
        bouquet_files = []
        try:
            for filename in os.listdir(enigma2_dir):
                if filename.endswith(".tv"):
                    # Prvo grupiši po tipu
                    if filename.startswith("userbouquet.ciefpsettings"):
                        # CiefpSettings buketi
                        name_part = filename.replace("userbouquet.", "").replace(".tv", "")
                        display_name = name_part.replace("_", " ").title()
                        bouquet_files.append(("🔷 " + display_name, filename, "normal"))

                    elif filename.startswith("userbouquet.web_cam") or "webcam" in filename.lower():
                        # Webcam buketi
                        name_part = filename.replace("userbouquet.", "").replace(".tv", "")
                        display_name = name_part.replace("_", " ").title()
                        bouquet_files.append(("🎥 " + display_name, filename, "webcam"))

        except Exception as e:
            print(f"[Ciefp] Error reading /etc/enigma2: {e}")

        if not bouquet_files:
            self.session.open(MessageBox,
                              "No bouquet files found!\n\nExpected:\n- userbouquet.ciefpsettings_*.tv\n- userbouquet.web_cam_*.tv",
                              MessageBox.TYPE_INFO)
            return

        # Sortiraj
        bouquet_files.sort(key=lambda x: x[0])

        # Prikaži listu
        choices = [(f[0], (f[1], f[2])) for f in bouquet_files]
        self.session.openWithCallback(
            self.userbouquetSelected,
            ChoiceBox,
            title="Select IPTV Bouquet:",
            list=choices
        )

    def userbouquetSelected(self, choice):
        """Kada korisnik izabere bouquet, učitaj ga"""
        if not choice:
            return

        filename, bouquet_type = choice[1]  # (filename, type)
        filepath = os.path.join("/etc/enigma2", filename)

        if not os.path.exists(filepath):
            self.session.open(MessageBox, f"File not found: {filename}", MessageBox.TYPE_ERROR)
            return

        name_part = filename.replace("userbouquet.", "").replace(".tv", "").replace("_", " ").title()

        # Ako je webcam bouquet, otvori WebcamPlayer
        if bouquet_type == "webcam":
            self.openWebcamPlayer(filepath, name_part)
        else:
            # Normalno parsiranje za CiefpSettings bukete
            self["status"].setText(f"Loading {name_part}...")
            self.parseTVFile(filepath, name_part)

    def openWebcamPlayerMenu(self):
        """Otvara meni za izbor webcam buketa"""
        enigma2_dir = "/etc/enigma2"

        if not os.path.exists(enigma2_dir):
            self.session.open(MessageBox, "Directory /etc/enigma2 not found!", MessageBox.TYPE_ERROR)
            return

        # Pronađi samo webcam bukete
        webcam_files = []
        try:
            for filename in os.listdir(enigma2_dir):
                if filename.endswith(".tv"):
                    # Tražimo webcam bukete (različiti pattern-i)
                    if (filename.startswith("userbouquet.web_cam") or
                            "webcam" in filename.lower() or
                            "prenj" in filename.lower()):
                        name_part = filename.replace("userbouquet.", "").replace(".tv", "")
                        display_name = name_part.replace("_", " ").title()
                        webcam_files.append((display_name, filename))

        except Exception as e:
            print(f"[Ciefp] Error reading webcam files: {e}")

        if not webcam_files:
            self.session.open(MessageBox,
                              "No webcam bouquets found!\n\nExpected files like:\n- userbouquet.web_cam_*.tv\n- userbouquet.ciefpsettings_iptv_webcam.tv\n- userbouquet.*prenj*.tv",
                              MessageBox.TYPE_INFO)
            return

        # Sortiraj
        webcam_files.sort(key=lambda x: x[0])

        # Prikaži listu za izbor
        choices = [(f"🎥 {f[0]}", f[1]) for f in webcam_files]
        self.session.openWithCallback(
            self.webcamPlayerSelected,
            ChoiceBox,
            title="Select Webcam Bouquet:",
            list=choices
        )

    def webcamPlayerSelected(self, choice):
        """Kada korisnik izabere webcam bouquet"""
        if not choice:
            return

        filename = choice[1]
        filepath = os.path.join("/etc/enigma2", filename)

        if not os.path.exists(filepath):
            self.session.open(MessageBox, f"File not found: {filename}", MessageBox.TYPE_ERROR)
            return

        name_part = filename.replace("userbouquet.", "").replace(".tv", "").replace("_", " ").title()

        # Otvori WebcamPlayer
        self.session.open(WebcamPlayer, filepath, name_part)

    def openWebcamPlayer(self, bouquet_file, bouquet_name):
        """Otvara WebcamPlayer za dati bouquet"""
        try:
            from .WebcamPlayer import WebcamPlayer
            self.session.open(WebcamPlayer, bouquet_file, bouquet_name)
        except Exception as e:
            self.session.open(MessageBox, f"Error opening WebcamPlayer: {str(e)}", MessageBox.TYPE_ERROR)

    # === MREŽNI SADRŽAJ ===
    def openNetworkMenu(self):
        self.session.openWithCallback(
            self.networkMenuSelected,
            ChoiceBox,
            title="Network Options",
            list=[ 
			    ("Connect to Phone (Android FTP)", "connect_phone"),
                ("Connect to Laptop (SMB)", "connect_laptop"),
                ("Browse Network Shares", "browse_network"),
                ("Add Network Share", "add_share"),
                ("Disconnect All", "disconnect"),
                ("Auto-Scan", "autoscan"),
            ]
        )

    def networkMenuSelected(self, choice):
        if not choice:
            return
			

        if choice[1] == "connect_phone":
            self.connectToPhone()
        elif choice[1] == "connect_laptop":
            self.connectToLaptop()
        elif choice[1] == "browse_network":
            self.browseNetworkShares()
        elif choice[1] == "add_share":
            self.addNetworkShare()
        elif choice[1] == "disconnect":
            self.disconnectNetwork()
        elif choice[1] == "autoscan":
            self.autoScanNetwork()

# --- FTP PHONE CONNECT SEQUENCER ---
    def connectToPhone(self):
        self.session.openWithCallback(self.phoneIpEntered, VirtualKeyBoard, title="Enter your phone's IP address.:", text="192.168.1.")

    def phoneIpEntered(self, ip):
        if ip:
            self.phone_ip = ip
            self.session.openWithCallback(self.phonePortEntered, VirtualKeyBoard, title="Enter the FTP port (Android usually 2121):", text="2121")

    def phonePortEntered(self, port):
        if port:
            self.phone_port = port
            self.session.openWithCallback(self.phoneUserEntered, VirtualKeyBoard, title="Enter FTP username:", text="root")

    def phoneUserEntered(self, user):
        if user is not None:
            self.phone_user = user
            self.session.openWithCallback(self.phonePassEntered, VirtualKeyBoard, title="Enter FTP username:", text="")

    def phonePassEntered(self, password):
        if password is not None:
            try:
                from .CiefpFTPBrowser import CiefpFTPBrowser
                # Redosled slanja: session (ide automatski), ip, port, user, password
                self.session.open(CiefpFTPBrowser, self.phone_ip, self.phone_port, self.phone_user, password)
            except Exception as e:
                self.session.open(MessageBox, "Error opening: %s" % str(e), MessageBox.TYPE_ERROR)

    def connectToLaptop(self):
        self.session.openWithCallback(
            self.laptopIPEntered,
            VirtualKeyBoard,
            title="Enter Laptop IP Address",
            text="192.168.1."
        )

    def laptopIPEntered(self, ip_address):
        if not ip_address:
            return

        # Spremi IP adresu odmah
        self.laptop_ip = ip_address.strip()

        self.session.openWithCallback(
            self.laptopShareNameEntered,
            VirtualKeyBoard,
            title="Enter Share Name (or leave empty for default)",
            text=""
        )

    def laptopShareNameEntered(self, share_name):
        """Pokreni montiranje u pozadinskom thread-u"""
        # Provjeri da li laptop_ip postoji
        if not hasattr(self, 'laptop_ip') or not self.laptop_ip:
            self.session.open(MessageBox, "No IP address entered!", MessageBox.TYPE_ERROR)
            return

        ip_address = self.laptop_ip
        share_name = share_name or ""

        # Prikaži status odmah
        self["status"].setText(f"Connecting to {ip_address}...")
        self.session.open(MessageBox, f"Connecting to {ip_address}...\nPlease wait...", MessageBox.TYPE_INFO, timeout=2)

        # Pokreni montiranje u thread-u
        def mount_job():
            mount_point = os.path.join(NETWORK_MOUNT, "laptop")

            # Kreiraj mount point (ovo je brzo, može u thread-u)
            if not os.path.exists(mount_point):
                try:
                    os.makedirs(mount_point, exist_ok=True)
                except Exception as e:
                    from twisted.internet import reactor
                    reactor.callFromThread(self.show_mount_error, f"Cannot create mount point: {str(e)}")
                    return

            if share_name:
                smb_path = f"//{ip_address}/{share_name}"
            else:
                smb_path = f"//{ip_address}"

            success = self.mountSMBShare(smb_path, mount_point)

            # Vrati se u glavnu nit za UI ažuriranja
            from twisted.internet import reactor
            reactor.callFromThread(self.mount_finished, success, mount_point)

        thread = threading.Thread(target=mount_job)
        thread.daemon = True
        thread.start()

    def show_mount_error(self, error):
        """Prikaži grešku pri montiranju"""
        self.session.open(MessageBox, error, MessageBox.TYPE_ERROR)
        self["status"].setText("Mount failed")

    def mount_finished(self, success, mount_point):
        """Callback nakon završetka montiranja"""
        if success:
            self.session.open(MessageBox, "Successfully connected!", MessageBox.TYPE_INFO, timeout=2)
            self.loadFolderContent(mount_point)
        else:
            self.session.open(MessageBox, "Cannot connect! Check IP and sharing.", MessageBox.TYPE_ERROR)
            self["status"].setText("Connection failed")

    def check_mount_status(self):
        """Provjerava status montiranja"""
        if hasattr(self, 'mount_done') and self.mount_done:
            self.mount_check_timer.stop()

            if self.mount_success:
                self.session.open(MessageBox, "Successfully connected!", MessageBox.TYPE_INFO, timeout=2)
                self.loadFolderContent(self.mount_point)
            else:
                if self.mount_error:
                    self.session.open(MessageBox, f"Error: {self.mount_error}", MessageBox.TYPE_ERROR)
                else:
                    self.session.open(MessageBox, "Cannot connect! Check IP and sharing.", MessageBox.TYPE_ERROR)
                self["status"].setText("Connection failed")

            # Očisti
            del self.mount_done
            del self.mount_success
            if hasattr(self, 'mount_point'):
                del self.mount_point
            if hasattr(self, 'mount_error'):
                del self.mount_error

    def mountSMBShare(self, smb_path, mount_point):
        """Montira SMB share (poziva se u thread-u)"""
        try:
            # Ako je već mountovan, prvo ga odmontiraj
            if os.path.ismount(mount_point):
                subprocess.run(["umount", "-l", mount_point], capture_output=True, timeout=10)

            # Pokušaj sa različitim verzijama SMB protokola
            mount_options = [
                ["mount", "-t", "cifs", smb_path, mount_point, "-o",
                 "ro,username=guest,password=,iocharset=utf8,vers=3.0"],
                ["mount", "-t", "cifs", smb_path, mount_point, "-o",
                 "ro,username=guest,password=,iocharset=utf8,vers=2.0"],
                ["mount", "-t", "cifs", smb_path, mount_point, "-o", "ro,guest,iocharset=utf8"],
            ]

            for cmd in mount_options:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        return True
                except subprocess.TimeoutExpired:
                    continue
                except Exception:
                    continue

            return False

        except Exception as e:
            print(f"[CiefpVideoPlayer] Mount error: {e}")
            return False

    def browseNetworkShares(self):
        """Pregled mountovanih share-ova"""
        mounted_shares = []
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    if "cifs" in line or NETWORK_MOUNT in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            mounted_shares.append(parts[1])
        except:
            pass

        if mounted_shares:
            choices = [("📂 " + share, share) for share in mounted_shares]
            choices.append(("➕ Add New Share", "add_new"))

            self.session.openWithCallback(
                self.shareSelected,
                ChoiceBox,
                title="Network Shares",
                list=choices
            )
        else:
            self.session.open(MessageBox, "No network shares found!", MessageBox.TYPE_INFO)
            self.connectToLaptop()

    def shareSelected(self, choice):
        if not choice:
            return

        if choice[1] == "add_new":
            self.connectToLaptop()
        else:
            self.loadFolderContent(choice[1])

    def addNetworkShare(self):
        self.session.openWithCallback(
            self.shareTypeSelected,
            ChoiceBox,
            title="Add Network Share",
            list=[
                ("Windows SMB/CIFS", "smb"),
                ("Linux NFS", "nfs"),
            ]
        )

    def shareTypeSelected(self, choice):
        if not choice:
            return

        share_type = choice[1]
        self.session.openWithCallback(
            self.sharePathEntered,
            VirtualKeyBoard,
            title=f"Enter {share_type.upper()} path",
            text="192.168.1.100/Photos"
        )

    def sharePathEntered(self, path):
        if not path:
            return

        share_type = self.pending_share_type
        self.configureShare(share_type, path)

    def configureShare(self, share_type, path):
        """Pokreni konfiguraciju share-a u pozadinskom thread-u"""
        mount_name = path.replace("/", "_").replace(".", "_")
        mount_point = os.path.join(NETWORK_MOUNT, mount_name)

        self["status"].setText(f"Mounting {share_type.upper()} share...")

        def mount_job():
            if not os.path.exists(mount_point):
                try:
                    os.makedirs(mount_point, exist_ok=True)
                except Exception as e:
                    reactor.callFromThread(self.show_mount_error, str(e))
                    return

            success = False
            if share_type == "smb":
                success = self.mountSMBShare("//" + path, mount_point)
            elif share_type == "nfs":
                try:
                    cmd = ["mount", "-t", "nfs", path, mount_point, "-o", "ro"]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    success = result.returncode == 0
                except Exception:
                    success = False

            from twisted.internet import reactor
            reactor.callFromThread(self.mount_configured_finished, success, mount_point)

        self.pending_share_type = share_type
        thread = threading.Thread(target=mount_job)
        thread.daemon = True
        thread.start()

    def show_mount_error(self, error):
        self.session.open(MessageBox, f"Error: {error}", MessageBox.TYPE_ERROR)
        self["status"].setText("Mount failed")

    def mount_configured_finished(self, success, mount_point):
        if success:
            self.session.open(MessageBox, "Share mounted!", MessageBox.TYPE_INFO)
            self.loadFolderContent(mount_point)
        else:
            self.session.open(MessageBox, "Failed to mount share!", MessageBox.TYPE_ERROR)
            self["status"].setText("Mount failed")

    def disconnectNetwork(self):
        """Odmontiraj sve network share-ove"""
        self["status"].setText("Disconnecting network shares...")

        def unmount_job():
            try:
                for item in os.listdir(NETWORK_MOUNT):
                    mount_point = os.path.join(NETWORK_MOUNT, item)
                    if os.path.ismount(mount_point):
                        subprocess.run(["umount", "-l", mount_point], capture_output=True, timeout=10)
                from twisted.internet import reactor
                reactor.callFromThread(self.disconnect_finished, True)
            except Exception as e:
                print(f"[CiefpVideoPlayer] Unmount error: {e}")
                from twisted.internet import reactor
                reactor.callFromThread(self.disconnect_finished, False)

        thread = threading.Thread(target=unmount_job)
        thread.daemon = True
        thread.start()

    def disconnect_finished(self, success):
        if success:
            self.session.open(MessageBox, "All network shares disconnected", MessageBox.TYPE_INFO)
        else:
            self.session.open(MessageBox, "Some shares could not be disconnected", MessageBox.TYPE_WARNING)
        self.loadLocalContent()
        self["status"].setText("Ready")

    def autoScanNetwork(self):
        """Skeniranje mreže sa detaljnim logovanjem grešaka"""
        import socket
        import threading
        from twisted.internet import reactor

        self["status"].setText("SMB network scan in progress...")
        print("[Ciefp Scan] Započinjem skeniranje mreže...")

        def scan_job():
            found_devices = []
            base_ip = ""
            try:
                # 1. Određivanje lokalnog IP-a
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                my_ip = s.getsockname()[0]
                s.close()
                base_ip = ".".join(my_ip.split(".")[:3]) + "."
                print(f"[Ciefp Scan] Lokalni IP: {my_ip}, Opseg: {base_ip}1-254")
            except Exception as e:
                print(f"[Ciefp Scan] Greška pri dobijanju IP-a: {e}")
                base_ip = "192.168.1."

            # 2. Skeniranje porta 445
            for i in range(1, 255):
                ip = base_ip + str(i)
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.3)
                    result = sock.connect_ex((ip, 445))

                    if result == 0:
                        print(f"[Ciefp Scan] PRONAĐEN SMB uređaj na: {ip}")
                        try:
                            hostname = socket.gethostbyaddr(ip)[0]
                        except Exception as hn_err:
                            print(f"[Ciefp Scan] Nije moguće dobiti hostname za {ip}: {hn_err}")
                            hostname = ip
                        found_devices.append((hostname, ip))
                    sock.close()
                except Exception as loop_err:
                    # Ne printamo svaku grešku (većina će biti timeout), samo kritične
                    pass

            print(f"[Ciefp Scan] Skeniranje završeno. Pronađeno uređaja: {len(found_devices)}")

            # 3. Povratak u glavni thread
            try:
                reactor.callFromThread(self.finalizeScan, found_devices)
            except Exception as reactor_err:
                print(f"[Ciefp Scan] KRITIČNA GREŠKA: Reactor call failed: {reactor_err}")

        # Pokretanje thread-a
        try:
            thread = threading.Thread(target=scan_job)
            thread.daemon = True
            thread.start()
        except Exception as thread_err:
            print(f"[Ciefp Scan] Greška pri pokretanju thread-a: {thread_err}")

    def finalizeScan(self, found_devices):
        """Prikaz rezultata - osiguraj da su klase uvezene"""
        print("[Ciefp Scan] Finalizacija prikaza na ekranu...")
        try:
            if found_devices:
                choices = [("{} ({})".format(hostname, ip), ip) for hostname, ip in found_devices]
                self.session.openWithCallback(
                    self.scannedDeviceSelected,
                    ChoiceBox,
                    title="Devices found:",
                    list=choices
                )
            else:
                self.session.open(MessageBox, "Scan complete: No device responded on port 445.",
                                  MessageBox.TYPE_INFO)
        except Exception as ui_err:
            print(f"[Ciefp Scan] UI Greška (finalizeScan): {ui_err}")

        self["status"].setText("Scanning complete.")

    def scannedDeviceSelected(self, choice):
        """Kada se odabere uređaj sa skenera, tražimo unos naziva foldera"""
        if choice:
            self.laptop_ip = choice[1]
            print(f"[Ciefp Scan] Odabran uređaj: {self.laptop_ip}. Otvaram tastaturu za naziv foldera...")

            # Umesto direktnog pokretanja laptopShareNameEntered(""),
            # sada otvaramo VirtualKeyBoard da korisnik ukuca folder
            self.session.openWithCallback(
                self.laptopShareNameEntered,
                VirtualKeyBoard,
                title="Enter the name of the shared folder:",
                text=""
            )

    def laptopShareNameEntered(self, share_name):
        """Sada prima share_name sa tastature i pokreće montiranje"""
        if not hasattr(self, 'laptop_ip') or not self.laptop_ip:
            self.session.open(MessageBox, "Error: IP address not saved!", MessageBox.TYPE_ERROR)
            return

        # Ako korisnik nije ništa ukucao, prekidamo da ne bi bilo greške u mount-u
        if not share_name:
            self["status"].setText("Connection canceled - folder name not entered.")
            return

        ip_address = self.laptop_ip
        print(f"[Ciefp Scan] Pokušaj konekcije na: //{ip_address}/{share_name}")

        # Prikaži status i pokreni mount thread
        self["status"].setText(f"Connecting to: {ip_address}...")

        def mount_job():
            # Kreiramo jedinstvenu tačku montiranja na osnovu IP-a i foldera
            mount_point = os.path.join(NETWORK_MOUNT, f"scan_{share_name}")

            if not os.path.exists(mount_point):
                try:
                    os.makedirs(mount_point, exist_ok=True)
                except Exception as e:
                    from twisted.internet import reactor
                    reactor.callFromThread(self.show_mount_error, f"Folder error: {str(e)}")
                    return

            smb_path = f"//{ip_address}/{share_name}"
            success = self.mountSMBShare(smb_path, mount_point)

            from twisted.internet import reactor
            reactor.callFromThread(self.mount_finished, success, mount_point)

        thread = threading.Thread(target=mount_job)
        thread.daemon = True
        thread.start()

    # === ONLINE MOD ===
    def openOnlineMenu(self):
        """Otvara meni za online sadržaj"""
        self.session.openWithCallback(
            self.onlineMenuSelected,
            ChoiceBox,
            title="Online Video",
            list=[
                ("GitHub TV Lists (.tv)", "github_tv"),
                ("GitHub M3U lists", "github_m3u"),
                ("Open Directory (Movie/TV Series)", "opendirectory"),  # NOVA OPCIJA
                ("Manual URL", "manual_url"),
            ]
        )
    
    def onlineMenuSelected(self, choice):
        if not choice:
            return
        
        if choice[1] == "github_tv":
            self.scanGithubTV()
        elif choice[1] == "github_m3u":
            self.scanGithubM3U()
        elif choice[1] == "opendirectory":  # NOVA OPCIJA
            self.openOpenDirectoryBrowser()
        elif choice[1] == "manual_url":
            self.enterManualURL()
    
    def scanGithubTV(self):
        """Skenira GitHub za .tv fajlove"""
        self["status"].setText("Scanning GitHub for TV lists...")
        try:
            req = urllib.request.Request(GITHUB_API_TV)
            req.add_header("User-Agent", "Enigma2-CiefpVideoPlayer")
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                tv_files = []
                for item in data:
                    if item.get("type") == "file":
                        name = item.get("name", "")
                        if name.endswith(".tv"):
                            clean_name = name.replace("userbouquet.", "").replace(".tv", "").replace("_", " ")
                            clean_name = " ".join([w.capitalize() for w in clean_name.split()])
                            tv_files.append((clean_name, item.get("download_url"), name))
                
                if tv_files:
                    self.session.openWithCallback(
                        self.loadOnlineTVFile,
                        ChoiceBox,
                        title="Select TV list:",
                        list=[(f[0], (f[1], f[2])) for f in sorted(tv_files)]
                    )
                else:
                    self.session.open(MessageBox, "There are no .tv files on GitHub.", MessageBox.TYPE_INFO)
                    self["status"].setText("No .tv files found")
        except Exception as e:
            self["status"].setText("GitHub error: " + str(e)[:30])
            self.session.open(MessageBox, "GitHub Error: " + str(e), MessageBox.TYPE_ERROR)
    
    def scanGithubM3U(self):
        """Skenira GitHub M3U folder za M3U fajlove"""
        self["status"].setText("Scanning GitHub M3U folder...")
        try:
            req = urllib.request.Request(GITHUB_API_M3U)
            req.add_header("User-Agent", "Enigma2-CiefpVideoPlayer")
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                m3u_files = []
                for item in data:
                    if item.get("type") == "file":
                        name = item.get("name", "")
                        if name.lower().endswith(('.m3u', '.m3u8')):
                            clean_name = name.replace(".m3u", "").replace(".m3u8", "").replace("_", " ")
                            clean_name = " ".join([w.capitalize() for w in clean_name.split()])
                            m3u_files.append((clean_name, item.get("download_url"), name))
                
                if m3u_files:
                    self.session.openWithCallback(
                        self.loadOnlineM3UFile,
                        ChoiceBox,
                        title="Select M3U list:",
                        list=[(f[0], (f[1], f[2])) for f in sorted(m3u_files)]
                    )
                else:
                    self.session.open(MessageBox, "No M3U files found in M3U folder!", MessageBox.TYPE_INFO)
                    self["status"].setText("No M3U files found")
                    
        except Exception as e:
            self["status"].setText("GitHub error: " + str(e)[:30])
            self.session.open(MessageBox, "GitHub Error: " + str(e), MessageBox.TYPE_ERROR)
    
    def loadOnlineTVFile(self, choice):
        """Učitava .tv fajl i prikazuje video listu"""
        if not choice:
            return
        
        dl_url, filename = choice[1]
        display_name = choice[0]
        tmp_path = os.path.join(CACHE_DIR, filename)
        
        self["status"].setText("Downloading {}...".format(filename))
        
        try:
            urllib.request.urlretrieve(dl_url, tmp_path)
            self.parseTVFile(tmp_path, display_name)
        except Exception as e:
            self["status"].setText("Download error")
            self.session.open(MessageBox, "Download error: " + str(e), MessageBox.TYPE_ERROR)
    
    def loadOnlineM3UFile(self, choice):
        """Učitava M3U fajl i prikazuje video listu"""
        if not choice:
            return
        
        dl_url, filename = choice[1]
        display_name = choice[0]
        tmp_path = os.path.join(CACHE_DIR, filename)
        
        self["status"].setText("Downloading {}...".format(filename))
        
        try:
            urllib.request.urlretrieve(dl_url, tmp_path)
            self.parseM3UFile(tmp_path, display_name)
        except Exception as e:
            self["status"].setText("Download error")
            self.session.open(MessageBox, "Download error: " + str(e), MessageBox.TYPE_ERROR)

    def parseTVFile(self, filepath, display_name):
        """Parsira Enigma2 .tv bouquet fajl"""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f.readlines()]

            self.current_online_items = []

            i = 0
            while i < len(lines):
                line = lines[i]

                if line.startswith("#SERVICE 4097:") or line.startswith("#SERVICE 1:"):
                    last_colon = line.rfind(':')
                    second_last_colon = line.rfind(':', 0, last_colon - 1)
                    
                    url = ""
                    if second_last_colon != -1:
                        raw_url = line[second_last_colon + 1:last_colon]
                        url = raw_url.replace("%3a", ":").replace("%2f", "/")
                        url = url.replace("%3f", "?").replace("%3d", "=").replace("%26", "&")
                    
                    name = "Nepoznato"
                    
                    if i + 1 < len(lines) and lines[i + 1].startswith("#DESCRIPTION"):
                        desc_line = lines[i + 1]
                        name = desc_line[13:].strip()
                        try:
                            from urllib.parse import unquote
                            name = unquote(name)
                        except:
                            name = name.replace("%20", " ")
                        i += 1
                    
                    if url:
                        self.current_online_items.append({
                            "name": name,
                            "path": url,
                            "type": "online",
                            "info": "VIDEO"
                        })
                
                i += 1

            if self.current_online_items:
                self.displayOnlineList(display_name)
                self["status"].setText("{} video links found".format(len(self.current_online_items)))
            else:
                self.session.open(MessageBox, "There are no video links in this listing.", MessageBox.TYPE_WARNING)
                self["status"].setText("No videos found")

        except Exception as e:
            print("[CiefpVideoPlayer] Parse error:", e)
            self.session.open(MessageBox, "Error parsing file: " + str(e), MessageBox.TYPE_ERROR)

    def parseM3UFile(self, filepath, display_name):
        """Parsira M3U playlist fajl"""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            self.current_online_items = []
            
            lines = content.splitlines()
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.startswith("#EXTINF:"):
                    name = line.split(",", 1)[-1].strip() if "," in line else "Nepoznato"
                    if i + 1 < len(lines):
                        url = lines[i + 1].strip()
                        if url and (url.startswith("http://") or url.startswith("https://")):
                            self.current_online_items.append({
                                "name": unquote(name),
                                "path": url,
                                "type": "online",
                                "info": "STREAM"
                            })
                        i += 1
                i += 1
            
            if self.current_online_items:
                self.displayOnlineList(display_name)
                self["status"].setText("{} streams found".format(len(self.current_online_items)))
            else:
                self.session.open(MessageBox, "No streams in M3U list.", MessageBox.TYPE_WARNING)
                self["status"].setText("No streams found")
                
        except Exception as e:
            print("[CiefpVideoPlayer] M3U parse error:", e)
            self.session.open(MessageBox, "Error parsing M3U: " + str(e), MessageBox.TYPE_ERROR)
    
    def enterManualURL(self):
        """Ručni unos URL-a za M3U ili direktan stream"""
        self.session.openWithCallback(
            self.manualURLEntered,
            VirtualKeyBoard,
            title="Enter M3U or Stream URL:",
            text="http://"
        )
    
    def openOpenDirectoryBrowser(self):
        """Otvara browser za Open Directory"""
        opendirs_file = os.path.join(PLUGIN_PATH, "opendirectories.txt")
        addresses = []

        if os.path.exists(opendirs_file):
            try:
                with open(opendirs_file, "r") as f:
                    addresses = [line.strip() for line in f.readlines() if
                                 line.strip().startswith(('http://', 'https://'))]
            except:
                pass

        # Ako nema adresa, ponudi unos
        if not addresses:
            self.session.openWithCallback(
                self.addOpenDirectoryUrl,
                VirtualKeyBoard,
                title="Enter Open Directory URL:",
                text="http://"
            )
            return

        # Prikaži listu adresa
        self.session.openWithCallback(
            self.openDirectorySelected,
            ChoiceBox,
            title="Select Open Directory:",
            list=[(addr, addr) for addr in addresses] + [("➕ Add New URL", "add_new")]
        )

    def addOpenDirectoryUrl(self, url):
        """Dodaje novi URL u opendirectories.txt i otvara ga"""
        if not url or not url.strip():
            return

        url = url.strip().rstrip('/') + '/'
        if not url.startswith(('http://', 'https://')):
            self.session.open(MessageBox, "Invalid URL! Must start with http:// or https://", MessageBox.TYPE_ERROR)
            return

        # Sačuvaj u fajl
        opendirs_file = os.path.join(PLUGIN_PATH, "opendirectories.txt")
        with open(opendirs_file, "a") as f:
            f.write(url + "\n")

        # Otvori odmah
        self.browseOpenDirectory(url)

    def openDirectorySelected(self, choice):
        """Odabrana adresa iz liste"""
        if not choice:
            return

        if choice[1] == "add_new":
            self.session.openWithCallback(
                self.addOpenDirectoryUrl,
                VirtualKeyBoard,
                title="Enter Open Directory URL:",
                text="http://"
            )
        else:
            self.browseOpenDirectory(choice[1])

    def browseOpenDirectory(self, url):
        """Otvara HTTP direktorijum za browsing - NOVI EKRAN"""
        self.session.open(OpenDirectoryBrowser, url)
    
    def manualURLEntered(self, url):
        if not url or not url.startswith("http"):
            return
        
        if url.endswith((".m3u", ".m3u8")):
            self["status"].setText("Downloading M3U...")
            try:
                tmp_path = os.path.join(CACHE_DIR, "manual.m3u")
                urllib.request.urlretrieve(url, tmp_path)
                self.parseM3UFile(tmp_path, "Manual URL")
            except Exception as e:
                self.session.open(MessageBox, "Error downloading: " + str(e), MessageBox.TYPE_ERROR)
        else:
            self.current_online_items = [{
                "name": "Manual Stream",
                "path": url,
                "type": "online",
                "info": "STREAM"
            }]
            self.displayOnlineList("Manual URL")
    
    def displayOnlineList(self, title):
        """Prikazuje online listu na ekranu"""
        self.mode = "ONLINE"
        self["main_list"].hide()
        self["online_list"].show()
        
        menu_list = []
        for item in self.current_online_items:
            display = "🎬 {} [{}]".format(item["name"], item["info"])
            menu_list.append(display)
        
        self["online_list"].setList(menu_list)
        self["selection_info"].setText("Online: " + title)
        self["status"].setText("Online mode - {} items".format(len(menu_list)))

    def handleOk(self):
        if self.mode == "ONLINE":
            current = self["online_list"].getCurrent()
            if current:
                idx = self["online_list"].getSelectedIndex()
                if idx >= 0 and idx < len(self.current_online_items):
                    item = self.current_online_items[idx]
                    self.playVideo(item["path"], item["name"])
        else:
            if self["main_list"].canDescent():
                self["main_list"].descent()
            else:
                filename = self["main_list"].getFilename()
                if filename:
                    self.playVideo(filename, os.path.basename(filename))

    def playVideo(self, path, name):
        """Pokreće video i automatski priprema titl"""
        self["status"].setText("Priprema titla i videa...")

        # 1. Putanje za titl
        video_dir = os.path.dirname(path)
        video_name_no_ext = os.path.splitext(name)[0]
        local_srt_link = "/tmp/" + video_name_no_ext + ".srt"

        # 2. Ako je fajl lokalan ili mrežni (nije http/ftp)
        if not path.startswith(("http", "ftp")):
            # Tražimo bilo koji .srt fajl u tom folderu
            try:
                for f in os.listdir(video_dir):
                    if f.lower().endswith(".srt"):
                        # Ako titl sadrži deo imena filma, napravi prečicu u /tmp
                        if video_name_no_ext[:10].lower() in f.lower():
                            remote_srt_path = os.path.join(video_dir, f)
                            # Brišemo stari link ako postoji
                            if os.path.exists(local_srt_link): os.remove(local_srt_link)
                            # Pravimo simbolički link (ne zauzima prostor, a plejer ga vidi u /tmp)
                            os.symlink(remote_srt_path, local_srt_link)
                            print(f"[Ciefp] Titl povezan preko symlink-a: {f}")
                            break
            except:
                pass

        # 3. Pokretanje plejera
        service_type = 4097
        ref = eServiceReference(service_type, 0, path)
        ref.setName(name)
        self.session.open(MoviePlayer, ref)


def main(session, **kwargs):
    session.open(CiefpVideoPlayerMain)


def Plugins(**kwargs):
    return [PluginDescriptor(name="{} v{}".format(PLUGIN_NAME, PLUGIN_VERSION), description="Video Player - Local, Network & Online", where=PluginDescriptor.WHERE_PLUGINMENU, icon="icon.png", fnc=main)]