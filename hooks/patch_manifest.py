# -*- coding: utf-8 -*-
"""p4a 构建钩子：给 AndroidManifest.xml 注入 android:usesCleartextTraffic="true"。

为什么必须做这一步：
    Android 9（API 28）起，targetSdk >= 28 的应用默认禁止明文 HTTP，
    且平台的 MediaPlayer 组件也会一并拒绝 http:// 的音视频地址。
    本项目的直播列表里混有 http://hg.537224.xyz:6060/... 这类明文电台流，
    不打这个开关，这些频道点击后会毫无反应（列表能拉到，但播放失败）。

    另外：明文 http 流偶尔会 fetch 失败，日志里会有 Cleartext traffic not permitted。

钩子由 python-for-android 在打包流程中调用。不同 p4a 版本调用的钩子名不一致，
所以下面把可能出现的钩子名全部覆盖到；每次操作都幂等（已包含则跳过），
重复调用不会损坏 manifest。
"""

import os

FLAG = 'usesCleartextTraffic'
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', 'venv', 'res', 'obj'}
SPEC_FILE = 'buildozer.spec'


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
    """查找 dist 目录下的 AndroidManifest.xml，不遍历整个 Android SDK。"""
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
            # 只在已经进入 dist / 构建目录后继续深入，避免遍历整个 SDK
            entered_build = ('dists' in path or 'build-' in path
                             or 'bootstrap_builds' in path)
            if depth < 3 or entered_build:
                manifests.extend(_scan(path, depth + 1))
    return manifests


def _project_dirs():
    """hook 的工作目录随 p4a 版本而变（可能在 .buildozer/android/app 下），
    因此向上回溯找到含 buildozer.spec 的项目根目录，连同当前目录一起作为起点。
    """
    roots = []
    current = os.getcwd()
    probe = current
    for _ in range(10):
        if os.path.exists(os.path.join(probe, SPEC_FILE)):
            roots.append(probe)
            break
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    roots.append(current)
    roots.append(os.path.join(current, '.buildozer'))

    unique = []
    for root in roots:
        if root not in unique and os.path.isdir(root):
            unique.append(root)
    return unique


def _patch_all():
    for root in _project_dirs():
        manifests = _scan(root)
        print('[radio hook] scan %s -> %d manifest(s)' % (root, len(manifests)))
        for manifest in manifests:
            _patch(manifest)


# 不同 p4a 版本支持不同的钩子点，全部挂上，命中任意一个即可生效
def before_build(*args, **kwargs):
    _patch_all()


def after_build(*args, **kwargs):
    _patch_all()


def before_apk_build(*args, **kwargs):
    _patch_all()


def after_apk_build(*args, **kwargs):
    _patch_all()


def before_apk_assemble(*args, **kwargs):
    _patch_all()


def after_apk_assemble(*args, **kwargs):
    _patch_all()
