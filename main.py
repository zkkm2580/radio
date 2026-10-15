import os
import sys
import traceback
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.core.text import LabelBase
from kivy.utils import platform

# 1. 字体安全注册：优先使用同目录自带的 font.ttf
DEFAULT_FONT = None
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bundled_font = os.path.join(current_dir, 'font.ttf')
    if os.path.exists(bundled_font):
        LabelBase.register(name='Chinese', fn_regular=bundled_font)
        DEFAULT_FONT = 'Chinese'
    elif platform == 'android':
        for sys_font in ['/system/fonts/NotoSansSC-Regular.otf', '/system/fonts/DroidSansFallback.ttf']:
            if os.path.exists(sys_font):
                LabelBase.register(name='Chinese', fn_regular=sys_font)
                DEFAULT_FONT = 'Chinese'
                break
except Exception as e:
    print(f"Font registration warning: {e}")


class RadioPlayer(App):

    def build(self):
        try:
            return self._build_ui()
        except Exception as e:
            # 极限兜底：如果构建 UI 出现任何不可预见异常，展示错误信息而不是闪退
            err_box = BoxLayout(orientation='vertical')
            err_label = Label(text=f"Startup Error:\n{traceback.format_exc()}", font_size=18)
            err_box.add_widget(err_label)
            return err_box

    def _build_ui(self):
        self.player = None
        self.prepared_listener = None

        root = BoxLayout(orientation='vertical')

        self.input = TextInput(
            hint_text='输入流媒体 URL（MP3 / M3U8 / 直播流）',
            size_hint_y=None,
            height=100,
            font_size=24,
            font_name=DEFAULT_FONT if DEFAULT_FONT else None,
            multiline=False
        )

        btn_bar = BoxLayout(size_hint_y=None, height=90)

        btn_add = Button(text='添加', font_size=24, font_name=DEFAULT_FONT if DEFAULT_FONT else None)
        btn_add.bind(on_press=self.add_url)

        btn_import = Button(text='导入 M3U', font_size=24, font_name=DEFAULT_FONT if DEFAULT_FONT else None)
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

        # 延迟异步初始化原生播放器与加载列表，确保 UI 完全展现，不阻塞冷启动
        self.load_playlist()
        return root

    def on_start(self):
        # Activity 准备就绪后再初始化播放器与动态权限
        self.init_player()
        self.request_android_permissions()

    def request_android_permissions(self):
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET, Permission.READ_EXTERNAL_STORAGE])
            except Exception as e:
                print(f"Permissions request warning: {e}")

    def get_playlist_path(self):
        # 优先使用 user_data_dir，异常回退到当前目录
        try:
            return os.path.join(self.user_data_dir, 'playlist.txt')
        except Exception:
            return 'playlist.txt'

    def init_player(self):
        if platform == 'android':
            try:
                from jnius import autoclass, PythonJavaClass, java_method
                MediaPlayer = autoclass('android.media.MediaPlayer')
                self.player = MediaPlayer()

                class PreparedListener(PythonJavaClass):
                    __javainterfaces__ = ['android/media/MediaPlayer$OnPreparedListener']
                    __javacontext__ = 'app'

                    def __init__(self, callback):
                        super(PreparedListener, self).__init__()
                        self.callback = callback

                    @java_method('(Landroid/media/MediaPlayer;)V')
                    def onPrepared(self, mp):
                        self.callback(mp)

                self.prepared_listener = PreparedListener(lambda mp: mp.start())
                self.player.setOnPreparedListener(self.prepared_listener)
            except Exception as e:
                print(f"Failed to initialize Android MediaPlayer: {e}")
                self.player = None
        else:
            self.player = None

    def play(self, url):
        if platform == 'android':
            if not self.player:
                self.init_player()
            if self.player:
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
            height=90,
            font_size=20
        )
        btn.bind(on_press=lambda x: self.play(url))
        self.list_box.add_widget(btn)

    def save_url(self, url):
        try:
            with open(self.get_playlist_path(), 'a', encoding='utf-8') as f:
                f.write(url + '\n')
        except Exception as e:
            print(f"Save URL error: {e}")

    def load_playlist(self):
        try:
            path = self.get_playlist_path()
            if not os.path.exists(path):
                return
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    url = line.strip()
                    if url:
                        self.add_item(url)
        except Exception as e:
            print(f"Load playlist error: {e}")

    def import_m3u(self, instance):
        for path in ['/sdcard/playlist.m3u', '/storage/emulated/0/playlist.m3u']:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                self.add_item(line)
                                self.save_url(line)
                    break
                except Exception as e:
                    print(f"Import M3U error: {e}")


if __name__ == '__main__':
    RadioPlayer().run()