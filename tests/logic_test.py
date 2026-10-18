# -*- coding: utf-8 -*-
"""纯 Python 逻辑测试：列表解析 + 按键映射 + 选中项循环。

用 stub 顶替 kivy 与 android，因此不需要真机和依赖即可验证核心逻辑。
运行：python tests/logic_test.py
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


# ---------------------------------------------------------------- stub kivy

class StubWidget(object):

    def __init__(self, **kwargs):
        self.children = []
        self.size = (100, 100)
        self.text = kwargs.get('text', '')
        self.__dict__.update(kwargs)

    def bind(self, **_kwargs):
        pass

    def add_widget(self, widget):
        self.children.append(widget)

    def clear_widgets(self):
        self.children = []

    def setter(self, _name):
        return lambda *args, **kwargs: None

    def walk(self):
        return []

    def scroll_to(self, widget, **_kwargs):
        self.last_scrolled = widget


class StubWindow(object):

    clearcolor = (1, 1, 1, 1)

    def bind(self, **_kwargs):
        pass


def _register_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class StubApp(object):

    def __init__(self, **_kwargs):
        pass

    def run(self):
        pass


_register_module('kivy')
_register_module('kivy.app', App=StubApp)
_register_module('kivy.clock', Clock=object)
_register_module('kivy.core')
_register_module('kivy.core.text', LabelBase=object)
_register_module('kivy.core.window', Window=StubWindow())
_register_module('kivy.utils', platform='')
_register_module('kivy.uix')
_register_module('kivy.uix.boxlayout', BoxLayout=StubWidget)
_register_module('kivy.uix.button', Button=StubWidget)
_register_module('kivy.uix.label', Label=StubWidget)
_register_module('kivy.uix.scrollview', ScrollView=StubWidget)
_register_module('kivy.uix.textinput', TextInput=StubWidget)

import main  # noqa: E402  (stub 就绪后才能导入)


# ---------------------------------------------------------------- 测试

class ParsePlaylistTest(unittest.TestCase):

    def test_extinf_m3u(self):
        text = '\n'.join([
            '#EXTM3U',
            '#EXTINF:-1 tvg-name="CNR1" group-title="电台",中国之声',
            'http://a.example.com/cnr1',
            '',
            '#EXTINF:-1,音乐之声',
            'http://a.example.com/music',
        ])
        result = main.parse_playlist(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], '中国之声')
        self.assertEqual(result[0]['url'], 'http://a.example.com/cnr1')
        self.assertEqual(result[1]['name'], '音乐之声')

    def test_plain_url_list(self):
        text = 'http://a.example.com/one.mp3\nhttps://b.example.com/two\n'
        result = main.parse_playlist(text)
        self.assertEqual([c['url'] for c in result],
                         ['http://a.example.com/one.mp3',
                          'https://b.example.com/two'])
        self.assertEqual(result[0]['name'], 'one')   # 去掉扩展名
        self.assertEqual(result[1]['name'], 'two')

    def test_inline_name_url(self):
        text = '央视一套,http://a.example.com/cctv1\n成都交通|http://b.example.com/cd\n'
        result = main.parse_playlist(text)
        self.assertEqual(result[0]['name'], '央视一套')
        self.assertEqual(result[1]['name'], '成都交通')
        self.assertEqual(result[1]['url'], 'http://b.example.com/cd')

    def test_dedup_and_skip_garbage(self):
        text = '\n'.join([
            'http://a.example.com/x',
            'http://a.example.com/x',
            '不是链接的一行',
            '#EXTINF:-1,无后续地址',
        ])
        result = main.parse_playlist(text)
        self.assertEqual(len(result), 1)

    def test_guess_name_fallback_host(self):
        self.assertEqual(main.guess_name('http://abc.com/'), 'abc.com')


class KeyMappingTest(unittest.TestCase):

    def test_key_names(self):
        resolve = main.RadioPlayer._resolve_key
        self.assertEqual(resolve('up', None, None), 'prev')
        self.assertEqual(resolve('down', None, None), 'next')
        self.assertEqual(resolve('enter', None, None), 'play')

    def test_sdl_and_scancode(self):
        resolve = main.RadioPlayer._resolve_key
        self.assertEqual(resolve(1073741906, None, None), 'prev')
        self.assertEqual(resolve(1073741905, None, None), 'next')
        self.assertEqual(resolve(82, None, None), 'prev')
        self.assertEqual(resolve(81, None, None), 'next')
        self.assertEqual(resolve(None, 40, None), 'play')

    def test_android_raw_keycodes(self):
        resolve = main.RadioPlayer._resolve_key
        self.assertEqual(resolve(19, None, None), 'prev')     # DPAD_UP
        self.assertEqual(resolve(20, None, None), 'next')     # DPAD_DOWN
        self.assertEqual(resolve(23, None, None), 'play')     # DPAD_CENTER
        self.assertEqual(resolve(66, None, None), 'play')     # KEYCODE_ENTER
        self.assertEqual(resolve(166, None, None), 'next')    # CHANNEL_UP
        self.assertEqual(resolve(167, None, None), 'prev')    # CHANNEL_DOWN
        self.assertEqual(resolve(87, None, None), 'next')     # MEDIA_NEXT
        self.assertEqual(resolve(88, None, None), 'prev')     # MEDIA_PREVIOUS

    def test_unknown_key_is_ignored(self):
        self.assertIsNone(main.RadioPlayer._resolve_key('z', None, None))
        self.assertIsNone(main.RadioPlayer._resolve_key(5, None, None))


class SelectionTest(unittest.TestCase):

    def setUp(self):
        self.app = main.RadioPlayer()
        self.app.scroll = StubWidget()
        self.app.list_box = StubWidget()
        self.app.item_widgets = []
        self.app.current_url = None
        self.app.palette = dict(main.LIGHT_THEME)
        self.app.selected_index = -1
        self.app.channels = [
            {'name': 'A', 'url': 'http://a/1'},
            {'name': 'B', 'url': 'http://a/2'},
            {'name': 'C', 'url': 'http://a/3'},
        ]
        self.app.set_channels(self.app.channels)

    def test_initial_selection_is_first(self):
        self.assertEqual(self.app.selected_index, 0)
        self.assertEqual(len(self.app.item_widgets), 3)

    def test_move_down_and_wrap(self):
        self.app.move_selection(1)
        self.assertEqual(self.app.selected_index, 1)
        self.app.move_selection(1)
        self.app.move_selection(1)
        self.assertEqual(self.app.selected_index, 0)   # 到底后回到顶部

    def test_move_up_wraps_to_last(self):
        self.app.move_selection(-1)
        self.assertEqual(self.app.selected_index, 2)

    def test_playing_item_marked(self):
        self.app.play_index(1)
        self.assertEqual(self.app.current_url, 'http://a/2')
        self.assertTrue(self.app.item_widgets[1].text.startswith('\u25b6'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
