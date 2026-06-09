# -*- coding: utf-8 -*-
import os
import json
import threading
import subprocess
import time
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from enigma import eServiceReference, eTimer
from Tools.LoadPixmap import LoadPixmap
from twisted.internet import reactor

# Putanje
PLUGIN_PATH = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer"
CONFIG_FILE = os.path.join(PLUGIN_PATH, "webcam_config.json")
PLACEHOLDER = os.path.join(PLUGIN_PATH, "background.png")

# ============================================================
# WEBCAM PLAYLIST PLAYER SA MINI SKIN-om (kao u CiefpYouTube)
# ============================================================
class WebcamPlaylistPlayer(Screen):
    """Mini player za webcam plejlistu - automatsko prebacivanje"""
    
    def __init__(self, session, playlist, start_index=0, bouquet_name=""):
        # Učitaj podešavanja za alpha vrednost (transparentnost)
        alpha_hex = self.get_mini_skin_opacity()
        
        self.skin = f"""
        <screen position="0,0" size="1920,160" title="CiefpVideoPlayer WebCam" backgroundColor="#ff000000" flags="wfNoBorder">
            <eLabel position="0,0" size="1920,160" backgroundColor="#{alpha_hex}00000e" zPosition="1" />
            <eLabel text="NOW PLAYING:" position="50,20" size="180,40" font="Regular;22" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" />
            <widget name="title" position="240,15" size="1630,50" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#{alpha_hex}00000e" transparent="1" zPosition="2" />
            <eLabel text="NEXT:" position="50,75" size="180,40" font="Regular;20" foregroundColor="#ffffff" backgroundColor="#00000000" transparent="1" zPosition="2" />
            <widget name="next_title" position="240,72" size="1200,40" font="Regular;24" foregroundColor="#ffcc00" backgroundColor="#{alpha_hex}00000e" transparent="1" zPosition="2" />
            <widget name="playlist_info" position="50,120" size="300,30" font="Regular;22" foregroundColor="#00ffcc" backgroundColor="transparent" transparent="1" zPosition="2" />
            <widget name="bouquet_name" position="800,20" size="1000,30" font="Regular;24" halign="right" foregroundColor="#ffffff" backgroundColor="transparent" transparent="1" zPosition="2" />
            <widget name="status" position="900,120" size="500,30" font="Regular;22" halign="right" foregroundColor="#ffcc00" backgroundColor="transparent" transparent="1" zPosition="2" />    
            <widget name="controls" position="240,120" size="700,30" font="Regular;22" foregroundColor="#03fc1c" backgroundColor="#{alpha_hex}00000e" transparent="1" zPosition="2" />
            <widget name="time" position="1600,110" size="300,50" font="Regular;36" halign="right" foregroundColor="#ffffff" backgroundColor="transparent" transparent="1" zPosition="2"/>
        </screen>
        """
        
        Screen.__init__(self, session)
        self.session = session
        self.playlist = playlist
        self.index = start_index
        self.bouquet_name = bouquet_name
        self.webcam_timeout = self.load_webcam_timeout()
        self.auto_switch_timer = None
        self.countdown_timer = None
        self.countdown = self.webcam_timeout
        self.is_paused = False
        self.is_loading = False
        self.pending_next_title = ""
        
        self["title"] = Label("Loading...")
        self["next_title"] = Label("")
        self["status"] = Label("")
        self["playlist_info"] = Label("")
        self["controls"] = Label(f"🔴 WEBCAM | Auto-switch: {self.webcam_timeout}s | OK: Pause | ▲/▼: Skip | EXIT: Exit")
        self["time"] = Label("")
        self["bouquet_name"] = Label(bouquet_name[:100] if len(bouquet_name) > 100 else bouquet_name)
        
        self["actions"] = ActionMap(["SetupActions", "DirectionActions"], {
            "cancel": self.handleExit,
            "ok": self.pauseToggle,
            "down": self.nextVideo,
            "up": self.prevVideo
        }, -1)
        
        self.time_timer = eTimer()
        self.time_timer.callback.append(self.updateTime)
        self.time_timer.start(1000)
        
        self.onLayoutFinish.append(self.startExtraction)
    
    def get_mini_skin_opacity(self):
        """Učitava transparentnost mini skin-a"""
        opacity_map = {
            '100': 'FF', '90': 'E6', '80': 'CC', '70': 'B3',
            '60': '99', '50': '80', '40': '66', '30': '4D',
            '20': '33', '10': '1A', '0': '00',
        }
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    opacity = data.get('mini_skin_opacity', '50')
                    return opacity_map.get(str(opacity), '80')
        except:
            pass
        return '80'
    
    def load_webcam_timeout(self):
        """Učitava vreme trajanja webcam-a"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    return int(data.get('display_duration', 15))
        except:
            pass
        return 15
    
    def updateTime(self):
        try:
            import time
            self["time"].setText(time.strftime("%H:%M:%S"))
        except:
            pass
    
    def startExtraction(self):
        """Pokreće učitavanje trenutnog webcam-a"""
        if self.auto_switch_timer:
            self.auto_switch_timer.stop()
        if self.countdown_timer:
            self.countdown_timer.stop()
        
        if self.index >= len(self.playlist):
            # Kraj plejliste - vrati se na početak ili zatvori
            self.handleExit()
            return
        
        current_video = self.playlist[self.index]
        url = current_video.get('url')
        title = current_video.get('title', 'Camera')
        
        self["title"].setText(f"⏳ Loading: {title}...")
        self["status"].setText("Loading stream...")
        self.is_loading = True
        
        # Pripremi sledeći naziv
        if self.index + 1 < len(self.playlist):
            self.pending_next_title = self.playlist[self.index + 1].get('title', '')
        else:
            self.pending_next_title = "End of playlist"
        
        self["playlist_info"].setText(f"Camera: {self.index + 1} of {len(self.playlist)}")
        
        # Direktno pusti URL (ne treba yt-dlp za obične stream-ove)
        self.playVideoDirect(url, title)

    def playVideoDirect(self, video_url, title):
        """Pušta video - koristi odgovarajući servicetype"""
        try:
            print(f"[WebcamPlayer] Playing URL: {video_url}")
            print(f"[WebcamPlayer] Title: {title}")

            # Dobij servicetype iz trenutnog item-a
            current_video = self.playlist[self.index]
            servicetype = current_video.get('servicetype', 5002)

            print(f"[WebcamPlayer] Using servicetype: {servicetype}")

            # Koristi odgovarajući servicetype
            ref = eServiceReference(servicetype, 0, video_url)
            ref.setName(title)
            self.session.nav.playService(ref)

            self["title"].setText(title)
            self["next_title"].setText(self.pending_next_title)
            self["status"].setText("")
            self.is_loading = False

            self.start_auto_switch_timer()

        except Exception as e:
            print(f"[WebcamPlayer] Error with {servicetype}: {e}")
            # Fallback na 4097
            try:
                print("[WebcamPlayer] Fallback to 4097")
                ref = eServiceReference(4097, 0, video_url)
                ref.setName(title)
                self.session.nav.playService(ref)
                self.start_auto_switch_timer()
            except Exception as e2:
                print(f"[WebcamPlayer] Fallback failed: {e2}")
                self.is_loading = False
                self.showError(str(e2)[:30])

    def start_auto_switch_timer(self):
        """Pokreće timer za automatsko prebacivanje na sledeći webcam"""
        if self.auto_switch_timer:
            self.auto_switch_timer.stop()
        if self.countdown_timer:
            self.countdown_timer.stop()
        
        self.countdown = self.webcam_timeout
        
        # Timer za countdown prikaz
        self.countdown_timer = eTimer()
        self.countdown_timer.callback.append(self.update_countdown)
        self.countdown_timer.start(1000)
        
        # Timer za prebacivanje
        self.auto_switch_timer = eTimer()
        self.auto_switch_timer.callback.append(self.auto_switch_callback)
        self.auto_switch_timer.start(self.webcam_timeout * 1000, True)
    
    def update_countdown(self):
        """Ažurira prikaz odbrojavanja"""
        if self.is_paused or self.is_loading:
            return
        if self.countdown > 0:
            self.countdown -= 1
            self["status"].setText(f"Next camera in: {self.countdown}s")
        else:
            if self.countdown_timer:
                self.countdown_timer.stop()
    
    def auto_switch_callback(self):
        """Callback za automatsko prebacivanje"""
        if self.is_paused or self.is_loading:
            return
        self.nextVideo()
    
    def nextVideo(self):
        """Sledeći video u plejlisti"""
        if self.is_loading:
            return
        
        if self.auto_switch_timer:
            self.auto_switch_timer.stop()
        if self.countdown_timer:
            self.countdown_timer.stop()
        self.is_paused = False
        
        if self.index < len(self.playlist) - 1:
            self.index += 1
        else:
            # Kraj plejliste - zatvori
            self.handleExit()
            return
        
        self.startExtraction()
    
    def prevVideo(self):
        """Prethodni video u plejlisti"""
        if self.is_loading:
            return
        
        if self.auto_switch_timer:
            self.auto_switch_timer.stop()
        if self.countdown_timer:
            self.countdown_timer.stop()
        self.is_paused = False
        
        if self.index > 0:
            self.index -= 1
        else:
            # Ako si na prvom, idi na poslednji
            self.index = len(self.playlist) - 1
        
        self.startExtraction()
    
    def pauseToggle(self):
        """Pauzira/pokreće trenutni video i zaustavlja timer"""
        try:
            service = self.session.nav.getCurrentService()
            if service and hasattr(service, 'pause'):
                service.pause()
                self.is_paused = not self.is_paused
                if self.is_paused:
                    if self.auto_switch_timer:
                        self.auto_switch_timer.stop()
                    if self.countdown_timer:
                        self.countdown_timer.stop()
                    self["controls"].setText("🔴 WEBCAM PAUSED | OK: Resume | ▲/▼: Skip | EXIT: Exit")
                    self["status"].setText("PAUSED")
                else:
                    self.start_auto_switch_timer()
                    self["controls"].setText(f"🔴 WEBCAM | Auto-switch: {self.webcam_timeout}s | OK: Pause | ▲/▼: Skip | EXIT: Exit")
        except Exception as e:
            print(f"[WebcamPlayer] Pause error: {e}")
    
    def showError(self, error_msg):
        """Prikazuje grešku i preskače"""
        self["title"].setText(f"Error: {error_msg}. Skipping...")
        self.is_loading = False
        self.nextVideo()
    
    def handleExit(self):
        """Izlaz i čišćenje"""
        if self.auto_switch_timer:
            self.auto_switch_timer.stop()
        if self.countdown_timer:
            self.countdown_timer.stop()
        if self.time_timer:
            self.time_timer.stop()
        self.session.nav.stopService()
        self.close()


# ============================================================
# GLAVNI WEBCAM PLAYER EKRAN
# ============================================================
class WebcamPlayer(Screen):
    """Glavni ekran za pregled webcam buketa"""
    
    skin = """
    <screen name="WebcamPlayer" position="0,0" size="1920,1080" title="Webcam Player" backgroundColor="#00240e" flags="wfNoBorder">
        <eLabel position="0,0" size="1920,100" backgroundColor="#1a1a1a" zPosition="-1" />
        <eLabel text="..:: CiefpVideoPlayer ::.." position="60,25" size="600,50" font="Regular;40" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" />
        <widget name="webcam_list" position="60,150" size="1000,750" scrollbarMode="showOnDemand" itemHeight="50" font="Regular;32" foregroundColor="#ffffff" backgroundColor="#101010" transparent="1" />
        <widget name="status" position="60,950" size="1000,50" font="Regular;28" foregroundColor="#f0f0f0" backgroundColor="#101010" transparent="1" halign="left" />
        <widget name="time" position="1650,25" size="200,50" font="Regular;36" halign="right" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="1"/>
        <widget name="poster_placeholder" position="1150,150" size="700,750" alphatest="blend" zPosition="1" />
        <widget name="selection_info" position="1150,910" size="700,50" font="Regular;30" halign="center" foregroundColor="#00FF00" transparent="1" />
        <eLabel position="0,980" size="1920,100" backgroundColor="#1a1a1a" zPosition="1" />
        <eLabel position="60,1015" size="30,30" backgroundColor="red" zPosition="2" />
        <eLabel text="Exit" position="105,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
        <eLabel position="300,1015" size="30,30" backgroundColor="green" zPosition="2" />
        <eLabel text="Settings" position="345,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
        <eLabel position="510,1015" size="30,30" backgroundColor="yellow" zPosition="2" />
        <eLabel text="Play All" position="555,1010" size="200,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
    </screen>
    """

    def __init__(self, session, bouquet_path, bouquet_name):
        Screen.__init__(self, session)
        self.session = session
        self.bouquet_path = bouquet_path
        self.bouquet_name = bouquet_name
        self.webcam_items = []
        
        # Učitaj podešavanja
        self.settings = self.load_settings()
        
        self["webcam_list"] = MenuList([])
        self["status"] = Label("Loading webcams...")
        self["time"] = Label("")
        self["poster_placeholder"] = Pixmap()
        self["selection_info"] = Label("Webcam: " + bouquet_name)
        
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
            "ok": self.okClicked,
            "cancel": self.close,
            "red": self.close,
            "green": self.openSettings,
            "yellow": self.playAll,
            "up": self.moveUp,
            "down": self.moveDown,
        }, -1)
        
        self.time_timer = eTimer()
        self.time_timer.callback.append(self.updateTime)
        self.time_timer.start(1000)
        
        self.onLayoutFinish.append(self.showDefaultImage)
        self.onLayoutFinish.append(self.loadWebcamList)
    
    def updateTime(self):
        import time
        self["time"].setText(time.strftime("%H:%M:%S"))
    
    def showDefaultImage(self):
        if os.path.exists(PLACEHOLDER):
            self["poster_placeholder"].instance.setPixmap(LoadPixmap(PLACEHOLDER))
    
    def load_settings(self):
        """Učitava podešavanja iz config fajla"""
        default_settings = {
            "display_duration": 15,
            "mini_skin_opacity": "50"
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    settings = json.load(f)
                    return settings
            except:
                pass
        
        return default_settings
    
    def save_settings(self):
        """Čuva podešavanja"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except:
            pass

    def loadWebcamList(self):
        """Učitava webcam kanale iz bouquet fajla - čuva i markere i kamere"""
        try:
            if not os.path.exists(self.bouquet_path):
                self["status"].setText(f"File not found: {self.bouquet_path}")
                return

            with open(self.bouquet_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f.readlines()]

            self.webcam_items = []  # Lista za prikaz (sa markerima)
            self.playlist_items = []  # Lista za puštanje (samo kamere)
            current_category = ""

            i = 0
            while i < len(lines):
                line = lines[i]

                if not line:
                    i += 1
                    continue

                # Prepoznaj kategorije (markeri)
                if line.startswith("#SERVICE 1:64:") or "====" in line:
                    if i + 1 < len(lines) and lines[i + 1].startswith("#DESCRIPTION"):
                        current_category = lines[i + 1].replace("#DESCRIPTION", "").strip()
                        # Dodaj marker u listu za prikaz
                        self.webcam_items.append({
                            "is_marker": True,
                            "name": f"📁 {current_category}",
                            "category": current_category
                        })
                        print(f"[WebcamPlayer] Marker: {current_category}")
                    i += 2
                    continue

                # Podrška za SERVICE 5002: format
                if line.startswith("#SERVICE 5002:"):
                    parts = line.split(':')
                    url = ""
                    name = ""

                    if len(parts) >= 11:
                        raw_url = parts[-1]
                        try:
                            from urllib.parse import unquote
                            url = unquote(raw_url)
                        except:
                            url = raw_url.replace("%3a", ":").replace("%2f", "/")

                    if i + 1 < len(lines) and lines[i + 1].startswith("#DESCRIPTION"):
                        desc_line = lines[i + 1]
                        name = desc_line.replace("#DESCRIPTION", "").strip()
                        try:
                            from urllib.parse import unquote
                            name = unquote(name)
                        except:
                            name = name.replace("%20", " ")
                        i += 1

                    if not name and url:
                        name = url.split('/')[-1].replace('.m3u8', '').replace('_', ' ')

                    if url and not self.is_youtube_url(url):
                        # Dodaj u listu za prikaz (sa ikonicom)
                        self.webcam_items.append({
                            "is_marker": False,
                            "name": f"🎥 {name}",
                            "url": url,
                            "title": name,
                            "category": current_category,
                            "servicetype": 5002
                        })
                        # Dodaj u listu za puštanje (samo čisto ime, bez markera)
                        self.playlist_items.append({
                            "name": name,
                            "url": url,
                            "title": name,
                            "category": current_category,
                            "servicetype": 5002
                        })
                        print(f"[WebcamPlayer] Added cam: {name[:50]}")

                # Podrška za SERVICE 4097: format
                if line.startswith("#SERVICE 4097:"):
                    parts = line.split(':')
                    url = ""
                    name = ""

                    if len(parts) >= 12:
                        raw_url = parts[10]
                        name_raw = parts[11] if len(parts) > 11 else ""
                        try:
                            from urllib.parse import unquote
                            url = unquote(raw_url)
                            name = unquote(name_raw)
                        except:
                            url = raw_url.replace("%3a", ":").replace("%2f", "/")
                            name = name_raw.replace("%20", " ")
                    elif len(parts) >= 11:
                        raw_url = parts[10]
                        try:
                            from urllib.parse import unquote
                            url = unquote(raw_url)
                        except:
                            url = raw_url.replace("%3a", ":").replace("%2f", "/")

                    if (not name or name == "Nepoznato") and i + 1 < len(lines) and lines[i + 1].startswith(
                            "#DESCRIPTION"):
                        desc_line = lines[i + 1]
                        name = desc_line.replace("#DESCRIPTION", "").strip()
                        try:
                            from urllib.parse import unquote
                            name = unquote(name)
                        except:
                            name = name.replace("%20", " ")
                        i += 1

                    if not name and url:
                        name = url.split('/')[-1].replace('.m3u8', '').replace('.ts', '').replace('_', ' ')
                        if '?' in name:
                            name = name.split('?')[0]

                    if len(name) > 100:
                        name = name[:97] + "..."

                    if url and not self.is_youtube_url(url):
                        # Dodaj u listu za prikaz
                        self.webcam_items.append({
                            "is_marker": False,
                            "name": f"🎥 {name}",
                            "url": url,
                            "title": name,
                            "category": current_category,
                            "servicetype": 4097
                        })
                        # Dodaj u listu za puštanje
                        self.playlist_items.append({
                            "name": name,
                            "url": url,
                            "title": name,
                            "category": current_category,
                            "servicetype": 4097
                        })
                        print(f"[WebcamPlayer] Added cam: {name[:50]}")

                i += 1

            if self.playlist_items:
                self.updateList()
                self["status"].setText(
                    f"Found {len(self.playlist_items)} webcams, {len([x for x in self.webcam_items if x.get('is_marker', False)])} categories (YouTube ignored)")
            else:
                self["status"].setText("No webcam links found")
                self.session.open(MessageBox,
                                  f"No valid webcam links found!\n\nFile: {self.bouquet_path}",
                                  MessageBox.TYPE_INFO)

        except Exception as e:
            print(f"[WebcamPlayer] Error: {e}")
            import traceback
            traceback.print_exc()
            self["status"].setText(f"Error: {str(e)[:50]}")

    def updateList(self):
        """Ažurira prikaz liste - prikazuje i markere i kamere"""
        menu_list = []
        for item in self.webcam_items:
            menu_list.append(item['name'])
        self["webcam_list"].setList(menu_list)

    def okClicked(self):
        """Kada korisnik klikne OK na stavku u listi"""
        current = self["webcam_list"].getCurrent()
        if not current:
            return

        idx = self["webcam_list"].getSelectedIndex()
        if idx >= 0 and idx < len(self.webcam_items):
            item = self.webcam_items[idx]

            # Ako je marker (kategorija), ne radi ništa ili preskoči
            if item.get('is_marker', False):
                # Možeš dodati opciju da se preskoči na prvu kameru u kategoriji
                self["status"].setText(f"Category: {item['name']} - select a camera below")
                return

            # Inače, prikaži meni za kameru
            choices = [
                ("▶ Play Single File", "single"),
                ("▶▶ Play Playlist (All)", "playlist_all"),
                ("▶ Play from here (Playlist)", "playlist_from_here"),
                ("⚙ Settings (Duration)", "settings"),
            ]

            self.session.openWithCallback(
                self.webcamMenuSelected,
                ChoiceBox,
                title=f"Webcam: {item['title']}",
                list=choices
            )

    def webcamMenuSelected(self, choice):
        if not choice:
            return

        action = choice[1]
        current_idx = self["webcam_list"].getSelectedIndex()

        # Pronađi pravi indeks u playlist_items (samo kamere, bez markera)
        # Treba da preskočimo markere da bi dobili odgovarajući indeks u playlist_items

        if action == "single":
            # Pronađi odgovarajuću kameru u playlist_items
            selected_item = self.webcam_items[current_idx]
            if not selected_item.get('is_marker', False):
                # Ovo je kamera, nađi njen indeks u playlist_items
                for i, cam in enumerate(self.playlist_items):
                    if cam['url'] == selected_item['url']:
                        single_playlist = [self.playlist_items[i]]
                        self.session.open(WebcamPlaylistPlayer, single_playlist, 0, self.bouquet_name)
                        break

        elif action == "playlist_all":
            # Pusti celu plejlistu (samo kamere, bez markera)
            self.session.open(WebcamPlaylistPlayer, self.playlist_items, 0, self.bouquet_name)

        elif action == "playlist_from_here":
            # Pusti plejlistu od trenutne pozicije (preskoči markere)
            selected_item = self.webcam_items[current_idx]
            if not selected_item.get('is_marker', False):
                for i, cam in enumerate(self.playlist_items):
                    if cam['url'] == selected_item['url']:
                        self.session.open(WebcamPlaylistPlayer, self.playlist_items, i, self.bouquet_name)
                        break
            else:
                # Ako je marker, počni od prve kamere u toj kategoriji
                self.session.open(WebcamPlaylistPlayer, self.playlist_items, 0, self.bouquet_name)

        elif action == "settings":
            self.openSettings()

    def playAll(self):
        """Žuti taster - pusti sve webcam-ove (samo kamere, bez markera)"""
        if self.playlist_items:
            self.session.open(WebcamPlaylistPlayer, self.playlist_items, 0, self.bouquet_name)
        else:
            self["status"].setText("No webcams to play")

    def alternative_parse(self, lines):
        """Alternativni parser za različite formate"""
        items = []

        for i, line in enumerate(lines):
            if "#SERVICE" in line and ("http" in line or "m3u8" in line):
                url = ""
                name = ""
                servicetype = 4097

                # Odredi servicetype
                if "5002" in line:
                    servicetype = 5002

                # Pokušaj naći URL
                import re
                url_match = re.search(r'(https?://[^\s\'":]+)', line)
                if url_match:
                    url = url_match.group(1)
                    url = url.replace('%3a', ':').replace('%2f', '/')

                # Pokušaj naći ime
                if i + 1 < len(lines) and "#DESCRIPTION" in lines[i + 1]:
                    desc_line = lines[i + 1]
                    name = desc_line.replace("#DESCRIPTION", "").strip()
                    try:
                        from urllib.parse import unquote
                        name = unquote(name)
                    except:
                        pass

                if not name and url:
                    name = url.split('/')[-1].replace('.m3u8', '').replace('_', ' ')

                if url and not self.is_youtube_url(url) and name:
                    items.append({
                        "name": name,
                        "url": url,
                        "title": name,
                        "servicetype": servicetype
                    })
                    print(f"[WebcamPlayer] Alt parser added: {name[:50]}")

        return items

    def is_youtube_url(self, url):
        """Proverava da li je URL YouTube link"""
        youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com', 'yewtu.be', 'invidious']
        url_lower = url.lower()
        for domain in youtube_domains:
            if domain in url_lower:
                return True
        return False

    def moveUp(self):
        self["webcam_list"].up()
    
    def moveDown(self):
        self["webcam_list"].down()

    def openSettings(self):
        """Zeleni taster - otvara podešavanja"""
        current_duration = self.settings.get("display_duration", 15)
        current_opacity = self.settings.get("mini_skin_opacity", "50")
        
        choices = [
            ("═" * 30, "separator"),
            (f"▶ Duration: {current_duration} seconds", "duration"),
            (f"▶ Mini Skin Opacity: {current_opacity}%", "opacity"),
            ("═" * 30, "separator"),
            ("15 seconds", 15),
            ("20 seconds", 20),
            ("25 seconds", 25),
            ("30 seconds", 30),
            ("40 seconds", 40),
            ("60 seconds", 60),
            ("═" * 30, "separator"),
            ("Opacity: 100%", "opacity_100"),
            ("Opacity: 80%", "opacity_80"),
            ("Opacity: 50%", "opacity_50"),
            ("Opacity: 30%", "opacity_30"),
            ("Opacity: 20%", "opacity_20"),
        ]
        
        self.session.openWithCallback(
            self.settingsSelected,
            ChoiceBox,
            title="Webcam Player Settings",
            list=choices
        )
    
    def settingsSelected(self, choice):
        if not choice or choice[1] == "separator":
            return
        
        action = choice[1]
        
        if action == "duration":
            # Već prikazano u listi
            pass
        elif isinstance(action, int):
            self.settings["display_duration"] = action
            self.save_settings()
            self.session.open(MessageBox, f"Duration set to {action} seconds", MessageBox.TYPE_INFO)
            self["status"].setText(f"Duration: {action}s")
        elif action.startswith("opacity_"):
            opacity = action.split("_")[1]
            self.settings["mini_skin_opacity"] = opacity
            self.save_settings()
            self.session.open(MessageBox, f"Mini skin opacity set to {opacity}%", MessageBox.TYPE_INFO)
            self["status"].setText(f"Opacity: {opacity}%")
    
    def close(self):
        if self.time_timer:
            self.time_timer.stop()
        Screen.close(self)