# -*- coding: utf-8 -*-
import os
import json
import ssl
import urllib.request
import urllib.parse
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Tools.LoadPixmap import LoadPixmap

# ---------- CONFIG ----------
CONFIG_FILE = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer/config.json"

def load_config():
    """Učitava kompletnu konfiguraciju iz config.json"""
    default = {
        "tmdb_api_key": "",
        "omdb_api_key": "",
        "cache_dir": "/tmp/ciefp_cache",
        "language": "en-US",
        "show_imdb_rating": True
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                for key in default:
                    if key not in config:
                        config[key] = default[key]
                return config
        except:
            return default
    return default

def get_cache_dir():
    """Vraća cache folder iz konfiguracije"""
    config = load_config()
    cache_dir = config.get('cache_dir', '/tmp/ciefp_cache')
    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except:
            pass
    return cache_dir

def get_omdb_rating(title, year=None, omdb_key=None):
    """Dohvata IMDb ocjenu preko OMDb API"""
    if not omdb_key:
        return None
    
    try:
        params = {"apikey": omdb_key, "t": title, "r": "json"}
        if year:
            params["y"] = year
        
        url = "http://www.omdbapi.com/?" + urllib.parse.urlencode(params)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(url, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        
        if data.get("Response") == "True":
            imdb_rating = data.get("imdbRating")
            if imdb_rating and imdb_rating != "N/A":
                return imdb_rating
        return None
    except Exception as e:
        print(f"[OMDb] Rating error: {e}")
        return None


class TMDBInfoScreen(Screen):
    skin = """
        <screen position="center,center" size="1920,1080" title="TMDB Info" backgroundColor="#0a0a0a" flags="wfNoBorder">
            <!-- Pozadina -->
            <eLabel position="0,0" size="1920,1080" backgroundColor="#0a0a0a" zPosition="-2" />
            
            <!-- Okvir -->
            <eLabel position="30,30" size="1860,1020" backgroundColor="#1a1a1a" zPosition="-1" />
            
            <!-- Poster -->
            <widget name="poster" position="50,50" size="500,750" alphatest="blend" zPosition="1" backgroundColor="#000000" />
            
            <!-- Naslov -->
            <widget name="title" position="600,60" size="1300,70" font="Regular;46" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" />
            
            <!-- Originalni naslov -->
            <widget name="original_title" position="600,140" size="1300,40" font="Regular;28" foregroundColor="#888888" backgroundColor="#1a1a1a" transparent="1" />
            
            <!-- Godina i trajanje -->
            <widget name="year_runtime" position="600,190" size="1300,40" font="Regular;30" foregroundColor="#D3D3D3" backgroundColor="#1a1a1a" transparent="1" />
            
            <!-- Ocjene -->
            <widget name="rating_tmdb" position="600,240" size="600,40" font="Regular;30" foregroundColor="#03a81f" backgroundColor="#1a1a1a" transparent="1" />
            <widget name="rating_imdb" position="600,300" size="600,40" font="Regular;30" foregroundColor="#f5c518" backgroundColor="#1a1a1a" transparent="1" />
            
            <!-- Žanrovi -->
            <widget name="genres" position="600,360" size="1300,50" font="Regular;28" foregroundColor="#f702db" backgroundColor="#1a1a1a" transparent="1" />
            
            <!-- Režiser -->
            <widget name="director" position="600,420" size="1300,40" font="Regular;28" foregroundColor="#f79102" backgroundColor="#1a1a1a" transparent="1" />
            
            <!-- Glumci -->
            <widget name="cast" position="600,480" size="1300,100" font="Regular;26" foregroundColor="#00FFFF" backgroundColor="#1a1a1a" transparent="1" />
            
            <!-- Opis (scrollable) -->
            <widget name="overview" position="600,560" size="1300,300" font="Regular;28" foregroundColor="#cccccc" backgroundColor="#1a1a1a" transparent="1" />
            
            <!-- Status bar -->
            <eLabel position="0,1030" size="1920,50" backgroundColor="#000000" zPosition="1" />
            <widget name="status" position="60,1040" size="800,35" font="Regular;26" foregroundColor="#888888" backgroundColor="#000000" transparent="1" />
            <widget name="filename" position="1100,1040" size="800,35" font="Regular;24" foregroundColor="#555555" backgroundColor="#000000" transparent="1" halign="right" />
            
            <!-- Dugmad -->
            <eLabel position="50,1035" size="30,30" backgroundColor="red" zPosition="2" />
            <eLabel text="Exit" position="95,1030" size="120,40" font="Regular;28" foregroundColor="#ffffff" backgroundColor="#000000" transparent="1" zPosition="2" />
            <eLabel position="220,1035" size="30,30" backgroundColor="green" zPosition="2" />
            <eLabel text="OK" position="265,1030" size="120,40" font="Regular;28" foregroundColor="#ffffff" backgroundColor="#000000" transparent="1" zPosition="2" />
        </screen>
    """
    
    def __init__(self, session, filename, search_query=None):
        Screen.__init__(self, session)
        self.session = session
        self.filename = filename
        self.search_query = search_query
        
        # Učitaj konfiguraciju
        self.config = load_config()
        self.api_key = self.config.get('tmdb_api_key', '')
        self.movie_data = None
        
        self["poster"] = Pixmap()
        self["title"] = Label("")
        self["original_title"] = Label("")
        self["year_runtime"] = Label("")
        self["rating_tmdb"] = Label("")
        self["rating_imdb"] = Label("")
        self["genres"] = Label("")
        self["director"] = Label("")
        self["cast"] = Label("")
        self["overview"] = Label("")
        self["status"] = Label("")
        self["filename"] = Label("")
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.close,
            "cancel": self.close,
            "red": self.close,
            "green": self.close,
        }, -1)
        
        # ISPRAVKA: Pozovi startPretraga umjesto loadInfo
        self.onFirstExecBegin.append(self.startPretraga)

    def startPretraga(self):
        """Pokreće pretragu TMDB"""
        print(f"[DEBUG TMDBInfo] startPretraga - filename type: {type(self.filename)}")

        # Ako imamo direktne podatke (dict za filmove ili serije)
        if self.filename and isinstance(self.filename, dict):
            # Provjeri da li ima 'title' (film) ili 'name' (serija)
            if 'title' in self.filename or 'name' in self.filename:
                print("[DEBUG TMDBInfo] Dobio direktne podatke (dict) - film ili serija")
                self.movie_data = self.filename
                self.loadInfo()
                return

        # Ako je filename string (naziv fajla) - pretraži
        if isinstance(self.filename, str):
            print(f"[DEBUG TMDBInfo] filename je string: {self.filename[:50]}...")
        else:
            print(f"[DEBUG TMDBInfo] filename je {type(self.filename)} - neocekivano!")

        # Pretraži na osnovu naziva
        upit = self.search_query if self.search_query else os.path.basename(self.filename)
        print(f"[DEBUG TMDBInfo] Pretražujem: {upit}")

        if not self.api_key:
            print("[DEBUG TMDBInfo] NEMA API KLJUCA!")
            self["status"].setText("No TMDB API Key! Set it in Settings.")
            self.movie_data = None
            self.loadInfo()
            return

        self.searchTMDB(upit)

    def searchTMDB(self, query):
        """Pretražuje TMDB na osnovu upita"""
        self["status"].setText(f"Searching TMDB: {query}...")
        
        try:
            # Prvo traži filmove
            params = {"api_key": self.api_key, "query": query}
            url = "https://api.themoviedb.org/3/search/movie?" + urllib.parse.urlencode(params)
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Enigma2-CiefpVideoPlayer'})
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8', errors='ignore'))
                results = data.get("results", [])
                
                if results:
                    self.get_details(results[0]['id'], 'movie')
                    return
            
            # Ako nema filma, traži seriju
            params = {"api_key": self.api_key, "query": query}
            url = "https://api.themoviedb.org/3/search/tv?" + urllib.parse.urlencode(params)
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Enigma2-CiefpVideoPlayer'})
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8', errors='ignore'))
                results = data.get("results", [])
                
                if results:
                    self.get_details(results[0]['id'], 'tv')
                    return
            
            # Ako nema rezultata
            self["status"].setText("No results found")
            self.movie_data = None
            self.loadInfo()
            
        except Exception as e:
            print(f"[TMDBInfo] Search error: {e}")
            self["status"].setText(f"Search error: {str(e)[:50]}")
            self.movie_data = None
            self.loadInfo()
    
    def get_details(self, media_id, media_type):
        """Dohvata detalje o filmu/seriji"""
        self["status"].setText("Loading details...")
        
        try:
            url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={self.api_key}&append_to_response=credits"
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Enigma2-CiefpVideoPlayer'})
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                self.movie_data = json.loads(response.read().decode('utf-8', errors='ignore'))
                self.loadInfo()
                
        except Exception as e:
            print(f"[TMDBInfo] Details error: {e}")
            self["status"].setText("Error loading details")
            self.movie_data = None
            self.loadInfo()
    
    def loadInfo(self):
        """Učitava i prikazuje informacije"""
        if not self.movie_data:
            self["status"].setText("No information available")
            self["filename"].setText(os.path.basename(self.filename)[:60] if isinstance(self.filename, str) else "Unknown")
            return
        
        if not isinstance(self.movie_data, dict):
            self["status"].setText("Error: Invalid data")
            return
        
        # Naslov i godina
        title = self.movie_data.get('title') or self.movie_data.get('name', 'N/A')
        year = ""
        if 'release_date' in self.movie_data and self.movie_data['release_date']:
            year = self.movie_data['release_date'][:4]
        elif 'first_air_date' in self.movie_data and self.movie_data['first_air_date']:
            year = self.movie_data['first_air_date'][:4]
        
        # Prikaz naslova sa godinom
        if year:
            self["title"].setText(f"{title} ({year})")
        else:
            self["title"].setText(title)
        
        # Originalni naslov
        original_title = self.movie_data.get('original_title') or self.movie_data.get('original_name', '')
        if original_title and original_title != title:
            self["original_title"].setText(original_title)
        
        # Godina i trajanje
        runtime = ""
        if 'runtime' in self.movie_data and self.movie_data['runtime']:
            runtime = f"{self.movie_data['runtime']} min"
        elif 'episode_run_time' in self.movie_data and self.movie_data['episode_run_time']:
            runtime = f"{self.movie_data['episode_run_time'][0]} min/ep"
        
        if year and runtime:
            self["year_runtime"].setText(f"{year} | {runtime}")
        elif year:
            self["year_runtime"].setText(year)
        elif runtime:
            self["year_runtime"].setText(runtime)
        
        # TMDB ocjena
        if 'vote_average' in self.movie_data and self.movie_data['vote_average']:
            tmdb_score = self.movie_data['vote_average']
            vote_count = self.movie_data.get('vote_count', 0)
            stars = "★" * int(round(tmdb_score / 2))
            stars += "☆" * (5 - int(round(tmdb_score / 2)))
            tmdb_rating = f"🎬 TMDB: {stars} {tmdb_score:.1f}/10 ({vote_count} votes)"
            self["rating_tmdb"].setText(tmdb_rating)
        
        # IMDb ocjena (preko OMDb API)
        if self.config.get('show_imdb_rating', True) and self.config.get('omdb_api_key'):
            imdb_rating = get_omdb_rating(title, year, self.config.get('omdb_api_key'))
            if imdb_rating:
                imdb_stars = "★" * int(round(float(imdb_rating) / 2))
                imdb_stars += "☆" * (5 - int(round(float(imdb_rating) / 2)))
                self["rating_imdb"].setText(f"📽️ IMDb: {imdb_stars} {imdb_rating}/10")
        
        # Žanrovi
        genres = []
        if 'genres' in self.movie_data:
            genres = [g['name'] for g in self.movie_data['genres']]
        self["genres"].setText(" | ".join(genres[:5]) if genres else "")
        
        # Režiser
        director = ""
        if 'credits' in self.movie_data:
            for crew in self.movie_data['credits'].get('crew', []):
                if crew.get('job') == 'Director':
                    director = f"🎬 Director: {crew.get('name', '')}"
                    break
        self["director"].setText(director)
        
        # Glumci (top 6)
        cast_list = []
        if 'credits' in self.movie_data:
            for cast in self.movie_data['credits'].get('cast', [])[:6]:
                cast_list.append(cast.get('name', ''))
        if cast_list:
            self["cast"].setText("👥 Cast: " + " | ".join(cast_list))
        
        # Opis
        overview = self.movie_data.get('overview', 'No description available.')
        if len(overview) > 600:
            overview = overview[:600] + "..."
        self["overview"].setText(overview)
        
        # Poster
        poster_path = self.movie_data.get('poster_path')
        if poster_path:
            self.load_poster(poster_path)
        
        self["status"].setText("Info loaded")
        filename_str = os.path.basename(self.filename)[:60] if isinstance(self.filename, str) else "Unknown"
        self["filename"].setText(filename_str)
    
    def load_poster(self, poster_path):
        """Učitava poster sa TMDB"""
        if not poster_path:
            return
        
        try:
            cache_dir = get_cache_dir()
            poster_file = os.path.join(cache_dir, os.path.basename(poster_path))
            
            if os.path.exists(poster_file):
                pixmap = LoadPixmap(poster_file)
                if pixmap:
                    self["poster"].instance.setPixmap(pixmap)
                return
            
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(poster_url, context=ctx, timeout=15) as response:
                data = response.read()
                with open(poster_file, 'wb') as f:
                    f.write(data)
            
            pixmap = LoadPixmap(poster_file)
            if pixmap:
                self["poster"].instance.setPixmap(pixmap)
                
        except Exception as e:
            print(f"[TMDB] Poster load error: {e}")