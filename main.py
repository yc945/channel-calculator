"""
明渠均匀流水力计算程序 - Flet 移动端版本
支持: 矩形/梯形/圆形/三角形/抛物线形
支持手机和桌面运行
"""

import math
import flet as ft

# 重力加速度
g = 9.81


class HydroSection:
    """水力断面几何参数"""

    def __init__(self, A: float, chi: float, B: float):
        self.A = max(A, 1e-12)
        self.chi = max(chi, 1e-12)
        self.B = max(B, 1e-12)
        self.R = self.A / self.chi
        self.h_m = self.A / self.B


def section_rect(b: float, h: float) -> HydroSection:
    return HydroSection(b * h, b + 2 * h, b)


def section_trap(b: float, h: float, m: float) -> HydroSection:
    A = (b + m * h) * h
    chi = b + 2 * h * math.sqrt(1 + m ** 2)
    B = b + 2 * m * h
    return HydroSection(A, chi, B)


def section_circ(D: float, h: float) -> HydroSection:
    h = min(h, D * (1 - 1e-9))
    theta = 2.0 * math.acos(1.0 - 2.0 * h / D)
    A = (D ** 2 / 8.0) * (theta - math.sin(theta))
    chi = D * theta / 2.0
    B = D * math.sin(theta / 2.0)
    return HydroSection(A, chi, B)


def section_tri(m: float, h: float) -> HydroSection:
    A = m * h ** 2
    chi = 2.0 * h * math.sqrt(1 + m ** 2)
    B = 2.0 * m * h
    return HydroSection(A, chi, B)


def section_para(B_top: float, h: float) -> HydroSection:
    A = (2.0 / 3.0) * B_top * h
    if B_top > 1e-9 and h > 1e-9:
        xi = 4.0 * h / B_top
        chi = (B_top / 2.0) * (math.sqrt(1 + xi ** 2) + math.log(xi + math.sqrt(1 + xi ** 2)) / xi)
    else:
        chi = B_top
    return HydroSection(A, chi, B_top)


def manning_Q(sec: HydroSection, n: float, S: float) -> float:
    if n <= 0 or S <= 0:
        return 0.0
    v = (1.0 / n) * sec.R ** (2.0 / 3.0) * math.sqrt(S)
    return v * sec.A


