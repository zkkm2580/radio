# -*- coding: utf-8 -*-
"""RadioPlayer - 安卓车机收音机。

- 内置远程播放列表，开机立刻显示条目（离线时走本地缓存）
- 支持车机 / 方向盘上下键切换条目，确认键播放
- 夜间模式跟随系统
"""

import os
import ssl
import threading
import time
import traceback
import urllib.request
from urllib.parse import unquote, urlparse

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

# ---------------------------------------------------------------- 配置

# 内置播放列表地址（每次启动自动拉取更新）
# 注意：列表本身走 HTTPS，但列表内的电台有不少是 http:// 明文流，
# Android 9+ 需要开启 usesCleartextTraffic 才能播放（见 buildozer.spec）
REMOTE_PLAYLIST_URL = 'https://zj.537224.xyz/radio.txt'

REMOTE_CACHE_FILE = 'remote_playlist.txt'   # 远程列表原始文本缓存
CUSTOM_FILE = 'custom_playlist.txt'         # 用户手动添加的频道
GOOD_SOURCE_FILE = 'good_source.txt'        # 记住真正能出声的那条线路

FETCH_TIMEOUT = 12
SCHEME_PREFIX = ('http://', 'https://', 'rtsp://', 'rtmp://', 'mms://')

# 播放相关
# prepareAsync 在部分车机上会无声挂起（既不回调 onPrepared 也不回调 onError），
# 必须有看门狗兜底，否则界面永远停在「正在缓冲」。
PREPARE_TIMEOUT = 12
PROBE_TIMEOUT = 8

# 部分 CDN 会按 UA 区别对待，给一个通用浏览器 UA 更稳
PLAY_UA = ('Mozilla/5.0 (Linux; Android 10; RadioPlayer) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')

# MediaPlayer 的 onError 回调只给整数，翻译成人话才能定位问题
ERROR_TEXT = {
    1: '未知错误',
    100: '播放器服务崩溃',
    200: '媒体服务丢失',
    -38: '播放器状态异常',
    -110: '连接超时',
    -1004: '网络 IO 错误',
    -1007: '数据格式错误',
    -1010: '不支持的编码',
    -2147483648: '底层未指定错误',
}

EXTRA_TEXT = {
    -1004: '连接被断开或源不可达',
    -1007: '分片数据不是合法媒体',
    -1010: '车机不支持该音频编码',
    -110: '源站响应超时',
}


def describe_error(what, extra):
    """把 (what, extra) 翻译成状态栏可直接显示的短句。"""
    if what is None:
        return ''
    main = ERROR_TEXT.get(what, 'code=%s' % what)
    sub = EXTRA_TEXT.get(extra)
    return '%s%s' % (main, '·%s' % sub if sub else '')

# ---------------------------------------------------------------- 主题
# 日间：米白纸感 + 墨绿主色 + 暖橙强调；夜间：深色低亮度，避免车机夜间刺眼

LIGHT_THEME = {
    'bg': (0.957, 0.949, 0.918, 1),
    'card': (1.0, 1.0, 1.0, 1),
    'card_selected': (0.145, 0.404, 0.298, 1),
    'card_playing': (0.898, 0.451, 0.145, 1),
    'text': (0.145, 0.157, 0.157, 1),
    'text_selected': (1.0, 1.0, 1.0, 1),
    'secondary': (0.42, 0.44, 0.44, 1),
    'input_bg': (1.0, 1.0, 1.0, 1),
}

DARK_THEME = {
    'bg': (0.075, 0.090, 0.098, 1),
    'card': (0.129, 0.153, 0.165, 1),
    'card_selected': (0.298, 0.545, 0.427, 1),
    'card_playing': (0.749, 0.404, 0.157, 1),
    'text': (0.898, 0.914, 0.918, 1),
    'text_selected': (1.0, 1.0, 1.0, 1),
    'secondary': (0.545, 0.576, 0.588, 1),
    'input_bg': (0.129, 0.153, 0.165, 1),
}

# ---------------------------------------------------------------- 字体

DEFAULT_FONT = None
try:
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _bundled_font = os.path.join(_current_dir, 'font.ttf')
    if os.path.exists(_bundled_font):
        LabelBase.register(name='Chinese', fn_regular=_bundled_font)
        DEFAULT_FONT = 'Chinese'
    elif platform == 'android':
        for _sys_font in ['/system/fonts/NotoSansSC-Regular.otf',
                          '/system/fonts/DroidSansFallback.ttf',
                          '/system/fonts/NotoSansCJK-Regular.ttc']:
            if os.path.exists(_sys_font):
                LabelBase.register(name='Chinese', fn_regular=_sys_font)
                DEFAULT_FONT = 'Chinese'
                break
