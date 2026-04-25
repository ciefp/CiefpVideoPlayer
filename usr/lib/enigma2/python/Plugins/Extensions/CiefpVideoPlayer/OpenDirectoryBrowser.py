# -*- coding: utf-8 -*-
import os
import re
import urllib.request
import urllib.parse
import ssl
import json
from enigma import eTimer
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from enigma import eServiceReference
from twisted.internet import reactor
from Components.Pixmap import Pixmap
from Tools.LoadPixmap import LoadPixmap
from .TMDBInfoScreen import TMDBInfoScreen

# Konfiguracija za TMDB
CONFIG_FILE = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer/config.json"

def get_api_key():
    """Učitava TMDB API ključ iz config.json"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('tmdb_api_key', '')
        except:
            pass
    return ""


class OpenDirectoryBrowser(Screen):
    skin = """
        <screen position="0,0" size="1920,1080" title="Open Directory Browser" backgroundColor="#00240e" flags="wfNoBorder">
            <widget name="background" position="1150,150" size="700,750" alphatest="blend" zPosition="1" />

            <eLabel position="0,0" size="1920,100" backgroundColor="#1a1a1a" zPosition="-1" />
            <eLabel text="..:: Open Directory Browser ::.." position="60,25" size="600,50" font="Regular;40" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" />

            <widget name="directory_list" position="60,150" size="1100,750" scrollbarMode="showAlways" itemHeight="50" font="Regular;32" transparent="1" />

            <widget name="poster" position="1150,150" size="700,750" alphatest="blend" zPosition="1" />

            <widget name="current_path" position="60,910" size="1800,45" font="Regular;28" foregroundColor="#00FF00" backgroundColor="transparent" transparent="1" zPosition="2"/>
            <widget name="status" position="60,950" size="1800,35" font="Regular;24" foregroundColor="#00FF00" backgroundColor="transparent" transparent="1" zPosition="2"/>

            <eLabel position="0,980" size="1920,100" backgroundColor="#1a1a1a" zPosition="1" />
            <eLabel text="RED: Exit" position="60,1020" size="200,40" font="Regular;24" foregroundColor="#FF0000" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
            <eLabel text="GREEN: Play" position="280,1020" size="200,40" font="Regular;24" foregroundColor="#008000" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
            <eLabel text="YELLOW: Movie Info" position="500,1020" size="250,40" font="Regular;24" foregroundColor="#FFDE21" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
            <eLabel text="BLUE: TV Series Info" position="760,1020" size="250,40" font="Regular;24" foregroundColor="#00a2ff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
        </screen>"""

    def __init__(self, session, url):
        Screen.__init__(self, session)
        self.session = session
        self.is_modal = True
        
        self.current_url = url
        self.history = [url]
        self.content_items = [] 
        self.loading = False
        
        self["background"] = Pixmap()
        self["poster"] = Pixmap()
        self["directory_list"] = MenuList([])
        self["current_path"] = Label(url)
        self["status"] = Label("Loading...")

        # Žuto (film) i plavo (serija) dugme
        self["actions"] = ActionMap(["SetupActions", "ColorActions"],
                                    {
                                        "ok": self.handleOk,
                                        "back": self.goBack,
                                        "cancel": self.close,
                                        "red": self.close,
                                        "green": self.playCurrent,
                                        "yellow": self.showMovieInfo,   # Filmovi
                                        "blue": self.showTVInfo,        # Serije
                                    }, -1)

        self.plugin_path = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer"
        self.background_png = os.path.join(self.plugin_path, "background.png")

        self.onLayoutFinish.append(self.setupLayout)
        self.onLayoutFinish.append(self.startLoading)

    def setupLayout(self):
        """Postavlja slike nakon što se prozor iscrta"""
        if os.path.exists(self.background_png):
            self["background"].instance.setPixmap(LoadPixmap(self.background_png))

    def startLoading(self):
        self.loading = True
        self["status"].setText("Fetching directory content...")
        self["current_path"].setText(self.current_url)
        
        # SSL kontekst za HTTPS linkove
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        try:
            from twisted.web.client import getPage
            getPage(self.current_url.encode('utf-8'), timeout=15).addCallback(self.fetchSuccess).addErrback(self.fetchError)
        except Exception as e:
            self.fetchError(str(e))

    def fetchSuccess(self, html):
        html = html.decode('utf-8', 'ignore')
        self.content_items = []
        
        # Regex za izvlačenje linkova (standardni Open Directory format)
        pattern = re.compile(r'href=["\'](.*?)["\']>(.*?)</a>', re.I)
        matches = pattern.findall(html)
        
        temp_list = []
        for link, name in matches:
            if link.startswith('?') or link.startswith('/'):
                continue
                
            full_url = urllib.parse.urljoin(self.current_url, link)
            is_folder = link.endswith('/')
            
            # Filtriramo samo video fajlove i foldere
            if is_folder or link.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.ts')):
                clean_name = urllib.parse.unquote(name).replace('/', '')
                temp_list.append((clean_name, full_url, is_folder))
        
        self.content_items = temp_list
        self.updateMenu()
        self.loading = False
        self["status"].setText(f"Found {len(self.content_items)} items")

    def fetchError(self, error):
        self.loading = False
        self["status"].setText("Error loading directory!")
        self.session.open(MessageBox, f"Failed to load directory:\n{error}", MessageBox.TYPE_ERROR)

    def updateMenu(self):
        display_list = []
        for item in self.content_items:
            prefix = "[DIR] " if item[2] else "[VIDEO] "
            display_list.append(prefix + item[0])
        self["directory_list"].setList(display_list)

    def handleOk(self):
        if self.loading:
            return
            
        idx = self["directory_list"].getSelectedIndex()
        if idx < 0 or idx >= len(self.content_items):
            return
            
        name, url, is_folder = self.content_items[idx]
        
        if is_folder:
            self.current_url = url
            self.history.append(url)
            self.startLoading()
        else:
            self.playVideo(url, name)

    def playCurrent(self):
        self.handleOk()

    def playVideo(self, url, name):
        """Pokreće MoviePlayer za video"""
        self["status"].setText(f"Starting: {name}")
        
        if '%' in url:
            try:
                url = urllib.parse.unquote(url)
            except:
                pass
                
        ref = eServiceReference(4097, 0, url)
        ref.setName(name)
        from Screens.InfoBar import MoviePlayer
        self.session.open(MoviePlayer, ref)

    # ==================== TMDB INFO FUNKCIJE ====================
    
    def showMovieInfo(self):
        """Prikazuje TMDB info za film (movie)"""
        if self.loading:
            return
            
        idx = self["directory_list"].getSelectedIndex()
        if idx < 0 or idx >= len(self.content_items):
            self.session.open(MessageBox, "No file selected!", MessageBox.TYPE_INFO)
            return
            
        name, url, is_folder = self.content_items[idx]
        
        if is_folder:
            self.session.open(MessageBox, "TMDB info is only available for video files, not folders!", MessageBox.TYPE_INFO)
            return
        
        api_key = get_api_key()
        if not api_key:
            self.session.open(MessageBox, "TMDB API Key not set!", MessageBox.TYPE_INFO)
            return
        
        self["status"].setText(f"Searching TMDB for movie: {name}...")
        
        # Parsiraj naziv fajla
        title, year = self.parse_filename_for_media(name)
        
        if not title:
            self.session.open(MessageBox, f"Cannot parse filename:\n{name}", MessageBox.TYPE_INFO)
            self["status"].setText("Parse failed")
            return
        
        # Pretraži TMDB za filmove
        self.search_tmdb_movie(title, year, name)

    def showTVInfo(self):
        """Prikazuje TMDB info za seriju (TV show)"""
        print("[DEBUG] showTVInfo - START")

        if self.loading:
            print("[DEBUG] showTVInfo - loading is True, returning")
            return

        idx = self["directory_list"].getSelectedIndex()
        print(f"[DEBUG] showTVInfo - selected index: {idx}")

        if idx < 0 or idx >= len(self.content_items):
            print("[DEBUG] showTVInfo - invalid index")
            self.session.open(MessageBox, "No file selected!", MessageBox.TYPE_INFO)
            return

        name, url, is_folder = self.content_items[idx]
        print(f"[DEBUG] showTVInfo - name: {name}, is_folder: {is_folder}")

        if is_folder:
            print("[DEBUG] showTVInfo - is folder, returning")
            self.session.open(MessageBox, "TMDB info is only available for video files, not folders!",
                              MessageBox.TYPE_INFO)
            return

        api_key = get_api_key()
        print(f"[DEBUG] showTVInfo - api_key: {api_key[:10] if api_key else 'NOT SET'}")

        if not api_key:
            print("[DEBUG] showTVInfo - no API key")
            self.session.open(MessageBox, "TMDB API Key not set!", MessageBox.TYPE_INFO)
            return

        self["status"].setText(f"Searching TMDB for TV series: {name}...")
        print(f"[DEBUG] showTVInfo - searching for: {name}")

        # Parsiraj naziv fajla
        title, year = self.parse_filename_for_media(name)
        print(f"[DEBUG] showTVInfo - parsed title: '{title}', year: '{year}'")

        if not title:
            print("[DEBUG] showTVInfo - no title parsed")
            self.session.open(MessageBox, f"Cannot parse filename:\n{name}", MessageBox.TYPE_INFO)
            self["status"].setText("Parse failed")
            return

        # Pretraži TMDB za serije
        print("[DEBUG] showTVInfo - calling search_tmdb_tv")
        self.search_tmdb_tv(title, year, name)

    def parse_filename_for_media(self, filename):
        """Parsira naziv fajla i vraća (title, year)"""
        name = filename
        
        # Ukloni ekstenziju
        name = re.sub(r'\.\w{2,4}$', '', name)
        
        # Ukloni razne oznake
        name = re.sub(r'\[.*?\]|\(.*?\)|\{.*?\}', '', name)
        name = re.sub(r'[_\.\-]+', ' ', name)
        
        # Ukloni S01E01 pattern za serije (ako postoji)
        name = re.sub(r'[Ss]\d{1,2}[Ee]\d{1,2}', '', name, flags=re.IGNORECASE)
        
        # Ukloni quality oznake
        noise = r'\b\d{3,4}p\b|\b1080i\b|\bHDRip\b|\bWEB[ -]?DL\b|\bBDRip\b|\bBluRay\b|\bHDTV\b|\bx264\b|\bx265\b|\bHEVC\b'
        name = re.sub(noise, '', name, flags=re.IGNORECASE)
        
        # Očisti višestruke razmake
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Izvuci godinu
        year_match = re.search(r'\b(19|20)\d{2}\b', name)
        year = year_match.group(0) if year_match else ""
        if year:
            name = name[:year_match.start()].strip()
        
        # Prve 2-3 riječi kao naslov
        words = name.split()
        title = " ".join(words[:3]) if words else name
        
        print(f"[OpenDirectory] Parsed: '{filename}' -> title='{title}', year='{year}'")
        
        return title, year
    
    def search_tmdb_movie(self, title, year, original_filename):
        """Pretražuje TMDB za filmove"""
        api_key = get_api_key()
        if not api_key:
            return
        
        self["status"].setText(f"Searching movie: {title}...")
        
        try:
            params = {"api_key": api_key, "query": title}
            if year:
                params["year"] = year
            url = "https://api.themoviedb.org/3/search/movie?" + urllib.parse.urlencode(params)
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Enigma2-CiefpVideoPlayer'})
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8', errors='ignore'))
                results = data.get("results", [])
                
                if results:
                    self.open_tmdb_info_screen(results[0], original_filename, "movie")
                    return
            
            self.session.open(MessageBox, f"No movie found for:\n{title}", MessageBox.TYPE_INFO)
            self["status"].setText("No results")
            
        except Exception as e:
            print(f"[OpenDirectory] Movie search error: {e}")
            self.session.open(MessageBox, f"Search error:\n{str(e)[:100]}", MessageBox.TYPE_ERROR)
            self["status"].setText("Search error")

    def search_tmdb_tv(self, title, year, original_filename):
        """Pretražuje TMDB za serije"""
        print(f"[DEBUG] search_tmdb_tv - START: title='{title}', year='{year}'")

        api_key = get_api_key()
        print(f"[DEBUG] search_tmdb_tv - api_key: {api_key[:10] if api_key else 'NOT SET'}")

        if not api_key:
            print("[DEBUG] search_tmdb_tv - no API key, returning")
            return

        self["status"].setText(f"Searching TV series: {title}...")

        try:
            params = {"api_key": api_key, "query": title}
            if year:
                params["first_air_date_year"] = year
            url = "https://api.themoviedb.org/3/search/tv?" + urllib.parse.urlencode(params)
            print(f"[DEBUG] search_tmdb_tv - URL: {url}")

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(url, headers={'User-Agent': 'Enigma2-CiefpVideoPlayer'})
            print("[DEBUG] search_tmdb_tv - making request...")

            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8', errors='ignore'))
                results = data.get("results", [])
                print(f"[DEBUG] search_tmdb_tv - got {len(results)} results")

                if results:
                    print(f"[DEBUG] search_tmdb_tv - first result: {results[0].get('name')}")
                    self.open_tmdb_info_screen(results[0], original_filename, "tv")
                    return

            print("[DEBUG] search_tmdb_tv - no results found")
            self.session.open(MessageBox, f"No TV series found for:\n{title}", MessageBox.TYPE_INFO)
            self["status"].setText("No results")

        except Exception as e:
            print(f"[DEBUG] search_tmdb_tv - ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.session.open(MessageBox, f"Search error:\n{str(e)[:100]}", MessageBox.TYPE_ERROR)
            self["status"].setText("Search error")

    def open_tmdb_info_screen(self, media_data, filename, media_type):
        """Otvara TMDBInfoScreen sa podacima"""
        print(f"[DEBUG] open_tmdb_info_screen - START: media_type={media_type}, filename={filename}")
        print(f"[DEBUG] open_tmdb_info_screen - media_data keys: {media_data.keys() if media_data else 'None'}")

        self["status"].setText("Loading TMDB details...")

        # Dohvati detalje (credits, etc.)
        api_key = get_api_key()
        if api_key and media_data.get('id'):
            try:
                url = f"https://api.themoviedb.org/3/{media_type}/{media_data['id']}?api_key={api_key}&append_to_response=credits"
                print(f"[DEBUG] open_tmdb_info_screen - fetching details: {url}")

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                req = urllib.request.Request(url, headers={'User-Agent': 'Enigma2-CiefpVideoPlayer'})
                with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                    details = json.loads(response.read().decode('utf-8', errors='ignore'))
                    media_data.update(details)
                    print(f"[DEBUG] open_tmdb_info_screen - details fetched, keys: {media_data.keys()}")
            except Exception as e:
                print(f"[DEBUG] open_tmdb_info_screen - details error: {e}")

        print(f"[DEBUG] open_tmdb_info_screen - opening TMDBInfoScreen with media_data dict")
        self.session.open(TMDBInfoScreen, media_data, filename)
        self["status"].setText("Ready")

    def goBack(self):
        """Siguran izlaz bez TypeError-a"""
        if self.loading:
            return
            
        if len(self.history) > 1:
            self.history.pop()
            self.current_url = self.history[-1]
            self.startLoading()
        else:
            self.close()