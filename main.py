import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView

from jnius import autoclass

MediaPlayer = autoclass('android.media.MediaPlayer')
from kivy.core.text import LabelBase

# 注册字体（假设你的字体文件叫 font.ttf）
LabelBase.register(name='Chinese', fn_regular='font.ttf')

# 在你的 UI 布局（如 Label 或 Button）中指定 font_name
# label = Label(text='直播源', font_name='Chinese')

PLAYLIST_FILE = 'playlist.txt'


class RadioPlayer(App):

    def build(self):
        self.player = MediaPlayer()

        root = BoxLayout(orientation='vertical')

        self.input = TextInput(
            hint_text='输入流媒体 URL（MP3 / M3U8 / 直播流）',
            size_hint_y=None,
            height=80,
            font_size=26,
            multiline=False
        )

        btn_bar = BoxLayout(size_hint_y=None, height=80)

        btn_add = Button(text='添加', font_size=26)
        btn_add.bind(on_press=self.add_url)

        btn_import = Button(text='导入 M3U', font_size=26)
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

    # 播放
    def play(self, url):
        try:
            self.player.reset()
            self.player.setDataSource(url)
            self.player.prepareAsync()
            self.player.setOnPreparedListener(lambda mp: mp.start())
        except Exception as e:
            print(e)

    # 添加 URL
    def add_url(self, instance):
        url = self.input.text.strip()
        if url:
            self.add_item(url)
            self.save_url(url)
            self.input.text = ''

    # UI 列表项
    def add_item(self, url):
        btn = Button(
            text=url,
            size_hint_y=None,
            height=80,
            font_size=22
        )
        btn.bind(on_press=lambda x: self.play(url))
        self.list_box.add_widget(btn)

    # 保存列表
    def save_url(self, url):
        with open(PLAYLIST_FILE, 'a', encoding='utf-8') as f:
            f.write(url + '\n')

    # 加载列表
    def load_playlist(self):
        if not os.path.exists(PLAYLIST_FILE):
            return
        with open(PLAYLIST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if url:
                    self.add_item(url)

    # 导入 M3U（放在 /sdcard/playlist.m3u）
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


RadioPlayer().run()