except Exception as exc:  # 字体缺失不致命，回退到默认字体
    print('Font registration warning: %s' % exc)


# ---------------------------------------------------------------- 列表解析

def guess_name(url):
    """从 URL 推断一个可读的频道名。"""
    try:
        parse = urlparse(url)
        tail = [seg for seg in parse.path.split('/') if seg]
        if tail:
            name = unquote(tail[-1])
            for ext in ('.m3u8', '.m3u', '.mp3', '.aac', '.flac', '.pls', '.ts'):
                if name.lower().endswith(ext):
                    name = name[: -len(ext)]
                    break
            if name:
                return name
        return parse.netloc
    except Exception:
        return url


def parse_playlist(text):
    """解析 M3U / 纯 URL / "名称,URL" 混合列表。

    返回 [{'name': str, 'url': str}, ...]，按 URL 去重并保持原有顺序。
    """
    items = []
    seen = set()
    pending_name = ''

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith('#EXTINF'):
            # #EXTINF:-1 tvg-name="xx" group-title="yy",频道名
            pending_name = line.rsplit(',', 1)[-1].strip() if ',' in line else ''
            continue
        if line.startswith('#'):
            continue

        name, url = pending_name, line
        pending_name = ''

        # 支持 "名称,URL" / "名称|URL" 行内写法
        for sep in (',', '\uff0c', '|'):
            if sep in line:
                left, right = line.split(sep, 1)
                right = right.strip()
                if left.strip() and right.lower().startswith(SCHEME_PREFIX):
                    name, url = left.strip(), right
                    break

        if not url.lower().startswith(SCHEME_PREFIX):
            continue
        if not name:
            name = guess_name(url)

        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({'name': name, 'url': url})

    return items


# ---------------------------------------------------------------- 应用

