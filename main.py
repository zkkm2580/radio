import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.core.text import LabelBase
from kivy.utils import platform

# 1. 字体安全加载：优先加载本地 font.ttf，找不到则回退到系统字体，避免崩溃
font_path = 'font.ttf'
if not os.path.exists(font_path) and platform == 'android':
    for sys_font in ['/system/fonts/NotoSansSC-Regular.otf', '/system/fonts/DroidSansFallback.ttf']:
        if os.path.exists(sys_font):
            font_path = sys_font
            break

if os.path.exists(font_path):
    LabelBase.register(name='Chinese', fn_regular=font_path)
    DEFAULT_FONT = 'Chinese'
else:
    DEFAULT_FONT = None


class RadioPlayer(App):

    def build(self):
        # 初始化播放器
        self.init_player()

        root = BoxLayout(orientation='vertical')

        self.input = TextInput(
            hint_text='输入流媒体 URL（MP3 / M3U8 / 直播流）',
            size_hint_y=None,
            height=80,
            font_size=26,
            font_name=DEFAULT_FONT if DEFAULT_FONT else None,
            multiline=False
        )

        btn_bar = BoxLayout(size_hint_y=None, height=80)

        btn_add = Button(text='添加', font_size=26, font_name=DEFAULT_FONT if DEFAULT_FONT else None)
        btn_add.bind(on_press=self.add_url)

        btn_import = Button(text='导入 M3U', font_size=26, font_name=DEFAULT_FONT if DEFAULT_FONT else None)
        btn_import.bind(on_press=self.import_m3u)

        btn_bar.add_widget(btn_add)
        btn_bar.add_widget(btn_import)

        self.list_box = BoxLayout(orientation='vertical', size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))

        scroll = ScrollView()
        scroll.add_widget(self.list_box)

        root.add_widget(self.input)
        root.add_widget(btn_bar)
        root.add_widget(scroll)

        self.load_playlist()
        return root

    def get_playlist_path(self):
        # 使用安全的 App 私有存储目录
        return os.path.join(self.user_data_dir, 'playlist.txt')

    def init_player(self):
        if platform == 'android':
            from jnius import autoclass, PythonJavaClass, java_method
            MediaPlayer = autoclass('android.media.MediaPlayer')
            self.player = MediaPlayer()

            class PreparedListener(PythonJavaClass):
                __javainterfaces__ = ['android/media/MediaPlayer$OnPreparedListener']
                __javacontext__ = 'app'

                def __init__(self, start_callback):
                    super(PreparedListener, self).__init__()
                    self.start_callback = start_callback

                @java_method('(Landroid/media/MediaPlayer;)V')
                def onPrepared(self, mp):
                    self.start_callback(mp)

            self.prepared_listener = PreparedListener(lambda mp: mp.start())
            self.player.setOnPreparedListener(self.prepared_listener)
        else:
            self.player = None

    def play(self, url):
        if platform == 'android' and self.player:
            try:
                self.player.reset()
                self.player.setDataSource(url)
                self.player.prepareAsync()
            except Exception as e:
                print(f"Playback error: {e}")
        else:
            print(f"[PC 预览模拟] 正在播放: {url}")

    def add_url(self, instance):
        url = self.input.text.strip()
        if url:
            self.add_item(url)
            self.save_url(url)
            self.input.text = ''

    def add_item(self, url):
        btn = Button(
            text=url,
            size_hint_y=None,
            height=80,
            font_size=22
        )
        btn.bind(on_press=lambda x: self.play(url))
        self.list_box.add_widget(btn)

    def save_url(self, url):
        with open(self.get_playlist_path(), 'a', encoding='utf-8') as f:
            f.write(url + '\n')

    def load_playlist(self):
        path = self.get_playlist_path()
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if url:
                    self.add_item(url)

    def import_m3u(self, instance):
        path = '/sdcard/playlist.m3u'
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    self.add_item(line)
                    self.save_url(line)


if __name__ == '__main__':
    RadioPlayer().run()