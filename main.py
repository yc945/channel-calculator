"""
明渠均匀流水力计算 v2.0 - Kivy Android版
支持: 矩形(免费试用) / 梯形/圆形/三角形/抛物线形(注册后可用)
计算模式: 给定水深求流量 / 给定流量求水深

作者: 宜昌水利 超哥
版本: 2.0
"""

import math
import os
import sys
import hashlib
import uuid

# ═══════════════════════════════════════════════
#  注册验证系统
# ═══════════════════════════════════════════════

_LICENSE_SECRET = "YCShuiLi@2025#HydroCalc"
FREE_SHAPES = {'矩形'}


def _compute_license(device_id: str) -> str:
    raw = hashlib.sha256(
        f"{device_id}{_LICENSE_SECRET}".encode('utf-8')
    ).hexdigest().upper()
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def verify_license(device_id: str, code: str) -> bool:
    return code.strip().upper() == _compute_license(device_id)


class LicenseManager:
    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        self._id_file = os.path.join(data_dir, '.device_id')
        self._lic_file = os.path.join(data_dir, '.license')
        self._device_id = None
        self._registered = None

    def get_device_id(self) -> str:
        if self._device_id:
            return self._device_id
        if os.path.exists(self._id_file):
            try:
                with open(self._id_file, 'r') as f:
                    did = f.read().strip()
                if did:
                    self._device_id = did
                    return did
            except Exception:
                pass
        did = str(uuid.uuid4()).replace('-', '')[:16].upper()
        try:
            os.makedirs(self._data_dir, exist_ok=True)
            with open(self._id_file, 'w') as f:
                f.write(did)
        except Exception:
            pass
        self._device_id = did
        return did

    def is_registered(self) -> bool:
        if self._registered is not None:
            return self._registered
        try:
            if os.path.exists(self._lic_file):
                with open(self._lic_file, 'r') as f:
                    code = f.read().strip()
                if code and verify_license(self.get_device_id(), code):
                    self._registered = True
                    return True
        except Exception:
            pass
        self._registered = False
        return False

    def activate(self, code: str) -> bool:
        if verify_license(self.get_device_id(), code):
            try:
                os.makedirs(self._data_dir, exist_ok=True)
                with open(self._lic_file, 'w') as f:
                    f.write(code.strip().upper())
                self._registered = True
                return True
            except Exception:
                pass
        return False


# ═══════════════════════════════════════════════
#  计算核心（纯Python，零Kivy依赖）
# ═══════════════════════════════════════════════

g = 9.81


class HydroSection:
    def __init__(self, A, chi, B):
        self.A = max(A, 1e-12)
        self.chi = max(chi, 1e-12)
        self.B = max(B, 1e-12)
        self.R = self.A / self.chi
        self.h_m = self.A / self.B


def section_rect(b, h):
    return HydroSection(b * h, b + 2 * h, b)


def section_trap(b, h, m):
    A = (b + m * h) * h
    chi = b + 2 * h * math.sqrt(1 + m ** 2)
    B = b + 2 * m * h
    return HydroSection(A, chi, B)


def section_circ(D, h):
    h = min(h, D * (1 - 1e-9))
    theta = 2.0 * math.acos(1.0 - 2.0 * h / D)
    A = (D ** 2 / 8.0) * (theta - math.sin(theta))
    chi = D * theta / 2.0
    B = D * math.sin(theta / 2.0)
    return HydroSection(A, chi, B)


def section_tri(m, h):
    return HydroSection(m * h ** 2, 2.0 * h * math.sqrt(1 + m ** 2), 2.0 * m * h)


def section_para(B_top, h):
    A = (2.0 / 3.0) * B_top * h
    if B_top > 1e-9 and h > 1e-9:
        xi = 4.0 * h / B_top
        chi = (B_top / 2.0) * (
            math.sqrt(1 + xi ** 2) + math.log(xi + math.sqrt(1 + xi ** 2)) / xi
        )
    else:
        chi = B_top
    return HydroSection(A, chi, B_top)


def make_section(shape, p):
    h = p['h']
    if shape == '矩形':
        return section_rect(p['b'], h)
    elif shape == '梯形':
        return section_trap(p['b'], h, p['m'])
    elif shape == '圆形':
        if h >= p['D']:
            raise ValueError(f"水深 {h:.3f}m 不能超过管径 {p['D']:.3f}m")
        return section_circ(p['D'], h)
    elif shape == '三角形':
        return section_tri(p['m'], h)
    else:
        return section_para(p['B_top'], h)


def manning_Q(sec, n, S):
    if n <= 0 or S <= 0:
        return 0.0
    return (1.0 / n) * sec.R ** (2.0 / 3.0) * math.sqrt(S) * sec.A


def bisect(f, lo, hi, tol=1e-9, max_iter=200):
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        fm = f(mid)
        if abs(fm) < tol or (hi - lo) < tol:
            return mid
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2.0


def solve_depth(shape, params, n, S, Q_target):
    h_max = params.get('D', 20.0) * 0.998 if shape == '圆形' else 20.0

    def res(h):
        return manning_Q(make_section(shape, {**params, 'h': h}), n, S) - Q_target

    while res(h_max) < 0 and h_max < 500:
        h_max *= 2
    result = bisect(res, 1e-4, h_max)
    if result is None:
        raise ValueError("求解失败，请检查参数是否合理")
    return result


