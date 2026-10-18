# -*- coding: utf-8 -*-
"""p4a 构建钩子：给 AndroidManifest.xml 注入 android:usesCleartextTraffic="true"。

为什么必须做这一步：
    Android 9（API 28）起，targetSdk >= 28 的应用默认禁止明文 HTTP，
    且平台的 MediaPlayer 组件也会一并拒绝 http:// 的音视频地址。
    本项目的直播列表里混有 http://hg.537224.xyz:6060/... 这类明文电台流，
    不打这个开关，这些频道点击后会毫无反应（列表能拉到，但播放失败）。

钩子会被 python-for-android 在打 APK 前后调用，操作是幂等的：
    已包含该属性则直接跳过，因此重复调用不会损坏 manifest。
"""

import os

FLAG = 'usesCleartextTraffic'
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', 'venv', 'res', 'obj'}


def _patch(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as handle:
            content = handle.read()
    except OSError:
        return False

    if FLAG in content or '<application' not in content:
        return False

    patched = content.replace(
        '<application', '<application android:%s="true"' % FLAG, 1)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(patched)
    print('[radio hook] usesCleartextTraffic injected -> %s' % path)
    return True


def _scan(base, depth=0):
    """查找 dist 目录下的 AndroidManifest.xml，不去遍历整个 Android SDK。"""
    manifests = []
    try:
        names = os.listdir(base)
    except OSError:
        return manifests

    for name in names:
        path = os.path.join(base, name)
        if os.path.isfile(path):
            if name == 'AndroidManifest.xml':
                manifests.append(path)
        elif os.path.isdir(path) and name not in SKIP_DIRS:
            entered_build = ('dists' in path or 'build-' in path
                             or 'bootstrap_builds' in path)
            if depth < 3 or entered_build:
                manifests.extend(_scan(path, depth + 1))
    return manifests


def _patch_all():
    roots = [os.getcwd(), os.path.abspath(os.path.join(os.getcwd(), os.pardir))]
    seen = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        for manifest in _scan(root):
            _patch(manifest)


def before_apk_build(*args, **kwargs):
    _patch_all()


def after_apk_build(*args, **kwargs):
    _patch_all()