class RadioPlayer(App):

    # 类级默认值：即使 build() 未跑完就有播放请求，也不会因缺属性崩溃
    current_play_url = None
    current_label = None
    play_token = 0
    play_attempts = ()
    attempt_index = -1
    prepare_watchdog = None
    last_error = None
    is_playing = False
    good_sources = None     # {原始 URL: (真正可用的 URL, 是否带请求头)}

    # -------------------------------------------------------- 生命周期

    def build(self):
        self.channels = []          # [{'name': str, 'url': str}]
        self.item_widgets = []      # 与 channels 顺序一致的按钮
        self.selected_index = -1
        self.current_url = None
        self.player = None
        self.prepared_listener = None
        self.error_listener = None

        # 播放线路重试相关状态
        self.current_play_url = None
        self.current_label = None
        self.play_token = 0         # 每次播放自增，用于作废过期回调
        self.play_attempts = []
        self.attempt_index = -1
        self.prepare_watchdog = None
        self.last_error = None
        self.is_playing = False

        self._fetching = False
        self._night = None
        self.palette = dict(LIGHT_THEME)
        self.root_widget = None

        try:
            return self._build_ui()
        except Exception:
            # 极限兜底：构建 UI 出错时展示错误而不是闪退
            box = BoxLayout(orientation='vertical')
            box.add_widget(Label(text='Startup Error:\n%s' % traceback.format_exc(),
                                 font_size=18))
            return box

    def on_start(self):
        self.apply_theme(force=True)
        # 冷启动先用本地缓存铺满列表，保证开机就有条目
        self.load_local_channels()

        self._load_good_sources()
        self.init_player()
        self.request_android_permissions()

        Window.bind(on_key_down=self.on_key_down)

        # 夜间模式跟随系统：定期核对 uiMode，系统切换立即换肤
        Clock.schedule_interval(self._watch_night_mode, 20)
        self._watch_night_mode()

        self.refresh_remote()

    def on_stop(self):
        self.play_token += 1
        self._cancel_watchdog()
        self.release_player()

    def on_resume(self):
        # 从后台返回时重新核对一次系统夜间设置
        self._watch_night_mode()

    # -------------------------------------------------------- 界面

    def _build_ui(self):
        root = BoxLayout(orientation='vertical', padding=8, spacing=8)

        top = BoxLayout(orientation='horizontal', size_hint_y=None,
                        height=90, spacing=8)

        self.input = TextInput(
            hint_text='输入流媒体 URL（MP3 / M3U8 / 直播流）',
            size_hint_x=0.56, font_size=24, multiline=False,
            font_name=DEFAULT_FONT, padding=[14, 18, 14, 18])

        self.btn_add = Button(text='添加', size_hint_x=0.22, font_size=24,
                              font_name=DEFAULT_FONT)
        self.btn_add.bind(on_press=self.add_url)

        self.btn_refresh = Button(text='刷新列表', size_hint_x=0.22, font_size=24,
                                  font_name=DEFAULT_FONT)
        self.btn_refresh.bind(on_press=lambda x: self.refresh_remote(manual=True))

        top.add_widget(self.input)
        top.add_widget(self.btn_add)
        top.add_widget(self.btn_refresh)

        self.status = Label(text='正在加载频道…', size_hint_y=None, height=40,
                            font_size=18, font_name=DEFAULT_FONT, halign='left',
                            valign='middle', shorten=True)
        self.status.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], None)))

        self.list_box = BoxLayout(orientation='vertical', size_hint_y=None,
                                  spacing=6)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        self.scroll = ScrollView()
        self.scroll.add_widget(self.list_box)

        self.hint = Label(text='上下键切换频道 · 确认键 / 点击播放',
                          size_hint_y=None, height=38, font_size=17,
                          font_name=DEFAULT_FONT, halign='center',
                          valign='middle')
        self.hint.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], None)))

        root.add_widget(top)
        root.add_widget(self.status)
        root.add_widget(self.scroll)
        root.add_widget(self.hint)

        self.root_widget = root
        return root

    def set_status(self, text):
        if getattr(self, 'status', None) is not None:
            self.status.text = text

    # -------------------------------------------------------- 列表渲染

    def set_channels(self, channels, status_text=None):
        """替换频道列表并重建界面（必须在主线程调用）。"""
        self.channels = channels
        self.selected_index = 0 if channels else -1
        self.rebuild_list()
        if status_text:
            self.set_status(status_text)

    def rebuild_list(self):
        self.list_box.clear_widgets()
        self.item_widgets = []

        if not self.channels:
            empty = Label(text='暂无频道\n请检查网络后点击「刷新列表」',
                          font_size=22, font_name=DEFAULT_FONT,
                          size_hint_y=None, height=160, halign='center',
                          valign='middle')
            empty.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], None)))
            self.list_box.add_widget(empty)
            return

        for index, channel in enumerate(self.channels):
            btn = Button(text=channel['name'], size_hint_y=None, height=96,
                         font_size=24, font_name=DEFAULT_FONT,
                         halign='left', valign='middle', shorten=True)
            btn.background_normal = ''
            btn.padding = (18, 12)
            btn.item_index = index
            btn.bind(on_press=self.on_item_press)
            btn.bind(size=lambda w, s: setattr(w, 'text_size', (s[0] - 36, None)))
            self.list_box.add_widget(btn)
            self.item_widgets.append(btn)

        self.refresh_item_styles()

    def refresh_item_styles(self):
        palette = self.palette
        for index, btn in enumerate(self.item_widgets):
            if index >= len(self.channels):
                continue
            is_playing = (self.channels[index]['url'] == self.current_url)
            is_selected = (index == self.selected_index)
            if is_playing:
                btn.background_color = palette['card_playing']
                btn.color = palette['text_selected']
            elif is_selected:
                btn.background_color = palette['card_selected']
                btn.color = palette['text_selected']
            else:
                btn.background_color = palette['card']
                btn.color = palette['text']
            name = self.channels[index]['name']
            btn.text = ('\u25b6 %s' % name) if is_playing else name

    def on_item_press(self, instance):
        index = getattr(instance, 'item_index', None)
        if index is None:
            return
        self.select(index)
        self.play_index(index)

    def select(self, index):
        if not self.channels:
            return
        total = len(self.channels)
        self.selected_index = index % total
        self.refresh_item_styles()
        try:
            self.scroll.scroll_to(self.item_widgets[self.selected_index],
                                  padding=12, animate=False)
        except Exception:
            pass

    def move_selection(self, delta):
        if not self.channels:
            return
        self.select((self.selected_index + delta) % len(self.channels))

    def play_index(self, index):
        if index is None or not (0 <= index < len(self.channels)):
            return
        channel = self.channels[index]
        self.play(channel['url'], channel['name'])

    # -------------------------------------------------------- 物理按键

    def on_key_down(self, window, key, scancode=None, codepoint=None,
                    modifiers=None, *args):
        """处理车机 / 方向盘按键。

        同时覆盖 SDL 键名、SDL keycode、SDL scancode 与安卓原始 keycode，
        避免不同车机上报形式不一致导致按键失灵。
        """
        action = self._resolve_key(key, scancode, codepoint)
        if action == 'prev':
            self.move_selection(-1)
            return True
        if action == 'next':
            self.move_selection(1)
            return True
        if action == 'play':
            self.play_index(self.selected_index)
            return True
        return False

    @staticmethod
    def _resolve_key(key, scancode, codepoint):
        if isinstance(key, str):
            klower = key.lower()
            if klower in ('up',):
                return 'prev'
            if klower in ('down',):
                return 'next'
            if klower in ('enter', 'spacebar', 'space', 'numpadenter'):
                return 'play'

        #  SDL keycode(>1000000) / SDL scancode(0-285) / 安卓原始 keycode
        prev_ids = {
            1073741906,  # SDLK_UP
            82,          # SDL_SCANCODE_UP
            19,          # KEYCODE_DPAD_UP
            167,         # KEYCODE_CHANNEL_DOWN
            88,          # KEYCODE_MEDIA_PREVIOUS
        }
        next_ids = {
            1073741905,  # SDLK_DOWN
            81,          # SDL_SCANCODE_DOWN
            20,          # KEYCODE_DPAD_DOWN
            166,         # KEYCODE_CHANNEL_UP
            87,          # KEYCODE_MEDIA_NEXT
        }
        play_ids = {
            13,          # SDLK_RETURN
            1073741912,  # SDLK_KP_ENTER
            40,          # SDL_SCANCODE_RETURN
            32,          # SDLK_SPACE
            44,          # SDL_SCANCODE_SPACE
            23,          # KEYCODE_DPAD_CENTER
            66,          # KEYCODE_ENTER
            85,          # KEYCODE_MEDIA_PLAY_PAUSE
        }

        for value in (key, scancode):
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            if value in prev_ids:
                return 'prev'
            if value in next_ids:
                return 'next'
            if value in play_ids:
                return 'play'

        if isinstance(codepoint, str) and codepoint in (' ', '\r', '\n'):
            return 'play'

        return None

    # -------------------------------------------------------- 本地存储

    def _path(self, filename):
        try:
            return os.path.join(self.user_data_dir, filename)
        except Exception:
            return filename

    def _read_file(self, path):
        try:
            if not os.path.exists(path):
                return ''
            with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                return fh.read()
        except Exception as exc:
            print('Read file error: %s' % exc)
            return ''

    def load_local_channels(self):
        """冷启动：渲染本地缓存 + 用户自定义频道。"""
        remote_raw = self._read_file(self._path(REMOTE_CACHE_FILE))
        custom_raw = self._read_file(self._path(CUSTOM_FILE))
        channels = self._dedup(parse_playlist(custom_raw)
                               + parse_playlist(remote_raw))

        if channels:
            self.set_channels(channels,
                              '已载入本地缓存 %d 个频道，正在更新…' % len(channels))
        else:
            self.set_channels([], '正在拉取内置频道列表…')

    @staticmethod
    def _dedup(channels):
        seen = set()
        result = []
        for channel in channels:
            key = channel['url'].lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(channel)
        return result

    def save_custom(self, url, name=None):
        try:
            line = '%s|%s\n' % (name, url) if name else '%s\n' % url
            with open(self._path(CUSTOM_FILE), 'a', encoding='utf-8') as fh:
                fh.write(line)
        except Exception as exc:
            print('Save URL error: %s' % exc)

    # -------------------------------------------------------- 远程更新

    def refresh_remote(self, manual=False):
        if self._fetching:
            return
        self._fetching = True
        self.set_status('正在更新频道列表…')
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    @staticmethod
    def _candidate_urls():
        """优先尝试 HTTPS，失败再回落明文 HTTP（源站随时可升级）。"""
        url = REMOTE_PLAYLIST_URL
        if url.startswith('http://'):
            return [url.replace('http://', 'https://', 1), url]
        return [url]

    @staticmethod
    def _open_url(url, verify=True):
        request = urllib.request.Request(
            url, headers={'User-Agent': 'RadioPlayer/1.0'})
        context = None
        if url.startswith('https://') and not verify:
            # 自签证书兜底：这里只拉取公开列表，不涉及敏感数据
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return urllib.request.urlopen(
            request, timeout=FETCH_TIMEOUT, context=context)

    def _fetch_worker(self):
        target_url = None
        text = None
        last_error = None

        for url in self._candidate_urls():
            # HTTPS 先按标准校验证书，失败再放宽兼容自签证书
            attempts = [True, False] if url.startswith('https://') else [True]
            for verify in attempts:
                try:
                    with self._open_url(url, verify) as resp:
                        raw = resp.read()
                    target_url = url
                    text = raw.decode('utf-8', errors='ignore')
                    break
                except Exception as exc:
                    last_error = exc
            if text is not None:
                break

        if text is None:
            Clock.schedule_once(lambda dt: self._on_remote_fail(last_error))
            return

        channels = parse_playlist(text)
        if not channels:
            Clock.schedule_once(lambda dt: self._on_remote_fail(
                ValueError('列表为空或格式无法识别')))
            return

        try:
            with open(self._path(REMOTE_CACHE_FILE), 'w',
                      encoding='utf-8') as fh:
                fh.write(text)
        except Exception as exc:
            print('Write cache error: %s' % exc)

        Clock.schedule_once(lambda dt: self._on_remote_ok(
            channels, target_url, len(channels)))

    def _on_remote_ok(self, channels, url, count):
        self._fetching = False
        custom_raw = self._read_file(self._path(CUSTOM_FILE))
        merged = self._dedup(parse_playlist(custom_raw) + channels)
        self.set_channels(merged, '列表已更新 · 共 %d 个频道' % count)

    def _on_remote_fail(self, error):
        self._fetching = False
        reason = str(error) if error is not None else '未知错误'
        if self.channels:
            self.set_status('列表更新失败（%s），当前显示本地缓存 %d 个频道'
                            % (reason, len(self.channels)))
        else:
            self.set_status('无法连接列表服务器（%s），稍后自动重试' % reason)
        # 一分钟后自动重试一次
        Clock.schedule_once(lambda dt: self.refresh_remote(), 60)

    # -------------------------------------------------------- M3U 导入

    def android_download_dir(self):
        if platform != 'android':
            return None
        try:
            from jnius import autoclass
            Environment = autoclass('android.os.Environment')
            return str(Environment.getExternalStoragePublicDirectory(
                Environment.DIRECTORY_DOWNLOADS).getAbsolutePath())
        except Exception:
            return None

    def import_candidates(self):
        paths = [self._path('imported.m3u'), '/sdcard/radio.m3u',
                 '/sdcard/playlist.m3u', '/storage/emulated/0/playlist.m3u']
        download = self.android_download_dir()
        if download:
            paths.insert(1, os.path.join(download, 'radio.m3u'))
            paths.insert(1, os.path.join(download, 'playlist.m3u'))
        return paths

    def import_m3u(self, instance=None):
        for path in self.import_candidates():
            if not isinstance(path, str) or not os.path.exists(path):
                continue
            try:
                channels = parse_playlist(self._read_file(path))
                if not channels:
                    continue
                existing = parse_playlist(self._read_file(self._path(CUSTOM_FILE)))
                with open(self._path(CUSTOM_FILE), 'w',
                          encoding='utf-8') as fh:
                    for channel in self._dedup(existing + channels):
                        fh.write('%s|%s\n' % (channel['name'], channel['url']))
                custom_raw = self._read_file(self._path(CUSTOM_FILE))
                remote_raw = self._read_file(self._path(REMOTE_CACHE_FILE))
                self.set_channels(
                    self._dedup(parse_playlist(custom_raw)
                                + parse_playlist(remote_raw)),
                    '已从 %s 导入 %d 个频道' % (os.path.basename(path),
                                          len(channels)))
                return
            except Exception as exc:
                print('Import M3U error: %s' % exc)
        self.set_status('未找到可导入的 M3U 文件（放在 Download 目录）')

    # -------------------------------------------------------- 手动添加

    def add_url(self, instance):
        url = self.input.text.strip()
        if not url:
            return
        channels = parse_playlist(url)
        if channels:
            self.save_custom(channels[0]['url'], channels[0]['name'])
        else:
            self.save_custom(url, None)
        self.input.text = ''

        custom_raw = self._read_file(self._path(CUSTOM_FILE))
        remote_raw = self._read_file(self._path(REMOTE_CACHE_FILE))
        self.set_channels(
            self._dedup(parse_playlist(custom_raw)
                        + parse_playlist(remote_raw)), '已添加频道')

    # -------------------------------------------------------- 播放

    def init_player(self):
        if platform != 'android':
            self.player = None
            return
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

            class ErrorListener(PythonJavaClass):
                __javainterfaces__ = ['android/media/MediaPlayer$OnErrorListener']
                __javacontext__ = 'app'

                def __init__(self, callback):
                    super(ErrorListener, self).__init__()
                    self.callback = callback

                @java_method('(Landroid/media/MediaPlayer;II)Z')
                def onError(self, mp, what, extra):
                    self.callback(what, extra)
                    return True

            self.prepared_listener = PreparedListener(self._on_prepared)
            self.error_listener = ErrorListener(self._on_playback_error)
            self.player.setOnPreparedListener(self.prepared_listener)
            self.player.setOnErrorListener(self.error_listener)

            # 息屏后保持播放
            try:
                PowerManager = autoclass('android.os.PowerManager')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
                self.player.setWakeMode(activity.getApplicationContext(),
                                        PowerManager.PARTIAL_WAKE_LOCK)
            except Exception as exc:
                print('WakeLock warning: %s' % exc)

        except Exception as exc:
            print('Failed to initialize Android MediaPlayer: %s' % exc)
            self.player = None

    def release_player(self):
        try:
            if self.player is not None:
                self.player.release()
        except Exception:
            pass
        finally:
            self.player = None

    def play(self, url, name=None):
        """开始播放。安卓端按候选线路逐个尝试，失败自动换下一条。"""
        label = name or guess_name(url)
        self.current_play_url = url
        self.current_url = url
        self.current_label = label
        self.play_token += 1        # 作废上一次播放可能残留的回调
        self.last_error = None
        self.is_playing = False
        self.refresh_item_styles()

        if platform != 'android':
            print('[PC 预览模拟] 正在播放: %s (%s)' % (label, url))
            self.set_status('[PC 预览] %s' % label)
            return

        if self.player is None:
            self.init_player()
        if self.player is None:
            self.current_url = None
            self.refresh_item_styles()
            self.set_status('播放器不可用，无法播放 %s' % label)
            return

        self.play_attempts = self._ordered_attempts(url)
        self.attempt_index = -1
        self._try_next_attempt()

    # ---------------------------------------------------- 候选线路

    @staticmethod
    def _url_attempts(url):
        """生成候选线路：主地址与协议互换地址 × 带/不带请求头。

        车机上报的失败原因五花八门（TLS 握手失败、CDN 拒绝默认 UA、
        HLS 栈挑协议），逐个试过比直接放弃可靠得多。
        """
        lower = url.lower()
        if not lower.startswith(('http://', 'https://')):
            return [(url, False)]   # 非 HTTP 协议不做协议互换，也没必要带头

        variants = [url]
        if lower.startswith('https://'):
            variants.append('http://' + url[len('https://'):])
        elif lower.startswith('http://'):
            variants.append('https://' + url[len('http://'):])

        attempts = []
        for variant in variants:
            # 先带请求头（CDN 更可能放行），不行再退回裸地址
            attempts.append((variant, True))
            attempts.append((variant, False))
        return attempts

    def _ordered_attempts(self, url):
        """上次在这台车机上出过声的线路排到最前，避免每次都先干等一轮超时。"""
        attempts = self._url_attempts(url)
        remembered = (self.good_sources or {}).get(url)
        if remembered:
            first = (remembered[0], bool(remembered[1]))
            attempts = [first] + [a for a in attempts if a != first]
        return attempts

    def _try_next_attempt(self, token=None):
        if token is not None and token != self.play_token:
            return          # 已被更新的播放请求取代，丢弃这次结果
        self.attempt_index += 1
        if self.attempt_index >= len(self.play_attempts):
            self._on_play_failed()
            return

        url, use_headers = self.play_attempts[self.attempt_index]
        token = self.play_token
        self._log('attempt %d/%d -> %s (headers=%s)'
                  % (self.attempt_index + 1, len(self.play_attempts),
                     url, use_headers))
        try:
            self.player.reset()
            self._configure_output()          # reset 会清空音频通道，需重设
            if not self._set_data_source(url, use_headers):
                raise RuntimeError('setDataSource 失败')
            self.player.prepareAsync()
        except Exception as exc:
            self._log('attempt error: %s' % exc)
            Clock.schedule_once(lambda dt: self._try_next_attempt(token), 0)
            return

        if self.attempt_index == 0:
            self.set_status('正在缓冲：%s' % self.current_label)
        else:
            self.set_status('换备用线路 %d/%d：%s'
                            % (self.attempt_index + 1, len(self.play_attempts),
                               self.current_label))
        self._schedule_watchdog(token)

    def _configure_output(self):
        """指定走媒体音量通道，避免车机上被当作通话音量或被系统压低。"""
        try:
            from jnius import autoclass
            AudioAttributes = autoclass('android.media.AudioAttributes')
            builder = AudioAttributes.Builder()
            builder.setUsage(AudioAttributes.USAGE_MEDIA)
            builder.setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
            self.player.setAudioAttributes(builder.build())
        except Exception as exc:
            print('AudioAttributes warning: %s' % exc)

    def _set_data_source(self, url, use_headers):
        try:
            if use_headers:
                from jnius import autoclass
                Uri = autoclass('android.net.Uri')
                HashMap = autoclass('java.util.HashMap')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                context = PythonActivity.mActivity.getApplicationContext()
                headers = HashMap()
                headers.put('User-Agent', PLAY_UA)
                headers.put('Referer', 'https://%s/' % urlparse(url).netloc)
                self.player.setDataSource(context, Uri.parse(url), headers)
            else:
                self.player.setDataSource(url)
            return True
        except Exception as exc:
            self._log('setDataSource failed: %s' % exc)
            return False

    # ---------------------------------------------------- 看门狗

    def _schedule_watchdog(self, token):
        self._cancel_watchdog()
        self.prepare_watchdog = Clock.schedule_once(
            lambda dt: self._on_prepare_timeout(token), PREPARE_TIMEOUT)

    def _cancel_watchdog(self):
        if self.prepare_watchdog is not None:
            try:
                self.prepare_watchdog.cancel()
            except Exception:
                pass
            self.prepare_watchdog = None

    def _on_prepare_timeout(self, token):
        if token != self.play_token:      # 已经切到别的播放请求，忽略
            return
        self.prepare_watchdog = None
        self._log('prepare timeout (%ss)' % PREPARE_TIMEOUT)
        self._try_next_attempt()

    # ---------------------------------------------------- 播放回调

    def _on_prepared(self, mp):
        token = self.play_token
        self._log('prepared ok')
        try:
            mp.start()
            self.is_playing = True
        except Exception as exc:
            self._log('start failed: %s' % exc)
        Clock.schedule_once(lambda dt: self._finish_prepare(token))

    def _finish_prepare(self, token):
        if token != self.play_token:
            return          # 用户已切到别的频道，别覆盖新请求的状态
        self._cancel_watchdog()
        self._remember_good_source()
        self.set_status('正在播放：%s' % self.current_label)

    # ---------------------------------------------------- 记住可用线路

    def _load_good_sources(self):
        self.good_sources = {}
        for line in self._read_file(self._path(GOOD_SOURCE_FILE)).splitlines():
            parts = line.split('\t')
            if len(parts) == 3:
                self.good_sources[parts[0]] = (parts[1], parts[2] == '1')

    def _remember_good_source(self):
        if not self.current_play_url or not self.play_attempts:
            return
        if not (0 <= self.attempt_index < len(self.play_attempts)):
            return
        url, use_headers = self.play_attempts[self.attempt_index]
        if self.good_sources is None:
            self.good_sources = {}
        self.good_sources[self.current_play_url] = (url, use_headers)
        try:
            with open(self._path(GOOD_SOURCE_FILE), 'w',
                      encoding='utf-8') as handle:
                for key, value in list(self.good_sources.items())[-60:]:
                    handle.write('%s\t%s\t%d\n' % (key, value[0],
                                                   1 if value[1] else 0))
        except Exception as exc:
            print('Save good source error: %s' % exc)

    def _on_playback_error(self, what, extra):
        # Java 线程回调，UI 操作必须切回主线程
        self._log('onError what=%s extra=%s' % (what, extra))
        Clock.schedule_once(lambda dt: self._handle_playback_error(what, extra))

    def _handle_playback_error(self, what, extra):
        self._cancel_watchdog()
        self.last_error = (what, extra)

        if self.is_playing:
            # 播放中途断流：不再瞎换线路，直接把原因说清楚
            self.set_status('播放中断：%s · %s'
                            % (self.current_label, describe_error(what, extra)))
            return

        self._try_next_attempt()

    def _on_play_failed(self):
        what, extra = self.last_error if self.last_error else (None, None)
        self.current_url = None
        self.is_playing = False
        self.refresh_item_styles()

        reason = describe_error(what, extra)
        self.set_status('%s 播放失败%s，正在自检网络…'
                        % (self.current_label, '（%s）' % reason if reason else ''))
        # 用 Python 的网络栈独立探一次源，区分「网络不通」与「车机播不出来」
        threading.Thread(target=self._probe_worker,
                         args=(self.current_play_url,), daemon=True).start()

    # ---------------------------------------------------- 网络自检

    def _probe_worker(self, url):
        result = {'playlist': None, 'segment': None, 'error': None}
        try:
            context = ssl.create_default_context()
            request = urllib.request.Request(url, headers={'User-Agent': PLAY_UA})
            with urllib.request.urlopen(
                    request, timeout=PROBE_TIMEOUT, context=context) as resp:
                code = resp.getcode()
                body = resp.read().decode('utf-8', errors='ignore')
            result['playlist'] = code

            segments = [line.strip() for line in body.splitlines()
                        if line.strip() and not line.strip().startswith('#')]
            if segments:
                seg_req = urllib.request.Request(
                    segments[0], headers={'User-Agent': PLAY_UA})
                with urllib.request.urlopen(
                        seg_req, timeout=PROBE_TIMEOUT, context=context) as sresp:
                    sresp.read(4096)
                result['segment'] = sresp.getcode()
        except Exception as exc:
            result['error'] = '%s: %s' % (type(exc).__name__, exc)

        Clock.schedule_once(lambda dt: self._on_probe_result(result))

    def _on_probe_result(self, result):
        error = result.get('error')
        if error:
            self.set_status('%s · 网络不通（%s）' % (self.current_label, error))
            return
        if result['playlist'] == 200 and result['segment'] == 200:
            self.set_status('%s · 源站正常但本机播不出声，多为车机不支持该编码'
                            % self.current_label)
        else:
            self.set_status('%s · 源站异常（列表 %s / 分片 %s）'
                            % (self.current_label, result['playlist'],
                               result['segment']))

    # ---------------------------------------------------- 日志

    def _log(self, message):
        """把播放过程写进 user_data_dir/play.log，便于真机排查。"""
        line = '%s %s\n' % (time.strftime('%H:%M:%S'), message)
        print('[radio] %s' % message)
        if platform != 'android':
            return
        try:
            with open(self._path('play.log'), 'a', encoding='utf-8') as handle:
                handle.write(line)
        except Exception:
            pass

    # -------------------------------------------------------- 权限

    def request_android_permissions(self):
        if platform != 'android':
            return
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.INTERNET,
                                 Permission.ACCESS_NETWORK_STATE])
        except Exception as exc:
            print('Permissions request warning: %s' % exc)

    # -------------------------------------------------------- 夜间模式

    def _system_night_mode(self):
        """True=夜间；False=日间；None=无法判定（保持现状）。"""
        if platform == 'android':
            try:
                from jnius import autoclass
                Configuration = autoclass('android.content.res.Configuration')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
                cfg = activity.getResources().getConfiguration()
                mask = cfg.uiMode & Configuration.UI_MODE_NIGHT_MASK
                return mask == Configuration.UI_MODE_NIGHT_YES
            except Exception as exc:
                print('Night mode detect warning: %s' % exc)
                return None
        # 桌面预览：按本地时间兜底，方便无设备时验证深色适配
        try:
            import datetime
            hour = datetime.datetime.now().hour
            return hour >= 19 or hour < 7
        except Exception:
            return False

    def _watch_night_mode(self, dt=None):
        state = self._system_night_mode()
        if state is None:
            return
        if self._night is None or state != self._night:
            self._night = state
            self.apply_theme(force=True)

    def apply_theme(self, force=False):
        """按当前夜间状态套用配色。"""
        night = self._system_night_mode()
        if night is None:
            night = bool(self._night)
        self._night = night
        self.palette = DARK_THEME if night else LIGHT_THEME
        palette = self.palette

        try:
            Window.clearcolor = palette['bg']
        except Exception:
            pass

        if self.root_widget is None:
            return

        for widget in self.root_widget.walk():
            if isinstance(widget, Button):
                widget.background_normal = ''
                if getattr(widget, 'item_index', None) is not None:
                    continue  # 频道条目由 refresh_item_styles 统一着色
                widget.background_color = palette['card_selected']
                widget.color = palette['text_selected']
            elif isinstance(widget, Label):
                widget.color = palette['secondary']
            elif isinstance(widget, TextInput):
                widget.background_normal = ''
                widget.background_color = palette['input_bg']
                widget.foreground_color = palette['text']
                widget.hint_text_color = palette['secondary']
                widget.cursor_color = palette['text']

        self.refresh_item_styles()


if __name__ == '__main__':
    RadioPlayer().run()