# ═══════════════════════════════════════════════
#  Kivy UI
# ═══════════════════════════════════════════════

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.metrics import dp, sp
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.uix.image import Image as KivyImage


# ── 字体注册 ──────────────────────────────────────────────────────

def find_chinese_font():
    if getattr(sys, 'frozen', False):
        app_path = os.path.dirname(sys.executable)
    else:
        app_path = os.path.dirname(os.path.abspath(__file__))

    candidates = [
        os.path.join(app_path, 'assets', 'NotoSansSC-Regular.ttf'),
        os.path.join(app_path, 'assets', 'fonts', 'NotoSansSC-Regular.ttf'),
        os.path.join(app_path, 'NotoSansSC-Regular.ttf'),
        os.path.join(app_path, 'assets', 'msyh.ttc'),
        os.path.join(app_path, 'assets', 'simhei.ttf'),
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\SIMSUN.TTC",
        '/system/fonts/NotoSansCJK-Regular.ttc',
        '/system/fonts/DroidSansFallback.ttf',
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                LabelBase.register('CN', path)
                return 'CN'
            except Exception:
                continue
    return 'Roboto'


CN_FONT = find_chinese_font()

# ── 颜色常量 ──────────────────────────────────────────────────────
BG       = (0.051, 0.106, 0.165, 1)
HEADER   = (0.075, 0.180, 0.290, 1)
CARD     = (0.063, 0.145, 0.239, 1)
PRIMARY  = (0.169, 0.424, 0.690, 1)
SUCCESS  = (0.153, 0.404, 0.286, 1)
TEXT     = (0.886, 0.910, 0.941, 1)
ACCENT   = (0.388, 0.702, 0.929, 1)
INPUT    = (0.027, 0.067, 0.122, 1)
WARN     = (0.898, 0.243, 0.243, 1)
YELLOW   = (0.984, 0.678, 0.322, 1)
DIVIDER  = (0.120, 0.260, 0.400, 1)
GOLD     = (0.855, 0.647, 0.125, 1)
LOCK_BG  = (0.18,  0.10,  0.04,  1)


# ── 控件工厂 ──────────────────────────────────────────────────────

def _bg(widget, color, radius=0):
    with widget.canvas.before:
        c = Color(*color)
        r = (RoundedRectangle(pos=widget.pos, size=widget.size, radius=[dp(radius)])
             if radius else Rectangle(pos=widget.pos, size=widget.size))

    def _upd(inst, _):
        r.pos = inst.pos
        r.size = inst.size

    widget.bind(pos=_upd, size=_upd)
    return c, r


def lbl(text, size=14, bold=False, color=None, halign='left', h=None, **kw):
    color = color or TEXT
    w = Label(text=text, font_name=CN_FONT, font_size=sp(size), bold=bold,
              color=color, halign=halign, **kw)
    w.bind(size=w.setter('text_size'))
    if h is not None:
        w.size_hint_y = None
        w.height = dp(h)
    return w


def inp(hint='', text='', filt='float', **kw):
    return TextInput(
        hint_text=hint, text=text,
        font_name=CN_FONT, font_size=sp(15),
        input_filter=filt, multiline=False,
        background_color=INPUT,
        foreground_color=TEXT,
        hint_text_color=(0.35, 0.45, 0.58, 1),
        cursor_color=ACCENT,
        size_hint_y=None, height=dp(46),
        padding=[dp(12), dp(10), dp(12), dp(10)],
        **kw
    )


def btn(text, color=None, h=50, radius=8, **kw):
    color = color or PRIMARY
    b = Button(
        text=text, font_name=CN_FONT, font_size=sp(15),
        background_normal='', background_down='',
        background_color=(0, 0, 0, 0),
        color=TEXT,
        size_hint_y=None, height=dp(h),
        **kw
    )
    _c, _r = _bg(b, color, radius=radius)

    def _press(inst):
        _c.rgba = tuple(max(0, x - 0.08) for x in color[:3]) + (1,)

    def _release(inst):
        _c.rgba = color

    b.bind(on_press=_press, on_release=_release)
    return b


def section_card(title):
    outer = BoxLayout(orientation='vertical',
                      size_hint_y=None, spacing=dp(6),
                      padding=[0, 0, 0, dp(4)])
    _bg(outer, CARD, radius=10)
    hdr = BoxLayout(size_hint_y=None, height=dp(36),
                    padding=[dp(12), 0, dp(12), 0])
    _bg(hdr, HEADER, radius=10)
    hdr.add_widget(lbl(title, size=13, bold=True, color=ACCENT,
                       halign='left', h=36))
    outer.add_widget(hdr)
    outer.bind(minimum_height=outer.setter('height'))
    return outer


def row(label_text, widget, label_w=0.42):
    r = BoxLayout(orientation='horizontal',
                  size_hint_y=None, height=dp(46),
                  spacing=dp(8), padding=[dp(10), 0, dp(10), 0])
    r.add_widget(lbl(label_text, size=14, color=TEXT,
                     halign='left', size_hint_x=label_w))
    r.add_widget(widget)
    return r


# ── Spinner 选项样式 ──────────────────────────────────────────────

class _SpinnerOption(SpinnerOption):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.font_name = CN_FONT
        self.font_size = sp(14)
        self.background_color = INPUT
        self.color = TEXT
        self.height = dp(46)


# ── 错误弹窗 ─────────────────────────────────────────────────────

def _show_error(msg):
    content = BoxLayout(orientation='vertical', spacing=dp(15),
                        padding=dp(15))
    _bg(content, CARD)
    content.add_widget(lbl(f'[!]  {msg}', size=14, color=WARN, halign='center'))
    ok = btn('确定', h=44, radius=8)
    content.add_widget(ok)
    popup = Popup(title='输入错误', content=content,
                  title_font=CN_FONT, title_color=TEXT,
                  separator_color=DIVIDER,
                  background_color=CARD,
                  size_hint=(0.88, None), height=dp(185))
    ok.bind(on_release=popup.dismiss)
    popup.open()


def _show_info(msg, title='提示'):
    content = BoxLayout(orientation='vertical', spacing=dp(15),
                        padding=dp(15))
    _bg(content, CARD)
    content.add_widget(lbl(msg, size=14, color=ACCENT, halign='center'))
    ok = btn('确定', h=44, radius=8)
    content.add_widget(ok)
    popup = Popup(title=title, content=content,
                  title_font=CN_FONT, title_color=TEXT,
                  separator_color=DIVIDER,
                  background_color=CARD,
                  size_hint=(0.88, None), height=dp(185))
    ok.bind(on_release=popup.dismiss)
    popup.open()


# ═══════════════════════════════════════════════
#  断面参数定义
# ═══════════════════════════════════════════════

SHAPE_PARAMS = {
    '矩形':    [('底宽 b (m)',   'b',     '5.0', '米'),
                ('水深 h (m)',   'h',     '2.0', '米')],
    '梯形':    [('底宽 b (m)',   'b',     '4.0', '米'),
                ('水深 h (m)',   'h',     '2.0', '米'),
                ('边坡系数 m',   'm',     '1.5', '无量纲')],
    '圆形':    [('管径 D (m)',   'D',     '1.2', '米'),
                ('水深 h (m)',   'h',     '0.8', '米')],
    '三角形':  [('边坡系数 m',   'm',     '1.0', '无量纲'),
                ('水深 h (m)',   'h',     '2.0', '米')],
    '抛物线形': [('水面宽 B (m)', 'B_top', '6.0', '米'),
                 ('水深 h (m)',   'h',     '2.0', '米')],
}

SHAPES_ALL = list(SHAPE_PARAMS.keys())


# ═══════════════════════════════════════════════
#  InputScreen
# ═══════════════════════════════════════════════

class InputScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._inputs = {}
        self._mode = '水深→流量'
        self._shape = '矩形'
        self._pending_shape = None

        _bg(self, BG)
        root = BoxLayout(orientation='vertical')
        self.add_widget(root)

        # 顶栏
        topbar = BoxLayout(size_hint_y=None, height=dp(62),
                           padding=[dp(15), dp(8), dp(15), dp(8)])
        _bg(topbar, HEADER)
        title_col = BoxLayout(orientation='vertical')
        title_col.add_widget(lbl('明渠均匀流水力计算', size=18, bold=True,
                                  color=TEXT, halign='center'))
        title_col.add_widget(lbl('宜昌水利  超哥  v2.0', size=11,
                                  color=ACCENT, halign='center', h=20))
        topbar.add_widget(title_col)
        root.add_widget(topbar)

        sv = ScrollView(do_scroll_x=False, bar_width=dp(4),
                        bar_color=ACCENT, bar_inactive_color=CARD)
        root.add_widget(sv)

        self._content = BoxLayout(
            orientation='vertical', size_hint_y=None,
            spacing=dp(12), padding=[dp(12), dp(12), dp(12), dp(24)]
        )
        self._content.bind(minimum_height=self._content.setter('height'))
        sv.add_widget(self._content)

        self._build_content()

    def on_enter(self):
        # 若从注册页返回且注册成功，恢复待选断面
        if self._pending_shape:
            app = App.get_running_app()
            if app.license_mgr.is_registered():
                self._shape = self._pending_shape
                self._spinner.text = self._pending_shape
            self._pending_shape = None
            self._rebuild_params()

    # ── 界面构建 ──────────────────────────────────────────────────

    def _build_content(self):
        c = self._content
        c.clear_widgets()
        self._inputs.clear()

        # Manning 公式说明
        c.add_widget(lbl('Q = (1/n) · A · R^(2/3) · S^(1/2)',
                         size=12, color=ACCENT, halign='center', h=28))

        # ── 计算模式 ──────────────────────────────────────────────
        mode_card = section_card('【计算模式】')
        mode_row = BoxLayout(orientation='horizontal',
                             size_hint_y=None, height=dp(50),
                             spacing=dp(8),
                             padding=[dp(10), dp(4), dp(10), dp(4)])

        def _make_mode_btn(text):
            tb = ToggleButton(
                text=text, group='mode',
                font_name=CN_FONT, font_size=sp(13),
                background_normal='', background_down='',
                background_color=(0, 0, 0, 0),
                color=TEXT,
            )
            _c1, _r1 = _bg(tb, CARD, radius=8)

            def _upd(inst, val):
                _c1.rgba = PRIMARY if inst.state == 'down' else CARD

            tb.bind(state=_upd)
            tb.bind(on_press=lambda inst: self._on_mode(inst.text))
            return tb

        self._btn_mode1 = _make_mode_btn('给定水深  求流量')
        self._btn_mode2 = _make_mode_btn('给定流量  求水深')
        self._btn_mode1.state = 'down'
        mode_row.add_widget(self._btn_mode1)
        mode_row.add_widget(self._btn_mode2)
        mode_card.add_widget(mode_row)
        c.add_widget(mode_card)

        # ── 断面类型 ──────────────────────────────────────────────
        shape_card = section_card('【断面类型】')
        sp_row = BoxLayout(size_hint_y=None, height=dp(50),
                           padding=[dp(10), dp(4), dp(10), dp(4)])
        self._spinner = Spinner(
            text=self._shape,
            values=SHAPES_ALL,
            font_name=CN_FONT, font_size=sp(15),
            background_normal='', background_down='',
            background_color=INPUT,
            color=TEXT,
            option_cls=_SpinnerOption,
            size_hint_y=None, height=dp(42),
        )
        self._spinner.bind(text=self._on_shape)
        sp_row.add_widget(self._spinner)
        shape_card.add_widget(sp_row)

        # 免费/付费提示
        note = lbl('矩形：免费试用    梯形/圆形/三角形/抛物线形：注册后可用',
                   size=11, color=GOLD, halign='center', h=24)
        shape_card.add_widget(note)
        c.add_widget(shape_card)

        # ── 断面参数（动态）──────────────────────────────────────
        self._params_card = section_card('【断面参数】')
        c.add_widget(self._params_card)
        self._rebuild_params()

        # ── 水力参数 ──────────────────────────────────────────────
        hydro_card = section_card('【水力参数】')
        n_inp = inp(hint='例: 0.014', text='0.014')
        S_inp = inp(hint='例: 0.001', text='0.001')
        self._inputs['n'] = n_inp
        self._inputs['S'] = S_inp
        hydro_card.add_widget(row('曼宁糙率 n', n_inp))
        hydro_card.add_widget(row('底坡 i', S_inp))
        c.add_widget(hydro_card)

        # ── 流量输入（给定流量求水深时显示）────────────────────────
        self._Q_card = section_card('【目标流量】')
        Q_inp = inp(hint='例: 10.0', text='')
        self._inputs['Q'] = Q_inp
        self._Q_card.add_widget(row('流量 Q (m3/s)', Q_inp))
        c.add_widget(self._Q_card)
        self._set_Q_card_visible(self._mode == '流量→水深')

        # ── 计算按钮 ──────────────────────────────────────────────
        calc_btn = btn('>>  立即计算', color=PRIMARY, h=56, radius=14)
        calc_btn.bind(on_release=self._calculate)
        c.add_widget(Widget(size_hint_y=None, height=dp(4)))
        c.add_widget(calc_btn)

    def _set_Q_card_visible(self, visible: bool):
        if visible:
            self._Q_card.opacity = 1
            self._Q_card.disabled = False
            self._Q_card.size_hint_y = None
        else:
            self._Q_card.opacity = 0
            self._Q_card.disabled = True
            self._Q_card.size_hint_y = None
            self._Q_card.height = 0

    def _rebuild_params(self):
        pc = self._params_card
        pc.clear_widgets()

        # 重建标题行
        hdr = BoxLayout(size_hint_y=None, height=dp(36),
                        padding=[dp(12), 0, dp(12), 0])
        _bg(hdr, HEADER, radius=10)
        hdr.add_widget(lbl('【断面参数】', size=13, bold=True,
                           color=ACCENT, halign='left', h=36))
        pc.add_widget(hdr)

        # 移除旧断面参数键
        for k in [k for k in self._inputs if k not in ('n', 'S', 'Q')]:
            del self._inputs[k]

        for label_text, key, default, hint in SHAPE_PARAMS[self._shape]:
            if key == 'h' and self._mode == '流量→水深':
                continue  # h 是求解目标，不需要输入
            w = inp(hint=hint, text=default)
            self._inputs[key] = w
            pc.add_widget(row(label_text, w))

    # ── 事件响应 ──────────────────────────────────────────────────

    def _on_mode(self, text):
        # 根据按钮文本精确判断模式（避免两个按钮都含"水深"导致的误判）
        self._mode = '水深→流量' if '求流量' in text else '流量→水深'
        self._set_Q_card_visible(self._mode == '流量→水深')
        self._rebuild_params()

    def _on_shape(self, spinner, shape):
        if shape not in FREE_SHAPES:
            app = App.get_running_app()
            if not app.license_mgr.is_registered():
                # 回退到上次已授权断面
                self._pending_shape = shape
                Clock.schedule_once(
                    lambda dt: setattr(self._spinner, 'text', self._shape), 0.05
                )
                self.manager.transition = SlideTransition(direction='left')
                self.manager.current = 'register'
                return
        self._shape = shape
        self._rebuild_params()

    # ── 取值 ─────────────────────────────────────────────────────

    def _get_float(self, key, name):
        txt = self._inputs[key].text.strip()
        try:
            v = float(txt)
        except ValueError:
            raise ValueError(f'[{name}] 输入无效，请填写数字')
        if v <= 0:
            raise ValueError(f'[{name}] 必须大于 0')
        return v

    # ── 计算 ─────────────────────────────────────────────────────

    def _calculate(self, *_):
        try:
            # 再次检查注册状态（防止绕过选择直接计算）
            if self._shape not in FREE_SHAPES:
                app = App.get_running_app()
                if not app.license_mgr.is_registered():
                    self._pending_shape = self._shape
                    self.manager.transition = SlideTransition(direction='left')
                    self.manager.current = 'register'
                    return

            n = self._get_float('n', '糙率 n')
            S = self._get_float('S', '底坡 i')
            shape = self._shape
            params = {}

            for label_text, key, *_ in SHAPE_PARAMS[shape]:
                if key == 'h' and self._mode == '流量→水深':
                    continue
                params[key] = self._get_float(key, label_text)

            if self._mode == '水深→流量':
                sec = make_section(shape, params)
                Q = manning_Q(sec, n, S)
                v = Q / sec.A
                solved_h = None
            else:
                Q_target = self._get_float('Q', '目标流量 Q')
                solved_h = solve_depth(shape, params, n, S, Q_target)
                params['h'] = solved_h
                sec = make_section(shape, params)
                Q = manning_Q(sec, n, S)
                v = Q / sec.A

            Fr = v / math.sqrt(g * sec.h_m) if sec.h_m > 1e-12 else 0
            C = sec.R ** (1.0 / 6.0) / n

            app = App.get_running_app()
            app.last_result = dict(
                shape=shape, n=n, S=S, Q=Q, v=v,
                sec=sec, Fr=Fr, C=C, solved_h=solved_h,
                params=params,
            )
            self.manager.transition = SlideTransition(direction='left')
            self.manager.current = 'result'

        except Exception as e:
            _show_error(str(e))


# ═══════════════════════════════════════════════
#  ResultScreen
# ═══════════════════════════════════════════════

def _result_row(name, val, unit):
    r = BoxLayout(orientation='horizontal',
                  size_hint_y=None, height=dp(40),
                  padding=[dp(12), 0, dp(12), 0])
    r.add_widget(lbl(name,  size=13, color=(0.65, 0.78, 0.92, 1),
                     halign='left',  size_hint_x=0.48))
    r.add_widget(lbl(val,   size=14, color=YELLOW,
                     halign='right', size_hint_x=0.38))
    r.add_widget(lbl(unit,  size=12, color=(0.55, 0.65, 0.75, 1),
                     halign='left',  size_hint_x=0.14))
    return r


class ResultScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg(self, BG)
        root = BoxLayout(orientation='vertical')
        self.add_widget(root)

        topbar = BoxLayout(size_hint_y=None, height=dp(58),
                           spacing=dp(10),
                           padding=[dp(10), dp(8), dp(15), dp(8)])
        _bg(topbar, HEADER)
        back = btn('< 返回', color=CARD, h=40, radius=8,
                   size_hint_x=None, width=dp(90))
        back.bind(on_release=lambda *_: self._go_back())
        topbar.add_widget(back)
        title_col = BoxLayout(orientation='vertical', size_hint_x=1)
        title_col.add_widget(lbl('计算结果', size=17, bold=True,
                                  color=TEXT, halign='center'))
        title_col.add_widget(lbl('宜昌水利  超哥', size=10,
                                  color=ACCENT, halign='center', h=18))
        topbar.add_widget(title_col)
        topbar.add_widget(Widget(size_hint_x=None, width=dp(90)))
        root.add_widget(topbar)

        sv = ScrollView(do_scroll_x=False, bar_width=dp(4),
                        bar_color=ACCENT, bar_inactive_color=CARD)
        root.add_widget(sv)
        self._body = BoxLayout(
            orientation='vertical', size_hint_y=None,
            spacing=dp(10), padding=[dp(12), dp(12), dp(12), dp(20)]
        )
        self._body.bind(minimum_height=self._body.setter('height'))
        sv.add_widget(self._body)

    def on_enter(self):
        self._render()

    def _go_back(self):
        self.manager.transition = SlideTransition(direction='right')
        self.manager.current = 'input'

    def _render(self):
        self._body.clear_widgets()
        r = App.get_running_app().last_result
        if r is None:
            self._body.add_widget(lbl('无结果', color=WARN, h=40))
            return

        sec = r['sec']
        Fr = r['Fr']
        solved_h = r['solved_h']

        if Fr < 0.95:
            flow_type, flow_color = '缓流  (Fr < 1)', ACCENT
        elif Fr > 1.05:
            flow_type, flow_color = '急流  (Fr > 1)', WARN
        else:
            flow_type, flow_color = '临界流 (Fr ≈ 1)', YELLOW

        # 主要结果大字卡
        hero = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(140),
                         spacing=dp(6), padding=[dp(16), dp(12), dp(16), dp(12)])
        _bg(hero, PRIMARY, radius=12)
        if solved_h is not None:
            hero.add_widget(lbl(f'求解水深  h = {solved_h:.5f} m',
                                size=15, bold=True, color=TEXT,
                                halign='center', h=28))
            hero.add_widget(lbl(f'验证流量  Q = {r["Q"]:.4f} m³/s',
                                size=14, color=TEXT, halign='center', h=24))
        else:
            hero.add_widget(lbl(f'流量  Q = {r["Q"]:.4f} m³/s',
                                size=16, bold=True, color=TEXT,
                                halign='center', h=32))
        hero.add_widget(lbl(f'流速  v = {r["v"]:.4f} m/s',
                            size=14, color=TEXT, halign='center', h=24))
        hero.add_widget(lbl(f'弗汝德数  Fr = {Fr:.4f}   {flow_type}',
                            size=13, color=flow_color, halign='center', h=24))
        self._body.add_widget(hero)

        # 断面几何
        geo = section_card('断面几何')
        for name, val, unit in [
            ('过水面积 A',   f'{sec.A:.4f}',   'm²'),
            ('湿周 χ',      f'{sec.chi:.4f}',  'm'),
            ('水力半径 R',   f'{sec.R:.4f}',   'm'),
            ('水面宽 B',     f'{sec.B:.4f}',   'm'),
            ('水力深度 hm',  f'{sec.h_m:.4f}', 'm'),
        ]:
            geo.add_widget(_result_row(name, val, unit))
        self._body.add_widget(geo)

        # 水力参数
        hyd = section_card('水力参数')
        for name, val, unit in [
            ('曼宁糙率 n', f'{r["n"]:.6f}', ''),
            ('底坡 i',     f'{r["S"]:.6f}  ({r["S"] * 1000:.4f}‰)', ''),
            ('谢才系数 C', f'{r["C"]:.3f}', 'm^(1/2)/s'),
        ]:
            hyd.add_widget(_result_row(name, val, unit))
        self._body.add_widget(hyd)

        # 警告
        if Fr > 1.05:
            box = BoxLayout(size_hint_y=None, height=dp(52),
                            padding=[dp(12), dp(8), dp(12), dp(8)])
            _bg(box, (0.35, 0.07, 0.07, 1), radius=8)
            box.add_widget(lbl('[!] 急流区域：需校核消能设施和护坦设计',
                               size=13, color=WARN, halign='left'))
            self._body.add_widget(box)
        elif 0.95 <= Fr <= 1.05:
            box = BoxLayout(size_hint_y=None, height=dp(52),
                            padding=[dp(12), dp(8), dp(12), dp(8)])
            _bg(box, (0.06, 0.20, 0.35, 1), radius=8)
            box.add_widget(lbl('[i] 临界流：建议验算临界水深和水跃位置',
                               size=13, color=ACCENT, halign='left'))
            self._body.add_widget(box)

        self._body.add_widget(Widget(size_hint_y=None, height=dp(8)))
        back_btn = btn('< 返回修改参数', color=CARD, h=50, radius=10)
        back_btn.bind(on_release=lambda *_: self._go_back())
        self._body.add_widget(back_btn)

        cp = BoxLayout(size_hint_y=None, height=dp(36),
                       padding=[dp(12), dp(4), dp(12), dp(4)])
        cp.add_widget(lbl('© 2025 宜昌水利 超哥 | 明渠水力计算工具 v2.0',
                          size=10, color=(0.40, 0.52, 0.64, 1),
                          halign='center'))
        self._body.add_widget(cp)


