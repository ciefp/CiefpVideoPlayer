import os
import threading
from ftplib import FTP
from twisted.internet import reactor
from Tools.LoadPixmap import LoadPixmap
from Screens.Screen import Screen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.MenuList import MenuList
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from enigma import eServiceReference
from Screens.InfoBar import MoviePlayer

PLUGIN_PATH = "/usr/lib/enigma2/python/Plugins/Extensions/CiefpVideoPlayer"
PLACEHOLDER = os.path.join(PLUGIN_PATH, "background.png")

class CiefpFTPBrowser(Screen):
    # Tvoj originalni skin
    skin = """
    <screen name="CiefpFTPBrowser" position="0,0" size="1920,1080" title="Ciefp FTP Phone Browser" backgroundColor="#00240e" flags="wfNoBorder">
        <eLabel position="0,0" size="1920,100" backgroundColor="#1a1a1a" zPosition="-1" />
        <widget source="Title" render="Label" position="70,45" size="1000,60" font="Regular;40" foregroundColor="#ffffff" backgroundColor="#101010" transparent="1" />
        <widget name="status" position="70,950" size="1000,50" font="Regular;28" foregroundColor="#f0f0f0" backgroundColor="#101010" transparent="1" halign="left" />
        <widget name="filelist" position="60,150" size="1000,750" itemHeight="50" scrollbarMode="showOnDemand" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#101010" transparent="1" />
        <widget name="poster_placeholder" position="1150,150" size="700,750" alphatest="blend" zPosition="1" />
        <eLabel position="0,980" size="1920,100" backgroundColor="#1a1a1a" zPosition="1" />
        <eLabel position="60,1015" size="30,30" backgroundColor="red" zPosition="2" />
        <eLabel text="Exit" position="105,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
        <eLabel position="300,1015" size="30,30" backgroundColor="green" zPosition="2" />
        <eLabel text="OK" position="345,1010" size="150,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#1a1a1a" transparent="1" zPosition="2" />
        <widget source="session.CurrentService" render="Label" position="1050,140" size="800,80" font="Regular;35" foregroundColor="#e5b24b" backgroundColor="#101010" transparent="1" halign="center" />
    </screen>
    """

    def __init__(self, session, ftp_ip, ftp_port, ftp_user, ftp_pass):
        Screen.__init__(self, session)
        self.session = session
        self.cache_list = [] # Lista za praćenje skinutih fajlova
        self.cleanCache() # Očisti staro pri pokretanju
        self.ftp_ip = ftp_ip
        self.ftp_port = ftp_port
        self.ftp_user = ftp_user
        self.ftp_pass = ftp_pass
        self.current_path = "/" # Početna putanja na Androidu
        
        self["status"] = Label("Connecting to phone...")
        self["filelist"] = MenuList([]) # Koristimo MenuList za FTP
        self["poster_placeholder"] = Pixmap()
        
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"],
        {
            "ok": self.okClicked,
            "cancel": self.close,
            "red": self.close,
            "green": self.okClicked,
            "up": self.up,
            "down": self.down,
            "left": self.left,
            "right": self.right
        }, -1)

        self.onLayoutFinish.append(self.showDefaultImage)
        self.onLayoutFinish.append(self.startFtpConnect)

    def showDefaultImage(self):
        if os.path.exists(PLACEHOLDER):
            self["poster_placeholder"].instance.setPixmap(LoadPixmap(PLACEHOLDER))

    def startFtpConnect(self):
        # Pokrećemo u novom thread-u da ne koči UI
        thread = threading.Thread(target=self.getFtpFiles)
        thread.daemon = True
        thread.start()

    def getFtpFiles(self):
        try:
            ftp = FTP()
            ftp.connect(self.ftp_ip, int(self.ftp_port), timeout=10)
            ftp.login(self.ftp_user, self.ftp_pass)
            ftp.cwd(self.current_path)
            
            lines = []
            ftp.dir(lines.append)
            
            items = []
            if self.current_path != "/":
                items.append((".. (Back to previous folder)", "parent", True))

            for line in lines:
                is_dir = line.startswith('d')
                name = line.split(None, 8)[-1]
                
                if is_dir:
                    items.append(("📂 " + name, name, True))
                else:
                    if name.lower().endswith(('.mp4', '.mkv', '.avi', '.mov')):
                        items.append(("🎬 " + name, name, False))
            
            ftp.quit()
            reactor.callFromThread(self.updateUI, items)
        except Exception as e:
            reactor.callFromThread(self.showError, str(e))

    def updateUI(self, items):
        self["filelist"].setList(items)
        self["status"].setText("Path: %s" % self.current_path)

    def showError(self, error):
        self["status"].setText("FTP Error: %s" % error)

    def okClicked(self):
        selection = self["filelist"].getCurrent()
        if not selection:
            return

        display_name, name, is_dir = selection

        if is_dir:
            if name == "parent":
                parts = self.current_path.strip("/").split("/")
                self.current_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
            else:
                self.current_path = (self.current_path + "/" + name).replace("//", "/")
            
            self["status"].setText("Loading...")
            self.startFtpConnect()
        else:
            self.playFtpVideo(name)

    def playFtpVideo(self, filename):
        # 1. Provera prioriteta skladištenja (USB -> HDD -> TMP)
        download_folder = "/tmp/"
        if os.path.exists("/media/usb") and os.path.ismount("/media/usb"):
            download_folder = "/media/usb/"
            self["status"].setText("Downloading to USB...")
        elif os.path.exists("/media/hdd") and os.path.ismount("/media/hdd"):
            download_folder = "/media/hdd/"
            self["status"].setText("Downloading to HDD...")
        else:
            self["status"].setText("No USB/HDD! Downloading to /tmp...")

        self.local_file = os.path.join(download_folder, filename)
        self.ftp_path = (self.current_path + "/" + filename).replace("//", "/")

        # 2. Pokretanje download-a u pozadini
        thread = threading.Thread(target=self.downloadAndPlayTask)
        thread.daemon = True
        thread.start()

    def downloadAndPlayTask(self):
        try:
            ftp = FTP()
            ftp.connect(self.ftp_ip, int(self.ftp_port), timeout=15)
            ftp.login(self.ftp_user, self.ftp_pass)

            # Dodajemo fajl u listu za čišćenje nakon gledanja
            if self.local_file not in self.cache_list:
                self.cache_list.append(self.local_file)

            # Stvarno preuzimanje fajla na izabranu lokaciju
            with open(self.local_file, 'wb') as f:
                ftp.retrbinary('RETR ' + self.ftp_path, f.write)

            ftp.quit()

            # Kada je preuzimanje 100% gotovo, pokreni plejer u glavnom thread-u
            reactor.callFromThread(self.startLocalPlayer)

        except Exception as e:
            reactor.callFromThread(self.showError, "Download failed: " + str(e))

    def downloadAndPlay(self):
        try:
            ftp = FTP()
            ftp.connect(self.ftp_ip, int(self.ftp_port), timeout=10)
            ftp.login(self.ftp_user, self.ftp_pass)
            self.cache_list.append(self.local_file) # Zapamti šta si skinuo

            # 1. Provera i download titla (SRT)
            subtitle_exts = [".srt", ".txt"]
            base_name = os.path.splitext(self.ftp_path)[0]

            for ext in subtitle_exts:
                try:
                    srt_path = base_name + ext
                    local_srt = os.path.splitext(self.local_file)[0] + ext

                    # Proveravamo da li titl postoji na serveru
                    if srt_path in ftp.nlst(os.path.dirname(srt_path)):
                        with open(local_srt, 'wb') as f:
                            ftp.retrbinary('RETR ' + srt_path, f.write)
                        self.cache_list.append(local_srt)  # Dodajemo u listu za brisanje
                except:
                    continue  # Ako titl ne postoji, samo nastavi dalje

            # Otvaramo lokalni fajl na USB-u za pisanje
            with open(self.local_file, 'wb') as f:
                ftp.retrbinary('RETR ' + self.ftp_path, f.write)

            ftp.quit()

            # Kada je download gotov, puštamo lokalni fajl
            from twisted.internet import reactor
            reactor.callFromThread(self.startLocalPlayer)

        except Exception as e:
            from twisted.internet import reactor
            reactor.callFromThread(self.showError, "Download failed: " + str(e))

    def startLocalPlayer(self):
        ref = eServiceReference(4097, 0, self.local_file)
        ref.setName("Phone Video: " + os.path.basename(self.local_file))

        # Otvori plejer i dodaj callback da obriše fajl čim se plejer zatvori
        player = self.session.openWithCallback(self.cleanCache, MoviePlayer, ref)

    def cleanCache(self):
        try:
            import os
            for f in self.cache_list:
                if os.path.exists(f):
                    # Brisanje glavnog video fajla
                    os.remove(f)

                    # Brisanje pratećih Enigma2 fajlova koji prljaju USB/TMP
                    base_name = os.path.splitext(f)[0]
                    extensions_to_clean = [".cuts", ".ap", ".sc", ".meta"]

                    for ext in extensions_to_clean:
                        extra_file = base_name + ext
                        if os.path.exists(extra_file):
                            os.remove(extra_file)

            # Resetovanje liste nakon čišćenja
            self.cache_list = []
        except Exception as e:
            print
            "[Ciefp FTP] Cache clean error: %s" % str(e)

    def up(self):
        self["filelist"].up()

    def down(self):
        self["filelist"].down()

    def left(self):
        self["filelist"].pageUp()

    def right(self):
        self["filelist"].pageDown()