def bisect(f, lo: float, hi: float, tol: float = 1e-9, max_iter: int = 150):
    f_lo = f(lo)
    f_hi = f(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = f(mid)
        if abs(f_mid) < tol or (hi - lo) < tol:
            return mid
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def solve_h(shape: str, params: dict, n: float, S: float, Q_target: float) -> float:
    if shape == '圆形 (非满流)':
        h_max = params['D'] * 0.998
    else:
        h_max = 20.0

    def residual(h):
        p = params.copy()
        p['h'] = h
        if shape == '矩形':
            sec = section_rect(p['b'], h)
        elif shape == '梯形':
            sec = section_trap(p['b'], h, p['m'])
        elif shape == '圆形 (非满流)':
            sec = section_circ(p['D'], h)
        elif shape == '三角形':
            sec = section_tri(p['m'], h)
        else:
            sec = section_para(p['B_top'], h)
        return manning_Q(sec, n, S) - Q_target

    while residual(h_max) < 0 and h_max < 100:
        h_max *= 2

    result = bisect(residual, 0.001, h_max)
    if result is None:
        raise ValueError("水深求解失败")
    return result


def main(page: ft.Page):
    page.title = "明渠均匀流水力计算"
    page.scroll = ft.ScrollMode.AUTO
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20

    # 修复弃用警告：使用新的 window 属性
    page.window.width = 400
    page.window.height = 700
    page.window.min_width = 350
    page.window.min_height = 500

    # ========== 状态变量 ==========
    calc_mode = "given_h"  # "given_h" 或 "given_q"

    # 存储输入控件引用
    params_inputs = {}

    # ========== 创建控件 ==========

    # 标题
    title = ft.Text("明渠均匀流水力计算", size=24, weight=ft.FontWeight.BOLD)
    formula = ft.Text("Q = (1/n) · A · R^(2/3) · S^(1/2)",
                      size=14, italic=True, color=ft.Colors.GREY_700)

    # 计算模式选择 - 使用 Row 替代 SegmentedButton 避免兼容性问题
    mode_text = ft.Text("计算模式:", weight=ft.FontWeight.BOLD)

    given_h_btn = ft.ElevatedButton(
        "给定水深求流量",
        on_click=lambda e: set_mode("given_h"),
    )

    given_q_btn = ft.ElevatedButton(
        "给定流量求水深",
        on_click=lambda e: set_mode("given_q"),
    )

    mode_buttons = ft.Row([given_h_btn, given_q_btn], spacing=10)

    # 断面类型下拉
    shape_dropdown = ft.Dropdown(
        label="断面类型",
        value="矩形",
        options=[
            ft.dropdown.Option("矩形"),
            ft.dropdown.Option("梯形"),
            ft.dropdown.Option("圆形 (非满流)"),
            ft.dropdown.Option("三角形"),
            ft.dropdown.Option("抛物线形"),
        ],
        width=200,
        on_change=lambda e: update_params()
    )

    # 断面参数容器
    params_container = ft.Column()

    # 水力参数
    n_input = ft.TextField(label="曼宁糙率 n", value="0.014", width=200)
    S_input = ft.TextField(label="底坡 i", value="0.001", width=200)
    Q_input = ft.TextField(label="流量 Q (m³/s)", value="10.0", width=200)

    # 结果显示
    result_text = ft.Text("", selectable=True, size=14)
    result_container = ft.Container(
        content=result_text,
        padding=15,
        bgcolor=ft.Colors.GREY_100,
        border_radius=10,
        visible=False
    )

    # 状态栏
    status_text = ft.Text("就绪", size=12, color=ft.Colors.GREY_600)

    def set_mode(mode: str):
        nonlocal calc_mode
        calc_mode = mode

        # 更新按钮样式
        if mode == "given_h":
            given_h_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
            given_q_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.GREY_300, color=ft.Colors.BLACK)
            # 隐藏流量输入框
            Q_input.visible = False
        else:
            given_h_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.GREY_300, color=ft.Colors.BLACK)
            given_q_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
            # 显示流量输入框
            Q_input.visible = True

        page.update()

    def update_params():
        """根据断面类型更新参数输入框"""
        params_container.controls.clear()
        params_inputs.clear()

        shape = shape_dropdown.value

        if shape == '矩形':
            params = [('底宽 b (m)', 'b', '5.0')]
        elif shape == '梯形':
            params = [('底宽 b (m)', 'b', '4.0'), ('边坡系数 m', 'm', '1.5')]
        elif shape == '圆形 (非满流)':
            params = [('管径 D (m)', 'D', '1.2')]
        elif shape == '三角形':
            params = [('边坡系数 m', 'm', '1.0')]
        else:  # 抛物线形
            params = [('水面宽 B (m)', 'B_top', '6.0')]

        # 总是添加水深
        params.append(('水深 h (m)', 'h', '2.0'))

        for label, key, default in params:
            input_field = ft.TextField(label=label, value=default, width=200)
            params_container.controls.append(input_field)
            params_inputs[key] = input_field

        page.update()

    def calculate(e):
        """执行计算"""
        try:
            shape = shape_dropdown.value

            n = float(n_input.value)
            S = float(S_input.value)

            if n <= 0 or S <= 0:
                raise ValueError("糙率和底坡必须大于0")

            # 获取断面参数
            params = {}
            for key, input_field in params_inputs.items():
                val = float(input_field.value)
                if val <= 0:
                    raise ValueError(f"{input_field.label} 必须大于0")
                params[key] = val

            h = params.get('h', 2.0)

            if calc_mode == "given_h":
                # 创建断面并计算流量
                if shape == '矩形':
                    sec = section_rect(params['b'], h)
                elif shape == '梯形':
                    sec = section_trap(params['b'], h, params['m'])
                elif shape == '圆形 (非满流)':
                    if h >= params['D']:
                        raise ValueError(f"水深 {h:.3f}m 不能超过管径 {params['D']:.3f}m")
                    sec = section_circ(params['D'], h)
                elif shape == '三角形':
                    sec = section_tri(params['m'], h)
                else:
                    sec = section_para(params['B_top'], h)

                Q = manning_Q(sec, n, S)
                v = Q / sec.A if sec.A > 0 else 0
                Fr = v / math.sqrt(g * sec.h_m) if sec.h_m > 1e-12 else 0

                if Fr < 0.95:
                    flow_type = "缓流 ▼"
                elif Fr > 1.05:
                    flow_type = "急流 ▲"
                else:
                    flow_type = "临界流 ─"

                # 获取底宽/管径信息
                if shape == '矩形':
                    width_info = f"底宽 b = {params['b']:.4f} m"
                elif shape == '梯形':
                    width_info = f"底宽 b = {params['b']:.4f} m, 边坡 m = {params['m']:.3f}"
                elif shape == '圆形 (非满流)':
                    width_info = f"管径 D = {params['D']:.4f} m"
                elif shape == '三角形':
                    width_info = f"边坡 m = {params['m']:.3f}"
                else:
                    width_info = f"水面宽 B = {params['B_top']:.4f} m"

                result = f"""════════════════════════════════════════
明渠均匀流水力计算结果 - {shape}
════════════════════════════════════════

【输入参数】
  糙率 n = {n:.5f}
  底坡 i = {S:.6f} ({S * 1000:.4f}‰)

【断面几何】
  {width_info}
  水深 h = {h:.4f} m
  过水面积 A = {sec.A:.4f} m²
  湿周 χ = {sec.chi:.4f} m
  水力半径 R = {sec.R:.4f} m
  水面宽 B = {sec.B:.4f} m

【水力计算】
  流量 Q = {Q:.4f} m³/s
  流速 v = {v:.4f} m/s
  弗汝德数 Fr = {Fr:.4f}
  流态 = {flow_type}

════════════════════════════════════════
计算完成
"""
                status_text.value = f"✓ 计算完成: Q = {Q:.3f} m³/s"

            else:  # 给定流量求水深
                Q_target = float(Q_input.value)
                if Q_target <= 0:
                    raise ValueError("流量必须大于0")

                # 移除水深参数用于求解
                solve_params = {k: v for k, v in params.items() if k != 'h'}

                # 检查圆形断面水深限制
                if shape == '圆形 (非满流)':
                    # 临时创建一个断面检查最大流量
                    temp_sec = section_circ(solve_params['D'], solve_params['D'] * 0.999)
                    max_Q = manning_Q(temp_sec, n, S)
                    if Q_target > max_Q:
                        raise ValueError(f"流量 {Q_target:.3f} m³/s 超过满管流量 {max_Q:.3f} m³/s")

                h_solved = solve_h(shape, solve_params, n, S, Q_target)

                # 使用求解的水深重新计算
                solve_params['h'] = h_solved
                if shape == '矩形':
                    sec = section_rect(solve_params['b'], h_solved)
                elif shape == '梯形':
                    sec = section_trap(solve_params['b'], h_solved, solve_params['m'])
                elif shape == '圆形 (非满流)':
                    sec = section_circ(solve_params['D'], h_solved)
                elif shape == '三角形':
                    sec = section_tri(solve_params['m'], h_solved)
                else:
                    sec = section_para(solve_params['B_top'], h_solved)

                Q = manning_Q(sec, n, S)
                v = Q / sec.A if sec.A > 0 else 0
                Fr = v / math.sqrt(g * sec.h_m) if sec.h_m > 1e-12 else 0

                if Fr < 0.95:
                    flow_type = "缓流 ▼"
                elif Fr > 1.05:
                    flow_type = "急流 ▲"
                else:
                    flow_type = "临界流 ─"

                # 获取底宽/管径信息
                if shape == '矩形':
                    width_info = f"底宽 b = {solve_params['b']:.4f} m"
                elif shape == '梯形':
                    width_info = f"底宽 b = {solve_params['b']:.4f} m, 边坡 m = {solve_params['m']:.3f}"
                elif shape == '圆形 (非满流)':
                    width_info = f"管径 D = {solve_params['D']:.4f} m"
                    flow_info = f"充满度 h/D = {h_solved / solve_params['D']:.4f}"
                elif shape == '三角形':
                    width_info = f"边坡 m = {solve_params['m']:.3f}"
                else:
                    width_info = f"水面宽 B = {solve_params['B_top']:.4f} m"

                result = f"""════════════════════════════════════════
明渠均匀流水力计算结果 - {shape}
════════════════════════════════════════

【输入参数】
  糙率 n = {n:.5f}
  底坡 i = {S:.6f} ({S * 1000:.4f}‰)
  目标流量 Q = {Q_target:.4f} m³/s

【求解结果】
  水深 h = {h_solved:.5f} m
  {flow_info if shape == '圆形 (非满流)' else ''}

【断面几何】
  {width_info}
  过水面积 A = {sec.A:.4f} m²
  湿周 χ = {sec.chi:.4f} m
  水力半径 R = {sec.R:.4f} m

【水力计算】
  计算流量 Q = {Q:.4f} m³/s
  流速 v = {v:.4f} m/s
  弗汝德数 Fr = {Fr:.4f}
  流态 = {flow_type}

════════════════════════════════════════
计算完成
"""
                status_text.value = f"✓ 计算完成: h = {h_solved:.4f} m"

            result_text.value = result
            result_container.visible = True

        except ValueError as e:
            result_text.value = f"⚠ 输入错误:\n{str(e)}"
            result_container.visible = True
            status_text.value = "✗ 计算失败"
        except Exception as e:
            result_text.value = f"⚠ 计算异常:\n{str(e)}"
            result_container.visible = True
            status_text.value = "✗ 计算失败"

        page.update()

    # 创建按钮
    calc_button = ft.ElevatedButton(
        "计算",
        on_click=calculate,
        icon=ft.Icons.CALCULATE,
        style=ft.ButtonStyle(padding=20, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
    )

    clear_button = ft.OutlinedButton("清空", on_click=lambda e: clear_result())

    def clear_result():
        result_container.visible = False
        result_text.value = ""
        status_text.value = "就绪"
        page.update()

    # 初始化
    update_params()

    # 初始设置模式（给定水深求流量，隐藏Q输入框）
    Q_input.visible = False
    given_h_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
    given_q_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.GREY_300, color=ft.Colors.BLACK)

    # 布局
    page.add(
        title,
        formula,
        ft.Divider(),
        mode_text,
        mode_buttons,
        ft.Divider(height=10),
        ft.Text("断面类型", weight=ft.FontWeight.BOLD),
        shape_dropdown,
        ft.Text("断面参数", weight=ft.FontWeight.BOLD),
        params_container,
        ft.Text("水力参数", weight=ft.FontWeight.BOLD),
        ft.Column([n_input, S_input, Q_input], spacing=10),
        ft.Row([calc_button, clear_button], spacing=10),
        result_container,
        status_text,
    )


if __name__ == "__main__":
    ft.app(target=main)