# ═══════════════════════════════════════════════
#  RegisterScreen  注册激活界面
# ═══════════════════════════════════════════════

DEVELOPER_EMAIL = "yangchao@126.com"
PRICE_YUAN = "9"


def _open_email_client(device_id: str):
    """打开系统邮件客户端，预填收件人/主题/正文"""
    import urllib.parse
    subject = urllib.parse.quote('注册申请-明渠水力计算工具')
    body = urllib.parse.quote(
        f'您好，\n\n请为以下设备码生成注册码：\n\n设备码：{device_id}\n\n'
        f'（已通过微信支付 {PRICE_YUAN} 元）\n\n谢谢！'
    )
    url = f'mailto:{DEVELOPER_EMAIL}?subject={subject}&body={body}'
    try:
        from kivy.utils import platform
        if platform == 'android':
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_VIEW)
            intent.setData(Uri.parse(url))
            PythonActivity.mActivity.startActivity(intent)
            return
    except Exception:
        pass
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


def _show_wechat_pay_popup(device_id: str):
    """弹出微信收款码 + 操作引导"""
    import os
    if getattr(sys, 'frozen', False):
        app_path = os.path.dirname(sys.executable)
    else:
        app_path = os.path.dirname(os.path.abspath(__file__))
    qr_path = os.path.join(app_path, 'assets', 'wechat_pay.png')

    content = BoxLayout(orientation='vertical', spacing=dp(10),
                        padding=[dp(14), dp(14), dp(14), dp(10)])
    _bg(content, CARD)

    content.add_widget(lbl(f'微信扫码支付  {PRICE_YUAN} 元',
                           size=16, bold=True, color=GOLD,
                           halign='center', h=30))

    if os.path.exists(qr_path):
        img_box = BoxLayout(size_hint_y=None, height=dp(240),
                            padding=[dp(8), dp(4), dp(8), dp(4)])
        img = KivyImage(source=qr_path, allow_stretch=True, keep_ratio=True)
        img_box.add_widget(img)
        content.add_widget(img_box)
    else:
        placeholder = BoxLayout(size_hint_y=None, height=dp(90),
                                padding=[dp(10), dp(10), dp(10), dp(10)])
        _bg(placeholder, INPUT, radius=6)
        placeholder.add_widget(lbl(
            '请将微信收款码图片放置于:\nassets/wechat_pay.png',
            size=13, color=WARN, halign='center'))
        content.add_widget(placeholder)

    content.add_widget(lbl('付款后点击下方按钮发送申请邮件',
                           size=12, color=(0.65, 0.78, 0.92, 1),
                           halign='center', h=22))

    popup = Popup(title='微信扫码付款',
                  title_font=CN_FONT, title_color=GOLD,
                  separator_color=GOLD,
                  background_color=CARD,
                  content=content,
                  size_hint=(0.90, None), height=dp(420))

    btn_row = BoxLayout(orientation='horizontal', size_hint_y=None,
                        height=dp(46), spacing=dp(10))
    paid_btn = btn(f'已付款  去发邮件', color=SUCCESS, h=46, radius=8)
    close_btn = btn('关闭', color=CARD, h=46, radius=8, size_hint_x=0.38)

    def _paid(*_):
        popup.dismiss()
        _open_email_client(device_id)

    paid_btn.bind(on_release=_paid)
    close_btn.bind(on_release=popup.dismiss)
    btn_row.add_widget(paid_btn)
    btn_row.add_widget(close_btn)
    content.add_widget(btn_row)

    popup.open()


class RegisterScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        _bg(self, BG)
        root = BoxLayout(orientation='vertical')
        self.add_widget(root)

        # ── 顶栏 ──────────────────────────────────────────────────
        topbar = BoxLayout(size_hint_y=None, height=dp(58),
                           spacing=dp(10),
                           padding=[dp(10), dp(8), dp(15), dp(8)])
        _bg(topbar, HEADER)
        back = btn('< 返回', color=CARD, h=40, radius=8,
                   size_hint_x=None, width=dp(90))
        back.bind(on_release=lambda *_: self._go_back())
        topbar.add_widget(back)
        title_col = BoxLayout(orientation='vertical', size_hint_x=1)
        title_col.add_widget(lbl('注册激活', size=17, bold=True,
                                  color=TEXT, halign='center'))
        title_col.add_widget(lbl(f'解锁全部断面类型  仅需 {PRICE_YUAN} 元', size=10,
                                  color=GOLD, halign='center', h=18))
        topbar.add_widget(title_col)
        topbar.add_widget(Widget(size_hint_x=None, width=dp(90)))
        root.add_widget(topbar)

        sv = ScrollView(do_scroll_x=False, bar_width=dp(4),
                        bar_color=ACCENT, bar_inactive_color=CARD)
        root.add_widget(sv)
        self._body = BoxLayout(
            orientation='vertical', size_hint_y=None,
            spacing=dp(14), padding=[dp(16), dp(14), dp(16), dp(24)]
        )
        self._body.bind(minimum_height=self._body.setter('height'))
        sv.add_widget(self._body)

        self._build_body()

    def _build_body(self):
        body = self._body
        body.clear_widgets()

        # ── 注册流程说明 ──────────────────────────────────────────
        flow_card = section_card('【注册流程  共4步】')
        steps = [
            ('1', '点击下方设备码  自动复制到剪贴板'),
            ('2', f'点击"扫码支付"  微信付款 {PRICE_YUAN} 元'),
            ('3', '点击"发送申请邮件"  自动填好内容'),
            ('4', '收到自动回复邮件后  填入注册码激活'),
        ]
        for num, text in steps:
            step_row = BoxLayout(orientation='horizontal',
                                 size_hint_y=None, height=dp(34),
                                 spacing=dp(10),
                                 padding=[dp(12), 0, dp(12), 0])
            num_box = BoxLayout(size_hint_x=None, width=dp(24),
                                size_hint_y=None, height=dp(24))
            _bg(num_box, PRIMARY, radius=12)
            num_box.add_widget(lbl(num, size=12, bold=True,
                                   color=TEXT, halign='center'))
            step_row.add_widget(num_box)
            step_row.add_widget(lbl(text, size=13, color=TEXT, halign='left'))
            flow_card.add_widget(step_row)
        body.add_widget(flow_card)

        # ── 设备码（点击复制）────────────────────────────────────
        dev_card = section_card('【第1步  您的设备码】')
        dev_card.add_widget(lbl('点击下方设备码即可复制',
                                size=12, color=(0.55, 0.65, 0.75, 1),
                                halign='center', h=22))

        # 设备码按钮 - 整块可点击
        self._copy_btn = Button(
            text='加载中...',
            font_name=CN_FONT, font_size=sp(17),
            bold=True,
            background_normal='', background_down='',
            background_color=(0, 0, 0, 0),
            color=YELLOW,
            size_hint_y=None, height=dp(54),
        )
        _bg(self._copy_btn, INPUT, radius=8)
        self._copy_btn.bind(on_release=self._copy_device_id)

        copy_hint = lbl('( 点击复制 )', size=11,
                        color=(0.40, 0.55, 0.70, 1),
                        halign='center', h=20)

        copy_wrapper = BoxLayout(orientation='vertical',
                                 size_hint_y=None, height=dp(80),
                                 spacing=dp(4),
                                 padding=[dp(10), dp(4), dp(10), dp(4)])
        copy_wrapper.add_widget(self._copy_btn)
        copy_wrapper.add_widget(copy_hint)
        dev_card.add_widget(copy_wrapper)

        self._copy_status = lbl('', size=12, color=SUCCESS,
                                 halign='center', h=22)
        dev_card.add_widget(self._copy_status)
        body.add_widget(dev_card)

        # ── 第2步：微信支付 ──────────────────────────────────────
        pay_card = section_card(f'【第2步  微信扫码支付 {PRICE_YUAN} 元】')
        pay_btn = btn(f'扫码支付  {PRICE_YUAN} 元（微信）',
                      color=(0.067, 0.502, 0.149, 1), h=52, radius=10)
        pay_btn.bind(on_release=self._show_pay)
        pay_wrapper = BoxLayout(size_hint_y=None, height=dp(60),
                                padding=[dp(10), dp(4), dp(10), dp(4)])
        pay_wrapper.add_widget(pay_btn)
        pay_card.add_widget(pay_wrapper)
        body.add_widget(pay_card)

        # ── 第3步：发送邮件 ──────────────────────────────────────
        mail_card = section_card('【第3步  发送申请邮件】')
        mail_card.add_widget(lbl(f'收件人：{DEVELOPER_EMAIL}',
                                 size=12, color=(0.55, 0.65, 0.75, 1),
                                 halign='center', h=22))
        mail_btn = btn('一键发送申请邮件', color=PRIMARY, h=52, radius=10)
        mail_btn.bind(on_release=self._send_email)
        mail_wrapper = BoxLayout(size_hint_y=None, height=dp(60),
                                 padding=[dp(10), dp(4), dp(10), dp(4)])
        mail_wrapper.add_widget(mail_btn)
        mail_card.add_widget(mail_wrapper)
        mail_card.add_widget(lbl('邮件内容已自动填好，确认发送即可',
                                 size=11, color=(0.45, 0.58, 0.72, 1),
                                 halign='center', h=20))
        body.add_widget(mail_card)

        # ── 第4步：输入注册码 ────────────────────────────────────
        input_card = section_card('【第4步  输入注册码激活】')
        input_card.add_widget(lbl('收到回复邮件后，将注册码填入下方：',
                                  size=12, color=(0.55, 0.65, 0.75, 1),
                                  halign='left', h=22))
        self._code_input = TextInput(
            hint_text='XXXX-XXXX-XXXX-XXXX',
            font_name=CN_FONT, font_size=sp(17),
            input_filter=None, multiline=False,
            background_color=INPUT,
            foreground_color=YELLOW,
            hint_text_color=(0.35, 0.45, 0.58, 1),
            cursor_color=ACCENT,
            size_hint_y=None, height=dp(52),
            padding=[dp(14), dp(13), dp(14), dp(13)],
        )
        self._code_input.bind(text=self._on_code_text)
        code_row = BoxLayout(size_hint_y=None, height=dp(52),
                             padding=[dp(10), 0, dp(10), 0])
        code_row.add_widget(self._code_input)
        input_card.add_widget(code_row)
        body.add_widget(input_card)

        # ── 状态 + 激活 + 返回 ───────────────────────────────────
        self._status_label = lbl('', size=13, color=ACCENT,
                                  halign='center', h=28)
        body.add_widget(self._status_label)

        act_btn = btn('确认激活', color=SUCCESS, h=56, radius=12)
        act_btn.bind(on_release=self._activate)
        body.add_widget(act_btn)

        free_btn = btn('暂不注册，继续使用免费版（仅矩形）',
                       color=CARD, h=44, radius=10)
        free_btn.bind(on_release=lambda *_: self._go_back())
        body.add_widget(free_btn)

    # ── 生命周期 ──────────────────────────────────────────────────

    def on_enter(self):
        app = App.get_running_app()
        did = app.license_mgr.get_device_id()
        self._copy_btn.text = did
        self._copy_status.text = ''
        self._status_label.text = ''
        if app.license_mgr.is_registered():
            self._status_label.text = '已注册激活，享有全功能使用权'
            self._status_label.color = SUCCESS

    # ── 事件 ─────────────────────────────────────────────────────

    def _copy_device_id(self, *_):
        app = App.get_running_app()
        did = app.license_mgr.get_device_id()
        try:
            Clipboard.copy(did)
            self._copy_status.text = '已复制到剪贴板!'
            self._copy_status.color = SUCCESS
        except Exception:
            self._copy_status.text = '复制失败，请手动长按选择'
            self._copy_status.color = WARN
        Clock.schedule_once(lambda dt: setattr(self._copy_status, 'text', ''), 3.0)

    def _show_pay(self, *_):
        app = App.get_running_app()
        did = app.license_mgr.get_device_id()
        _show_wechat_pay_popup(did)

    def _send_email(self, *_):
        app = App.get_running_app()
        did = app.license_mgr.get_device_id()
        _open_email_client(did)
        self._status_label.text = '已打开邮件客户端，请确认发送'
        self._status_label.color = ACCENT

    def _on_code_text(self, instance, value):
        upper = value.upper()
        if upper != value:
            instance.text = upper

    def _activate(self, *_):
        code = self._code_input.text.strip()
        if not code:
            self._status_label.text = '请先填写注册码'
            self._status_label.color = WARN
            return
        app = App.get_running_app()
        if app.license_mgr.activate(code):
            self._status_label.text = '注册成功！已解锁全部断面类型'
            self._status_label.color = SUCCESS
            Clock.schedule_once(lambda dt: self._go_back(), 1.8)
        else:
            self._status_label.text = '注册码无效，请核对设备码后重试'
            self._status_label.color = WARN

    def _go_back(self):
        self.manager.transition = SlideTransition(direction='right')
        self.manager.current = 'input'


# ═══════════════════════════════════════════════
#  App 主入口
# ═══════════════════════════════════════════════

class HydroApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.last_result = None
        self.license_mgr = None

    def build(self):
        Window.clearcolor = BG

        # 桌面调试时固定窗口大小，Android 上自动全屏
        try:
            from android import activity  # noqa: F401
        except ImportError:
            Window.size = (400, 720)

        # 初始化注册管理器
        self.license_mgr = LicenseManager(self.user_data_dir)

        sm = ScreenManager()
        sm.add_widget(InputScreen(name='input'))
        sm.add_widget(ResultScreen(name='result'))
        sm.add_widget(RegisterScreen(name='register'))
        return sm


if __name__ == '__main__':
    HydroApp().run()
