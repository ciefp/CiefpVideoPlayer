# -*- coding: utf-8 -*-
import os
import json
import shutil
import urllib.request
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList  # DODAJ OVO!
from Tools.LoadPixmap import LoadPixmap
from Components.Pixmap import Pixmap
from enigma import eTimer

CONFIG_FILE = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer/config.json"
DEFAULT_CACHE_DIR = "/tmp/ciefp_cache"
PLUGIN_PATH = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer"
PLACEHOLDER = os.path.join(PLUGIN_PATH, "background.png")

class CiefpSettings(Screen):
    skin = """
        <screen position="0,0" size="1920,1080" title="CiefpVideoPlayer Settings" backgroundColor="#00240e" flags="wfNoBorder">
            <eLabel position="0,0" size="1920,100" backgroundColor="#1a1a1a" zPosition="-1" />
            <eLabel text="..:: CiefpVideoPlayer Settings ::.." position="60,25" size="600,50" font="Regular;40" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" />
            
            <widget name="settings_list" position="60,150" size="1000,750" scrollbarMode="showAlways" itemHeight="50" font="Regular;32" transparent="1" />
            
            <widget name="poster_placeholder" position="1150,150" size="700,750" alphatest="blend" zPosition="1" />
            <widget name="status" position="60,910" size="1800,45" font="Regular;32" foregroundColor="#ffffff" backgroundColor="transparent" transparent="1" zPosition="2"/>
            
            <eLabel position="0,980" size="1920,100" backgroundColor="#1a1a1a" zPosition="1" />
            <eLabel position="60,1015" size="30,30" backgroundColor="red" zPosition="2" />
            <eLabel text="Exit" position="105,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
            <eLabel position="300,1015" size="30,30" backgroundColor="green" zPosition="2" />
            <eLabel text="Select" position="345,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
        </screen>
    """
    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.settings = self.load_settings()
        
        self["settings_list"] = MenuList([])
        self["status"] = Label("")
        self["poster_placeholder"] = Pixmap()
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
            "ok": self.handleOk,
            "cancel": self.close,
            "red": self.close,
            "green": self.handleOk,
            "up": self.moveUp,
            "down": self.moveDown,
        }, -1)
        self.menu_items = [
            ("TMDB API Key Setup", "api_key"),
            ("OMDb API Key Setup", "omdb_api_key"),  # DODAJ OVO
            ("Cache Settings", "cache"),
            ("Language", "language"),
            ("About", "about"),
            ("Close", "close")
        ]

        self.update_menu()

        self.onLayoutFinish.append(self.showDefaultImage)
    
    def load_settings(self):
        """Učitava settings iz config.json"""
        default = {
            "tmdb_api_key": "",
            "cache_size_mb": 100,
            "auto_clear_cache": False,
            "language": "en",
            "cache_dir": DEFAULT_CACHE_DIR
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    settings = json.load(f)
                    # Merge sa default
                    for key in default:
                        if key not in settings:
                            settings[key] = default[key]
                    return settings
            except:
                return default
        return default
    
    def save_settings(self):
        """Čuva settings u config.json"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
            return True
        except Exception as e:
            print(f"[Settings] Save error: {e}")
            return False

    def showDefaultImage(self):
        if os.path.exists(PLACEHOLDER):
            pixmap = LoadPixmap(PLACEHOLDER)
            if pixmap:
                self["poster_placeholder"].instance.setPixmap(pixmap)
            else:
                print("[CiefpSettings] Failed to load pixmap from:", PLACEHOLDER)
        else:
            print("[CiefpSettings] Placeholder file not found at:", PLACEHOLDER)

    def update_menu(self):
        """Ažurira prikaz menija"""
        menu_display = [item[0] for item in self.menu_items]
        self["settings_list"].setList(menu_display)
    
    def moveUp(self):
        self["settings_list"].up()
    
    def moveDown(self):
        self["settings_list"].down()

    def handleOk(self):
        idx = self["settings_list"].getSelectedIndex()
        if idx >= 0 and idx < len(self.menu_items):
            action = self.menu_items[idx][1]

            if action == "api_key":
                self.api_key_setup()
            elif action == "omdb_api_key":  # DODAJ OVO
                self.omdb_api_key_setup()
            elif action == "cache":
                self.cache_settings()
            elif action == "language":
                self.language_settings()
            elif action == "about":
                self.show_about()
            elif action == "close":
                self.close()

    def omdb_api_key_setup(self):
        """OMDb API Key setup menu"""
        current_key = self.settings.get('omdb_api_key', '')
        current_display = current_key[:20] + "..." if len(current_key) > 20 else current_key

        self.session.openWithCallback(
            self.omdb_api_key_menu_callback,
            ChoiceBox,
            title="OMDb API Key Setup",
            list=[
                (f"Current: {current_display}" if current_key else "No API Key Set", "current"),
                ("Enter API Key (Manual)", "manual"),
                ("Load API Key from File", "from_file"),
                ("Test API Key", "test"),
                ("Clear API Key", "clear"),
                ("Back", "back")
            ]
        )

    def omdb_api_key_menu_callback(self, choice):
        if not choice or choice[1] == "back":
            return

        action = choice[1]

        if action == "manual":
            self.session.openWithCallback(
                self.omdb_api_key_entered,
                VirtualKeyBoard,
                title="Enter OMDb API Key:",
                text=self.settings.get('omdb_api_key', '')
            )
        elif action == "from_file":
            self.load_omdb_api_key_from_file()
        elif action == "test":
            self.test_omdb_api_key()
        elif action == "clear":
            self.settings['omdb_api_key'] = ""
            self.save_settings()
            self.session.open(MessageBox, "OMDb API Key cleared!", MessageBox.TYPE_INFO)

    def omdb_api_key_entered(self, api_key):
        if api_key:
            self.settings['omdb_api_key'] = api_key.strip()
            self.save_settings()
            self.session.open(MessageBox, "OMDb API Key saved!", MessageBox.TYPE_INFO)

    def load_omdb_api_key_from_file(self):
        """Učitava OMDb API ključ iz tekst fajla"""
        search_paths = [
            "/home/root/",
            "/media/hdd/",
            "/media/usb/",
            "/tmp/"
        ]

        key_files = []
        for path in search_paths:
            if os.path.exists(path):
                for f in os.listdir(path):
                    if f.endswith(('.txt', '.key', '.api')) and ('omdb' in f.lower() or 'imdb' in f.lower()):
                        key_files.append((f, os.path.join(path, f)))

        if key_files:
            self.session.openWithCallback(
                self.load_selected_omdb_key_file,
                ChoiceBox,
                title="Select OMDb API Key File:",
                list=key_files
            )
        else:
            self.session.openWithCallback(
                self.manual_omdb_key_file_path,
                VirtualKeyBoard,
                title="Enter full path to OMDb API key file:",
                text="/media/hdd/omdb_key.txt"
            )

    def load_selected_omdb_key_file(self, choice):
        if choice:
            filepath = choice[1]
            self.read_omdb_api_key_from_file(filepath)

    def manual_omdb_key_file_path(self, filepath):
        if filepath:
            self.read_omdb_api_key_from_file(filepath)

    def read_omdb_api_key_from_file(self, filepath):
        try:
            with open(filepath, 'r') as f:
                api_key = f.read().strip()
                if api_key:
                    self.settings['omdb_api_key'] = api_key
                    self.save_settings()
                    self.session.open(MessageBox, f"OMDb API Key loaded from:\n{filepath}", MessageBox.TYPE_INFO)
                else:
                    self.session.open(MessageBox, "File is empty!", MessageBox.TYPE_ERROR)
        except Exception as e:
            self.session.open(MessageBox, f"Error reading file:\n{str(e)}", MessageBox.TYPE_ERROR)

    def test_omdb_api_key(self):
        """Testira OMDb API ključ"""
        omdb_key = self.settings.get('omdb_api_key', '')
        if not omdb_key:
            self.session.open(MessageBox, "No OMDb API Key set!\nPlease enter your OMDb API key first.",
                              MessageBox.TYPE_ERROR)
            return

        self["status"].setText("Testing OMDb API Key...")

        import threading
        def test():
            try:
                url = f"http://www.omdbapi.com/?apikey={omdb_key}&t=The+Matrix&r=json"
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(url, context=ctx, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get('Response') == 'True':
                        self.session.open(MessageBox,
                                          f"✅ OMDb API Key is valid!\n\nMovie: {data.get('Title')}\nIMDb: {data.get('imdbRating')}",
                                          MessageBox.TYPE_INFO)
                    else:
                        self.session.open(MessageBox, "⚠️ API Key seems invalid.\nPlease check your key.",
                                          MessageBox.TYPE_ERROR)
            except Exception as e:
                self.session.open(MessageBox, f"❌ API Key test failed!\n\n{str(e)[:100]}", MessageBox.TYPE_ERROR)
            self["status"].setText("Ready")

        thread = threading.Thread(target=test)
        thread.daemon = True
        thread.start()

    def api_key_setup(self):
        """TMDB API Key setup menu"""
        current_key = self.settings['tmdb_api_key']
        current_display = current_key[:20] + "..." if len(current_key) > 20 else current_key
        
        self.session.openWithCallback(
            self.api_key_menu_callback,
            ChoiceBox,
            title="TMDB API Key Setup",
            list=[
                (f"Current: {current_display}" if current_key else "No API Key Set", "current"),
                ("Enter API Key (Manual)", "manual"),
                ("Load API Key from File", "from_file"),
                ("Test API Key", "test"),
                ("Clear API Key", "clear"),
                ("Back", "back")
            ]
        )
    
    def api_key_menu_callback(self, choice):
        if not choice or choice[1] == "back":
            return
        
        action = choice[1]
        
        if action == "manual":
            self.session.openWithCallback(
                self.api_key_entered,
                VirtualKeyBoard,
                title="Enter TMDB API Key:",
                text=self.settings['tmdb_api_key']
            )
        elif action == "from_file":
            self.load_api_key_from_file()
        elif action == "test":
            self.test_api_key()
        elif action == "clear":
            self.settings['tmdb_api_key'] = ""
            self.save_settings()
            self.session.open(MessageBox, "API Key cleared!", MessageBox.TYPE_INFO)
    
    def api_key_entered(self, api_key):
        if api_key:
            self.settings['tmdb_api_key'] = api_key.strip()
            self.save_settings()
            self.session.open(MessageBox, "API Key saved!", MessageBox.TYPE_INFO)
    
    def load_api_key_from_file(self):
        """Učitava API ključ iz tekst fajla"""
        # Pretraži uobičajene lokacije
        search_paths = [
            "/home/root/",
            "/media/hdd/",
            "/media/usb/",
            "/tmp/"
        ]
        
        key_files = []
        for path in search_paths:
            if os.path.exists(path):
                for f in os.listdir(path):
                    if f.endswith(('.txt', '.key', '.api')) and 'tmdb' in f.lower():
                        key_files.append((f, os.path.join(path, f)))
        
        if key_files:
            self.session.openWithCallback(
                self.load_selected_key_file,
                ChoiceBox,
                title="Select API Key File:",
                list=key_files
            )
        else:
            self.session.openWithCallback(
                self.manual_key_file_path,
                VirtualKeyBoard,
                title="Enter full path to API key file:",
                text="/media/hdd/tmdb_key.txt"
            )
    
    def load_selected_key_file(self, choice):
        if choice:
            filepath = choice[1]
            self.read_api_key_from_file(filepath)
    
    def manual_key_file_path(self, filepath):
        if filepath:
            self.read_api_key_from_file(filepath)
    
    def read_api_key_from_file(self, filepath):
        try:
            with open(filepath, 'r') as f:
                api_key = f.read().strip()
                if api_key:
                    self.settings['tmdb_api_key'] = api_key
                    self.save_settings()
                    self.session.open(MessageBox, f"API Key loaded from:\n{filepath}", MessageBox.TYPE_INFO)
                else:
                    self.session.open(MessageBox, "File is empty!", MessageBox.TYPE_ERROR)
        except Exception as e:
            self.session.open(MessageBox, f"Error reading file:\n{str(e)}", MessageBox.TYPE_ERROR)
    
    def test_api_key(self):
        """Testira da li API ključ radi"""
        if not self.settings['tmdb_api_key']:
            self.session.open(MessageBox, "No API Key set!\nPlease enter your TMDB API key first.", MessageBox.TYPE_ERROR)
            return
        
        self["status"].setText("Testing API Key...")
        
        import threading
        
        def test():
            try:
                url = f"https://api.themoviedb.org/3/movie/550?api_key={self.settings['tmdb_api_key']}"
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "Enigma2-CiefpVideoPlayer")
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get('title'):
                        self.session.open(MessageBox, f"✅ API Key is valid!\n\nMovie: {data['title']}\nYear: {data['release_date'][:4]}", MessageBox.TYPE_INFO)
                    else:
                        self.session.open(MessageBox, "⚠️ API Key seems invalid.\nPlease check your key.", MessageBox.TYPE_ERROR)
            except Exception as e:
                self.session.open(MessageBox, f"❌ API Key test failed!\n\nError: {str(e)[:100]}", MessageBox.TYPE_ERROR)
            
            self["status"].setText("Ready")
        
        thread = threading.Thread(target=test)
        thread.daemon = True
        thread.start()

    def omdb_api_key_setup(self):
        """OMDb API Key setup menu"""
        current_key = self.settings.get('omdb_api_key', '')
        current_display = current_key[:20] + "..." if len(current_key) > 20 else current_key

        self.session.openWithCallback(
            self.omdb_api_key_menu_callback,
            ChoiceBox,
            title="OMDb API Key Setup",
            list=[
                (f"Current: {current_display}" if current_key else "No API Key Set", "current"),
                ("✏️ Enter API Key (Manual)", "manual"),
                ("📁 Load API Key from File", "from_file"),
                ("🧪 Test API Key", "test"),
                ("🗑️ Clear API Key", "clear"),
                ("❌ Back", "back")
            ]
        )

    def omdb_api_key_menu_callback(self, choice):
        if not choice or choice[1] == "back":
            return

        action = choice[1]

        if action == "manual":
            self.session.openWithCallback(
                self.omdb_api_key_entered,
                VirtualKeyBoard,
                title="Enter OMDb API Key:",
                text=self.settings.get('omdb_api_key', '')
            )
        elif action == "test":
            self.test_omdb_api_key()
        elif action == "clear":
            self.settings['omdb_api_key'] = ""
            self.save_settings()
            self.session.open(MessageBox, "OMDb API Key cleared!", MessageBox.TYPE_INFO)

    def omdb_api_key_entered(self, api_key):
        if api_key:
            self.settings['omdb_api_key'] = api_key.strip()
            self.save_settings()
            self.session.open(MessageBox, "OMDb API Key saved!", MessageBox.TYPE_INFO)

    def test_omdb_api_key(self):
        """Testira OMDb API ključ"""
        omdb_key = self.settings.get('omdb_api_key', '')
        if not omdb_key:
            self.session.open(MessageBox, "No OMDb API Key set!", MessageBox.TYPE_ERROR)
            return

        self["status"].setText("Testing OMDb API Key...")

        import threading
        def test():
            try:
                url = f"http://www.omdbapi.com/?apikey={omdb_key}&t=The+Matrix&r=json"
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(url, context=ctx, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get('Response') == 'True':
                        self.session.open(MessageBox,
                                          f"✅ OMDb API Key is valid!\n\nMovie: {data.get('Title')}\nIMDb: {data.get('imdbRating')}",
                                          MessageBox.TYPE_INFO)
                    else:
                        self.session.open(MessageBox, "⚠️ API Key seems invalid.", MessageBox.TYPE_ERROR)
            except Exception as e:
                self.session.open(MessageBox, f"❌ API Key test failed!\n\n{str(e)[:100]}", MessageBox.TYPE_ERROR)
            self["status"].setText("Ready")

        thread = threading.Thread(target=test)
        thread.daemon = True
        thread.start()
    
    def cache_settings(self):
        """Cache settings menu"""
        # Izračunaj veličinu keša
        cache_size = self.get_cache_size()
        
        self.session.openWithCallback(
            self.cache_menu_callback,
            ChoiceBox,
            title="Cache Settings",
            list=[
                (f"📊 Cache Info: {cache_size:.1f} MB", "info"),
                (f"💾 Max Cache Size: {self.settings['cache_size_mb']} MB", "size"),
                ("🗑️ Clear Cache", "clear"),
                (f"🔄 Auto-clear on exit: {'ON' if self.settings['auto_clear_cache'] else 'OFF'}", "auto"),
                ("❌ Back", "back")
            ]
        )
    
    def get_cache_size(self):
        """Vraća veličinu keša u MB"""
        cache_dir = self.settings.get('cache_dir', DEFAULT_CACHE_DIR)
        total_size = 0
        
        if os.path.exists(cache_dir):
            for dirpath, dirnames, filenames in os.walk(cache_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        total_size += os.path.getsize(fp)
        
        return total_size / (1024 * 1024)
    
    def cache_menu_callback(self, choice):
        if not choice or choice[1] == "back":
            return
        
        action = choice[1]
        
        if action == "info":
            cache_size = self.get_cache_size()
            cache_dir = self.settings.get('cache_dir', DEFAULT_CACHE_DIR)
            
            info_text = f"Cache Directory: {cache_dir}\n"
            info_text += f"Cache Size: {cache_size:.2f} MB\n"
            info_text += f"Max Size: {self.settings['cache_size_mb']} MB\n"
            info_text += f"Auto-clear: {'ON' if self.settings['auto_clear_cache'] else 'OFF'}"
            
            self.session.open(MessageBox, info_text, MessageBox.TYPE_INFO)
        
        elif action == "size":
            self.session.openWithCallback(
                self.cache_size_entered,
                VirtualKeyBoard,
                title="Enter max cache size (MB):",
                text=str(self.settings['cache_size_mb'])
            )
        
        elif action == "clear":
            self.clear_cache()
        
        elif action == "auto":
            self.settings['auto_clear_cache'] = not self.settings['auto_clear_cache']
            self.save_settings()
            self.session.open(MessageBox, f"Auto-clear cache: {'ON' if self.settings['auto_clear_cache'] else 'OFF'}", MessageBox.TYPE_INFO)
    
    def cache_size_entered(self, size):
        if size:
            try:
                new_size = int(size)
                if new_size > 0:
                    self.settings['cache_size_mb'] = new_size
                    self.save_settings()
                    self.session.open(MessageBox, f"Max cache size set to {new_size} MB", MessageBox.TYPE_INFO)
                else:
                    self.session.open(MessageBox, "Please enter a positive number!", MessageBox.TYPE_ERROR)
            except:
                self.session.open(MessageBox, "Invalid number!", MessageBox.TYPE_ERROR)
    
    def clear_cache(self):
        """Briše keš folder"""
        cache_dir = self.settings.get('cache_dir', DEFAULT_CACHE_DIR)
        
        if os.path.exists(cache_dir):
            try:
                for item in os.listdir(cache_dir):
                    item_path = os.path.join(cache_dir, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                
                self.session.open(MessageBox, "Cache cleared successfully!", MessageBox.TYPE_INFO)
            except Exception as e:
                self.session.open(MessageBox, f"Error clearing cache:\n{str(e)}", MessageBox.TYPE_ERROR)
        else:
            self.session.open(MessageBox, "Cache directory does not exist.", MessageBox.TYPE_INFO)
    
    def language_settings(self):
        """Language settings"""
        self.session.openWithCallback(
            self.language_selected,
            ChoiceBox,
            title="Select Language",
            list=[
                ("🇬🇧 English", "en"),
                ("🇷🇸 Serbian (Cyrillic)", "sr-cyrl"),
                ("🇷🇸 Serbian (Latin)", "sr-latn"),
                ("❌ Back", "back")
            ]
        )
    
    def language_selected(self, choice):
        if not choice or choice[1] == "back":
            return
        
        self.settings['language'] = choice[1]
        self.save_settings()
        self.session.open(MessageBox, f"Language set to {choice[0]}", MessageBox.TYPE_INFO)
    
    def show_about(self):
        """About screen"""
        about_text = "CiefpVideoPlayer v1.2\n\n"
        about_text += "Video Player for Enigma2\n"
        about_text += "with TMDB Integration\n\n"
        about_text += "Features:\n"
        about_text += "• Local video playback\n"
        about_text += "• Network mounts (SMB/NFS)\n"
        about_text += "• Online streaming (M3U/TV)\n"
        about_text += "• TMDB movie/TV info\n"
        about_text += "• Cache management\n\n"
        about_text += "GitHub: @ciefp\n"
        about_text += "Powered by TMDB API"
        
        self.session.open(MessageBox, about_text, MessageBox.TYPE_INFO)