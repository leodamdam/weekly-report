# -*- coding: utf-8 -*-
"""
BTN설법학교 대웅전 신축 계획(안) — 기획설계 도면 생성 스크립트

출력:
  BTN설법학교_대웅전_계획도면.pdf  (A3 가로, 8매)
  dxf/*.dxf                         (건축사무소 CAD 작업용, 단위 mm)

실행:  python3 make_drawings.py   (필요: reportlab, ezdxf)
치수·형상은 아래 '설계 변수'만 고치면 전 도면에 일괄 반영된다.
"""
import math
import os
import glob

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import ezdxf
from ezdxf.enums import TextEntityAlignment

HERE = os.path.dirname(os.path.abspath(__file__))
DATE = "2026.11.12"
PROJECT = "BTN설법학교 대웅전 신축 계획(안)"
HALL_NAME = "BTN설법학교"

# ---------------------------------------------------------------------------
# 설계 변수 (단위 m)
# ---------------------------------------------------------------------------
BAYS_X = [3.6, 4.2, 4.8, 4.2, 3.6]      # 정면 5칸 : 퇴칸-협칸-어칸-협칸-퇴칸
BAYS_Y = [3.0, 4.2, 4.2, 3.0]           # 측면 4칸 : 전퇴-내진-내진-후퇴
W = sum(BAYS_X)                          # 20.4
D = sum(BAYS_Y)                          # 14.4
XS = [-W / 2]
for b in BAYS_X:
    XS.append(round(XS[-1] + b, 3))
YS = [0.0]
for b in BAYS_Y:
    YS.append(round(YS[-1] + b, 3))

GIDAN = (-W / 2 - 1.5, -1.8, W / 2 + 1.5, D + 1.2)   # 기단 외곽
H_GIDAN = 0.9        # 기단 높이
H_CHOSEOK = 1.2      # 초석 상단 = 기둥 하부
FL = 1.5             # 마루(바닥) 높이
H_COL_TOP = 5.7      # 평주 상부
H_GONGPO_BASE = 5.95
EAVE_OUT = 2.6       # 처마 내밀기 (주심~처마끝)
COL_R = 0.25         # 기둥 반지름 (Ø500)
WALL_T = 0.24

# 감주법: 전면 내고주열(Y2) 중 어칸 두 기둥(X3,X4) 생략 → 청중 시야·카메라 동선 확보
COLS = []
for i, x in enumerate(XS):
    for j, y in enumerate(YS):
        exterior = i in (0, len(XS) - 1) or j in (0, len(YS) - 1)
        interior = (j == 3 and 1 <= i <= 4) or (j == 1 and i in (1, 4))
        if exterior or interior:
            COLS.append((x, y))

# ---------------------------------------------------------------------------
# 선 스타일 (레이어)
#   name: (선굵기mm, RGB, 대시(mm) 또는 None, DXF 색번호, DXF 선종류)
# ---------------------------------------------------------------------------
LAYERS = {
    "A-GRID": (0.13, (0.45, 0.45, 0.45), [5, 1.2, 0.8, 1.2], 8, "CENTER"),
    "A-CUT":  (0.50, (0, 0, 0), None, 7, "CONTINUOUS"),
    "A-OBJ":  (0.25, (0, 0, 0), None, 7, "CONTINUOUS"),
    "A-THIN": (0.13, (0.3, 0.3, 0.3), None, 9, "CONTINUOUS"),
    "A-HID":  (0.18, (0.35, 0.35, 0.35), [1.8, 1.0], 8, "DASHED"),
    "A-DIM":  (0.13, (0.15, 0.15, 0.15), None, 3, "CONTINUOUS"),
    "A-TEXT": (0.13, (0, 0, 0), None, 7, "CONTINUOUS"),
    "A-FURN": (0.18, (0.25, 0.25, 0.25), None, 4, "CONTINUOUS"),
    "A-GRND": (0.70, (0, 0, 0), None, 7, "CONTINUOUS"),
    "B-BRDC": (0.30, (0.80, 0.15, 0.10), None, 1, "CONTINUOUS"),     # 방송설비
    "B-BRDH": (0.25, (0.80, 0.15, 0.10), [2.0, 1.0], 1, "DASHED"),   # 방송 배선
    "B-LGHT": (0.30, (0.05, 0.35, 0.75), None, 5, "CONTINUOUS"),     # 방송조명
}

# ---------------------------------------------------------------------------
# 폰트
# ---------------------------------------------------------------------------
FONT = "KR"


def _register_font():
    cands = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ] + glob.glob("/usr/share/fonts/**/*Noto*CJK*KR*", recursive=True)
    for f in cands:
        if os.path.exists(f):
            if f.endswith(".ttc"):
                pdfmetrics.registerFont(TTFont(FONT, f, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(FONT, f))
            return f
    raise SystemExit("한글 폰트를 찾을 수 없습니다.")


# ---------------------------------------------------------------------------
# 출력 백엔드 : 같은 그리기 함수로 PDF와 DXF를 동시에 만든다
# ---------------------------------------------------------------------------
class PDFView:
    """모델 좌표(m)를 종이 좌표(mm)로 변환해 PDF에 그린다."""

    def __init__(self, c, ox, oy, scale):
        self.c, self.ox, self.oy, self.scale = c, ox, oy, scale
        self.k = scale / 1000.0     # 종이 1mm = 모델 k m

    def P(self, x, y):
        return ((self.ox + x * 1000.0 / self.scale) * mm,
                (self.oy + y * 1000.0 / self.scale) * mm)

    def _style(self, layer):
        lw, col, dash, _, _ = LAYERS[layer]
        self.c.setLineWidth(lw * mm)
        self.c.setStrokeColorRGB(*col)
        self.c.setDash([d * mm for d in dash] if dash else [])

    def _fill(self, fill):
        if isinstance(fill, (int, float)):
            self.c.setFillColorRGB(fill, fill, fill)
        else:
            self.c.setFillColorRGB(*fill)

    def line(self, x1, y1, x2, y2, layer="A-OBJ"):
        self._style(layer)
        a, b = self.P(x1, y1), self.P(x2, y2)
        self.c.line(a[0], a[1], b[0], b[1])

    def poly(self, pts, layer="A-OBJ", closed=False, fill=None, stroke=True):
        self._style(layer)
        p = self.c.beginPath()
        x, y = self.P(*pts[0])
        p.moveTo(x, y)
        for q in pts[1:]:
            x, y = self.P(*q)
            p.lineTo(x, y)
        if closed:
            p.close()
        if fill is not None:
            self._fill(fill)
        self.c.drawPath(p, stroke=1 if stroke else 0, fill=1 if fill is not None else 0)

    def circle(self, cx, cy, r, layer="A-OBJ", fill=None):
        self._style(layer)
        x, y = self.P(cx, cy)
        if fill is not None:
            self._fill(fill)
        self.c.circle(x, y, r * 1000.0 / self.scale * mm, stroke=1,
                      fill=1 if fill is not None else 0)

    def text(self, x, y, t, h=2.5, layer="A-TEXT", anchor="l", rot=0, color=None):
        size = h * mm / 0.72
        px, py = self.P(x, y)
        w = pdfmetrics.stringWidth(t, FONT, size)
        dx = {"l": 0, "c": -w / 2, "r": -w}[anchor]
        col = color or LAYERS[layer][1]
        self.c.saveState()
        self.c.translate(px, py)
        self.c.rotate(rot)
        self.c.setFillColorRGB(*col)
        self.c.setFont(FONT, size)
        self.c.drawString(dx, 0, t)
        self.c.restoreState()


class DXFView:
    """모델 좌표(m)를 DXF(mm)로 기록한다. 축척은 문자 높이 계산에만 쓴다."""

    def __init__(self, doc, scale):
        self.doc, self.msp, self.scale = doc, doc.modelspace(), scale
        self.k = scale / 1000.0

    @staticmethod
    def P(x, y):
        return (round(x * 1000.0, 2), round(y * 1000.0, 2))

    def line(self, x1, y1, x2, y2, layer="A-OBJ"):
        self.msp.add_line(self.P(x1, y1), self.P(x2, y2), dxfattribs={"layer": layer})

    def poly(self, pts, layer="A-OBJ", closed=False, fill=None, stroke=True):
        P = [self.P(*q) for q in pts]
        if fill is not None and fill != 1 and fill != (1, 1, 1):
            h = self.msp.add_hatch(color=8 if isinstance(fill, (int, float)) and fill > 0.3 else 7,
                                   dxfattribs={"layer": layer})
            h.paths.add_polyline_path(P, is_closed=True)
        if stroke:
            self.msp.add_lwpolyline(P, close=closed, dxfattribs={"layer": layer})

    def circle(self, cx, cy, r, layer="A-OBJ", fill=None):
        if fill is not None and fill != 1:
            n = 24
            self.poly([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
                       for i in range(n)], layer, closed=True, fill=fill, stroke=False)
        self.msp.add_circle(self.P(cx, cy), r * 1000.0, dxfattribs={"layer": layer})

    def text(self, x, y, t, h=2.5, layer="A-TEXT", anchor="l", rot=0, color=None):
        al = {"l": TextEntityAlignment.LEFT, "c": TextEntityAlignment.CENTER,
              "r": TextEntityAlignment.RIGHT}[anchor]
        e = self.msp.add_text(t, height=h * self.scale,
                              dxfattribs={"layer": layer, "style": "KR", "rotation": rot})
        e.set_placement(self.P(x, y), align=al)


def new_dxf():
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.styles.new("KR", dxfattribs={"font": "malgun.ttf"})
    allowed = [13, 18, 25, 30, 35, 50, 70]
    for name, (lw, _, _, col, lt) in LAYERS.items():
        lw100 = min(allowed, key=lambda a: abs(a - lw * 100))
        doc.layers.add(name, color=col, linetype=lt, lineweight=lw100)
    return doc


# ---------------------------------------------------------------------------
# 공통 도우미
# ---------------------------------------------------------------------------
def rect(v, x0, y0, x1, y1, layer="A-OBJ", fill=None, stroke=True):
    v.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, closed=True, fill=fill, stroke=stroke)


def arc_pts(cx, cy, r, a0, a1, n=24):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def clip_seg(x1, y1, x2, y2, xmin, ymin, xmax, ymax):
    """Liang-Barsky 선분 클리핑"""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - xmin), (dx, xmax - x1), (-dy, y1 - ymin), (dy, ymax - y1)):
        if p == 0:
            if q < 0:
                return None
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    if t0 > t1:
        return None
    return (x1 + t0 * dx, y1 + t0 * dy, x1 + t1 * dx, y1 + t1 * dy)


def lattice(v, x0, y0, x1, y1, step, layer="A-THIN"):
    """빗살(사선 격자) 꽃살 표현"""
    span = (x1 - x0) + (y1 - y0)
    n = int(span / step) + 2
    for i in range(-n, n + 1):
        c = i * step
        for sgn in (1, -1):
            s = clip_seg(x0 - 2 * span, y0 + sgn * (-2 * span) + c, x0 + 2 * span, y0 + sgn * (2 * span) + c,
                         x0, y0, x1, y1)
            if s and math.hypot(s[2] - s[0], s[3] - s[1]) > 1e-3:
                v.line(*s, layer=layer)


def dim_h(v, x1, x2, y, ext_y=None, label=None, h=2.2):
    k = v.k
    if ext_y is not None:
        v.line(x1, ext_y, x1, y - 1.2 * k * (1 if y < ext_y else -1), "A-DIM")
        v.line(x2, ext_y, x2, y - 1.2 * k * (1 if y < ext_y else -1), "A-DIM")
    v.line(x1 - 1.5 * k, y, x2 + 1.5 * k, y, "A-DIM")
    for x in (x1, x2):
        v.line(x - 0.9 * k, y - 0.9 * k, x + 0.9 * k, y + 0.9 * k, "A-CUT")
    lab = label if label is not None else f"{round((x2 - x1) * 1000):,}"
    v.text((x1 + x2) / 2, y + 0.8 * k, lab, h, "A-DIM", "c")


def dim_v(v, y1, y2, x, ext_x=None, label=None, h=2.2):
    k = v.k
    if ext_x is not None:
        v.line(ext_x, y1, x + 1.2 * k * (1 if x > ext_x else -1), y1, "A-DIM")
        v.line(ext_x, y2, x + 1.2 * k * (1 if x > ext_x else -1), y2, "A-DIM")
    v.line(x, y1 - 1.5 * k, x, y2 + 1.5 * k, "A-DIM")
    for y in (y1, y2):
        v.line(x - 0.9 * k, y - 0.9 * k, x + 0.9 * k, y + 0.9 * k, "A-CUT")
    lab = label if label is not None else f"{round((y2 - y1) * 1000):,}"
    v.text(x - 0.8 * k, (y1 + y2) / 2, lab, h, "A-DIM", "c", rot=90)


def level_mark(v, x, y, label, h=2.2, left=False):
    k = v.k
    s = 1.6 * k
    v.poly([(x, y), (x - s, y + s * 1.2), (x + s, y + s * 1.2)], "A-DIM", closed=True)
    v.line(x - 3 * k if not left else x - 18 * k, y, x + 18 * k if not left else x + 3 * k, y, "A-DIM")
    if left:
        v.text(x - 2.5 * k, y + 2.4 * k, label, h, "A-DIM", "r")
    else:
        v.text(x + 2.5 * k, y + 2.4 * k, label, h, "A-DIM", "l")


def leader(v, x1, y1, x2, y2, t, h=2.3, layer="A-TEXT", anchor=None):
    k = v.k
    v.circle(x1, y1, 0.35 * k, "A-DIM", fill=0)
    v.line(x1, y1, x2, y2, "A-DIM")
    a = anchor or ("l" if x2 >= x1 else "r")
    ext = 4 * k if a == "l" else -4 * k
    v.line(x2, y2, x2 + ext, y2, "A-DIM")
    v.text(x2 + ext + (0.8 * k if a == "l" else -0.8 * k), y2 - 0.8 * k, t, h, layer, a)


def grid_bubble(v, x, y, label, r_mm=3.6):
    v.circle(x, y, r_mm * v.k, "A-DIM")
    v.text(x, y - 1.1 * v.k, label, 2.6, "A-TEXT", "c")


def north_arrow(v, x, y, size_mm=9):
    k = v.k
    r = size_mm / 2 * k
    v.circle(x, y, r, "A-OBJ")
    v.poly([(x, y + r * 1.25), (x - r * 0.4, y - r * 0.6), (x, y - r * 0.25)], "A-OBJ", closed=True, fill=0)
    v.poly([(x, y + r * 1.25), (x + r * 0.4, y - r * 0.6), (x, y - r * 0.25)], "A-OBJ", closed=True)
    v.text(x, y + r * 1.45, "N", 3.0, "A-TEXT", "c")


def person_standing(v, x, y0, layer="A-THIN", facing=1):
    v.circle(x, y0 + 1.6, 0.11, layer)
    v.poly([(x - 0.2, y0 + 1.45), (x + 0.2, y0 + 1.45), (x + 0.17, y0 + 0.8), (x + 0.12, y0),
            (x - 0.12, y0), (x - 0.17, y0 + 0.8)], layer, closed=True)


def person_seated(v, x, y0, layer="A-THIN", facing=1):
    f = facing
    v.circle(x, y0 + 0.92, 0.11, layer)
    v.poly([(x - 0.17 * f, y0 + 0.78), (x + 0.12 * f, y0 + 0.78), (x + 0.16 * f, y0 + 0.2),
            (x + 0.5 * f, y0 + 0.18), (x + 0.5 * f, y0), (x - 0.2 * f, y0)], layer, closed=True)


# ---------------------------------------------------------------------------
# 평면도
# ---------------------------------------------------------------------------
SEATS = []


def compute_seats():
    SEATS.clear()
    xs = [round(1.25 + 0.9 * i, 2) for i in range(10)]
    ys = [round(1.4 + 0.9 * j, 2) for j in range(7)]
    for y in ys:
        for x0 in xs:
            for x in (x0, -x0):
                if abs(x) > 9.4:
                    continue
                if any(math.hypot(x - cx, y - cy) < 0.75 for cx, cy in COLS):
                    continue
                if abs(x) > 8.8 and 3.6 < y < 7.4:      # 영단·신중단 앞
                    continue
                if abs(x) > 8.8 and y < 2.9:             # 측면 출입문 동선
                    continue
                SEATS.append((x, y))
    return len(SEATS)


def draw_plan(v, light=False, annotate=True):
    L = (lambda n: "A-THIN") if light else (lambda n: n)
    gx0, gy0, gx1, gy1 = GIDAN
    k = v.k

    # 기단 + 계단
    rect(v, gx0, gy0, gx1, gy1, L("A-OBJ"))
    rect(v, gx0 + 0.3, gy0 + 0.3, gx1 - 0.3, gy1 - 0.3, "A-THIN")
    for cx, w, n in ((0.0, 3.6, 3), (-8.4, 2.4, 2), (8.4, 2.4, 2)):
        ytop = gy0
        for i in range(n + 1):
            v.line(cx - w / 2, ytop - 0.4 * i, cx + w / 2, ytop - 0.4 * i, L("A-OBJ"))
        for sx in (cx - w / 2 - 0.3, cx + w / 2):
            rect(v, sx, ytop - 0.4 * n, sx + 0.3, ytop, L("A-OBJ"))
    for sgn in (-1, 1):   # 측면 출입 계단
        xa = sgn * (W / 2 + 1.5)
        for i in range(3):
            v.line(xa + sgn * 0.4 * i, 0.3, xa + sgn * 0.4 * i, 2.7, L("A-OBJ"))
        v.line(xa, 0.3, xa + sgn * 0.8, 0.3, L("A-OBJ"))
        v.line(xa, 2.7, xa + sgn * 0.8, 2.7, L("A-OBJ"))

    # 그리드
    for i, x in enumerate(XS):
        v.line(x, gy0 - 2.0, x, gy1 + 0.6, "A-GRID")
        grid_bubble(v, x, gy0 - 2.0 - 3.6 * k - 4.6 * k * 2.1, f"X{i + 1}")
    for j, y in enumerate(YS):
        v.line(gx0 - 2.2, y, gx1 + 0.6, y, "A-GRID")
        grid_bubble(v, gx0 - 2.2 - 3.6 * k - 4.6 * k * 2.0, y, f"Y{j + 1}")

    # 초석
    for x, y in COLS:
        rect(v, x - 0.4, y - 0.4, x + 0.4, y + 0.4, "A-THIN")

    # 벽체·창호
    def wall(ax, ay, bx, by, kind):
        horiz = abs(ay - by) < 1e-6
        if horiz:
            a, b, c0 = min(ax, bx) + COL_R, max(ax, bx) - COL_R, ay
            def R(p, q, t): rect(v, p, c0 - t / 2, q, c0 + t / 2, L("A-CUT"),
                                 fill=None if light else 0.55)
            def Ln(p, q, off): v.line(p, c0 + off, q, c0 + off, L("A-OBJ"))
        else:
            a, b, c0 = min(ay, by) + COL_R, max(ay, by) - COL_R, ax
            def R(p, q, t): rect(v, c0 - t / 2, p, c0 + t / 2, q, L("A-CUT"),
                                 fill=None if light else 0.55)
            def Ln(p, q, off): v.line(c0 + off, p, c0 + off, q, L("A-OBJ"))
        if kind == "wall":
            R(a, b, WALL_T)
        elif kind == "window":
            m = (b - a) * 0.22
            R(a, a + m, WALL_T)
            R(b - m, b, WALL_T)
            for off in (-WALL_T / 2, -0.03, 0.03, WALL_T / 2):
                Ln(a + m, b - m, off)
        elif kind.startswith("door"):
            n = int(kind[4:])
            for off in (-WALL_T / 2, WALL_T / 2):
                Ln(a, b, off)
            seg = (b - a) / n
            for i in range(n):
                p, q = a + seg * i + 0.02, a + seg * (i + 1) - 0.02
                if horiz:
                    rect(v, p, c0 - 0.035, q, c0 + 0.035, L("A-OBJ"), fill=None if light else 0.2)
                else:
                    rect(v, c0 - 0.035, p, c0 + 0.035, q, L("A-OBJ"), fill=None if light else 0.2)

    front_doors = ["door3", "door4", "door4", "door4", "door3"]
    for i in range(5):
        wall(XS[i], 0, XS[i + 1], 0, front_doors[i])
        wall(XS[i], D, XS[i + 1], D, "door2" if i == 2 else "wall")
    for sgn_x in (XS[0], XS[-1]):
        kinds = ["door2", "window", "window", "wall"]
        for j in range(4):
            wall(sgn_x, YS[j], sgn_x, YS[j + 1], kinds[j])
    # 후불벽
    rect(v, XS[1] + COL_R, YS[3] - 0.13, XS[4] - COL_R, YS[3] + 0.13, L("A-CUT"),
         fill=None if light else 0.55)

    # 기둥
    for x, y in COLS:
        v.circle(x, y, COL_R, L("A-CUT"), fill=None if light else 0)

    # 불단·닫집·법상·의례단
    rect(v, -6.0, 9.6, 6.0, 11.15, L("A-FURN"))
    rect(v, -5.8, 9.8, 5.8, 10.95, "A-THIN")
    for x, r in ((-3.6, 0.45), (0, 0.65), (3.6, 0.45)):
        v.circle(x, 10.4, r, L("A-FURN"))
    rect(v, -2.4, 9.2, 2.4, 11.3, "A-HID")
    rect(v, -9.4, 8.0, -7.4, 9.6, L("A-FURN"))
    rect(v, -9.2, 8.2, -7.6, 9.4, "A-THIN")
    rect(v, -0.6, 8.3, 0.6, 8.85, L("A-FURN"))
    rect(v, 9.4, 4.0, 9.95, 7.0, L("A-FURN"))
    rect(v, -9.95, 4.0, -9.4, 7.0, L("A-FURN"))
    # 신도석(방석)
    for x, y in SEATS:
        rect(v, x - 0.27, y - 0.27, x + 0.27, y + 0.27, "A-THIN")

    if annotate:
        T = "A-TEXT"
        v.text(-5.0, 10.2, "불단", 2.2, T, "c")
        v.text(0, 11.65 if not light else 11.65, "후불벽(후불탱화)", 2.2, T, "c")
        if not light:
            v.text(2.5, 9.0, "닫집(상부)", 2.0, "A-HID", "l")
        v.text(-8.4, 9.75, "법상", 2.4, T, "c")
        v.text(-8.4, 7.55, "(설법좌)", 2.0, T, "c")
        v.text(0, 7.95, "이동식 강의대", 2.0, T, "c")
        v.text(9.15, 5.5, "신중단", 2.2, T, "c", rot=90)
        v.text(-9.15, 5.5, "영단", 2.2, T, "c", rot=90)
        if not light:
            v.text(-4.6, 7.4, "내진 — 예불·설법·녹화 공간", 2.6, T, "c")
            v.text(4.6, 7.4, f"좌식 방석 {len(SEATS)}석 (의자 시 약 {int(len(SEATS) * 0.6)}석)", 2.2, T, "c")
            v.text(-8.4, 12.9, "후면 통로 / 수장", 2.4, T, "c")
            v.text(8.4, 12.9, "방송장비 공간", 2.4, T, "c")
            v.text(0, 13.4, "후문(장비 반입)", 2.0, T, "c")
            v.text(0, -0.75, "꽃살 4분합문(정문)", 2.2, T, "c")
            v.text(-8.4, -0.75, "꽃살 3분합문", 2.0, T, "c")
            v.text(8.4, -0.75, "꽃살 3분합문", 2.0, T, "c")
            v.text(0, 0.42, "감주(減柱): 어칸 내고주 생략 → 시야·카메라 축 확보", 1.9, "A-HID", "c")
            v.text(0, gy1 + 0.25, "", 2, T)
            v.text(-12.4, 1.5, "측문", 2.0, T, "c", rot=90)
            v.text(12.4, 1.5, "측문", 2.0, T, "c", rot=90)

    # 치수
    if annotate and not light:
        y1 = gy0 - 2.0 + 0.0
        yb = gy0 - 0.4 - 3.6 * k
        dimy1 = gy0 - 1.2 - 4.0 * k
        dimy2 = dimy1 - 6.0 * k
        for i in range(5):
            dim_h(v, XS[i], XS[i + 1], dimy1)
        dim_h(v, XS[0], XS[-1], dimy2)
        dim_h(v, gx0, gx1, dimy2 - 6.0 * k, label=f"기단 {round((gx1 - gx0) * 1000):,}")
        dimx1 = gx0 - 1.0 - 2.0 * k
        dimx2 = dimx1 - 6.0 * k
        for j in range(4):
            dim_v(v, YS[j], YS[j + 1], dimx1)
        dim_v(v, YS[0], YS[-1], dimx2)
        dim_v(v, gy0, gy1, dimx2 - 6.0 * k, label=f"기단 {round((gy1 - gy0) * 1000):,}")
        _ = (y1, yb)


# ---------------------------------------------------------------------------
# 입면 공통 요소
# ---------------------------------------------------------------------------
def eave_y(x, R):
    """처마 하단선(앙곡: 귀로 갈수록 올라감)"""
    return 7.0 + 0.75 * (min(abs(x), R) / R) ** 3


def bracket(v, x, base=H_GONGPO_BASE, layer="A-OBJ"):
    """다포 공포 1조 (정면 표현)"""
    v.poly([(x - 0.2, base), (x + 0.2, base), (x + 0.3, base + 0.22), (x - 0.3, base + 0.22)], layer, closed=True)
    for i, w in enumerate((0.9, 1.4, 1.0)):
        yb = base + 0.22 + i * 0.27
        rect(v, x - w / 2, yb, x + w / 2, yb + 0.15, layer)
        for sx in (x - w / 2 + 0.12, x, x + w / 2 - 0.12):
            rect(v, sx - 0.09, yb + 0.15, sx + 0.09, yb + 0.27, "A-THIN")


def roof_front(v, half_w, ridge_half, hap_base=10.0, ridge_y=11.6, ridge_h=0.5, hapgak=False):
    """팔작지붕 입면. hapgak=True 이면 측면(합각면)"""
    R = half_w + EAVE_OUT
    n = 60
    xs = [-R + 2 * R * i / n for i in range(n + 1)]
    lower = [(x, eave_y(x, R)) for x in xs]
    upper = [(x, eave_y(x, R) + 0.45) for x in xs]
    tipL, tipR = (-R - 0.25, eave_y(R, R) + 0.85), (R + 0.25, eave_y(R, R) + 0.85)
    # 처마 단면 띠
    v.poly(lower, "A-OBJ")
    v.poly(upper, "A-OBJ")
    v.poly([lower[0], tipL, upper[0]], "A-OBJ")
    v.poly([lower[-1], tipR, upper[-1]], "A-OBJ")
    # 서까래·부연 마구리
    x = -R + 0.6
    while x < R - 0.6:
        v.circle(x, eave_y(x, R) + 0.13, 0.06, "A-THIN")
        rect(v, x - 0.05, eave_y(x, R) + 0.27, x + 0.05, eave_y(x, R) + 0.37, "A-THIN")
        x += 0.33
    hip_top = (ridge_half, hap_base)

    def top_at(x):
        ax = abs(x)
        if ax <= ridge_half:
            return hap_base if hapgak else ridge_y
        t = (ax - ridge_half) / (R + 0.25 - ridge_half)
        return hap_base + t * (tipR[1] - hap_base)

    # 기와골
    x = -R + 0.45
    while x < R - 0.3:
        y0 = eave_y(x, R) + 0.45
        y1 = top_at(x)
        if y1 - y0 > 0.1:
            v.line(x, y0, x, y1, "A-THIN")
        x += 0.3
    # 추녀마루
    for s in (-1, 1):
        v.poly([(s * tipR[0], tipR[1]), (s * hip_top[0], hip_top[1])], "A-OBJ")
        v.poly([(s * (tipR[0] - 0.15), tipR[1] + 0.22), (s * (hip_top[0] - 0.05), hip_top[1] + 0.25)], "A-OBJ")
    if not hapgak:
        for s in (-1, 1):
            v.poly([(s * ridge_half, hap_base), (s * (ridge_half + 0.25), ridge_y)], "A-OBJ")
        v.line(-ridge_half, hap_base, ridge_half, hap_base, "A-THIN")
        # 용마루 + 취두
        rect(v, -ridge_half - 0.25, ridge_y, ridge_half + 0.25, ridge_y + ridge_h, "A-OBJ")
        v.line(-ridge_half - 0.25, ridge_y + ridge_h * 0.45, ridge_half + 0.25, ridge_y + ridge_h * 0.45, "A-THIN")
        for s in (-1, 1):
            bx = s * (ridge_half + 0.25)
            v.poly([(bx, ridge_y), (bx + s * 0.25, ridge_y + 0.2), (bx + s * 0.3, ridge_y + 0.75),
                    (bx + s * 0.05, ridge_y + 1.0), (bx - s * 0.35, ridge_y + 0.9), (bx - s * 0.4, ridge_y + ridge_h)],
                   "A-OBJ")
    else:
        apex = ridge_y + ridge_h
        # 합각 하부 눈썹선
        v.line(-ridge_half, hap_base, ridge_half, hap_base, "A-OBJ")
        # 박공(목기연) 두 줄
        for off in (0.0, 0.22):
            v.poly([(-ridge_half - 0.3 + off, hap_base - 0.05 + off * 0.4), (0, apex - off * 0.9),
                    (ridge_half + 0.3 - off, hap_base - 0.05 + off * 0.4)], "A-OBJ")
        # 풍판
        xx = -ridge_half + 0.3
        while xx < ridge_half - 0.2:
            ytop = apex - 0.25 - abs(xx) * (apex - 0.25 - hap_base) / ridge_half
            if ytop > hap_base + 0.05:
                v.line(xx, hap_base, xx, ytop, "A-THIN")
            xx += 0.25
        # 지네철/박공 장식
        v.circle(0, apex - 0.55, 0.18, "A-THIN")
        # 용마루 마구리 + 취두
        rect(v, -0.35, apex, 0.35, apex + 0.12, "A-OBJ")
        v.poly([(-0.3, apex + 0.12), (-0.25, apex + 0.75), (0.15, apex + 0.95), (0.3, apex + 0.5), (0.3, apex + 0.12)],
               "A-OBJ")


def gidan_elev(v, half, steps):
    rect(v, -half, 0, half, H_GIDAN, "A-OBJ")
    for y in (0.3, 0.6):
        v.line(-half, y, half, y, "A-THIN")
    v.line(-half, H_GIDAN - 0.06, half, H_GIDAN - 0.06, "A-THIN")
    # 장대석 줄눈
    x = -half + 1.8
    row = 0
    for yb, yt in ((0, 0.3), (0.3, 0.6), (0.6, H_GIDAN - 0.06)):
        x = -half + (1.8 if row % 2 == 0 else 0.9)
        while x < half - 0.3:
            v.line(x, yb, x, yt, "A-THIN")
            x += 1.8
        row += 1
    for cx, w, n in steps:
        rect(v, cx - w / 2, 0, cx + w / 2, H_GIDAN, "A-OBJ", fill=1)
        for i in range(1, n):
            v.line(cx - w / 2, H_GIDAN * i / n, cx + w / 2, H_GIDAN * i / n, "A-OBJ")
        for sx in (cx - w / 2 - 0.3, cx + w / 2):
            v.poly([(sx, 0), (sx + 0.3, 0), (sx + 0.3, H_GIDAN + 0.05), (sx, H_GIDAN + 0.05)], "A-OBJ", closed=True)


def ground(v, x0, x1):
    v.line(x0, 0, x1, 0, "A-GRND")
    x = x0
    while x < x1 - 0.4:
        v.line(x, 0, x - 0.3, -0.3, "A-THIN")
        x += 0.6


def column_elev(v, x, top=H_COL_TOP):
    rect(v, x - 0.4, H_GIDAN, x + 0.4, H_CHOSEOK, "A-OBJ")
    # 배흘림: 하부 1/3 지점이 가장 굵음
    pts_l = [(x - 0.22, H_CHOSEOK), (x - 0.25, H_CHOSEOK + 1.4), (x - 0.21, top)]
    pts_r = [(x + 0.21, top), (x + 0.25, H_CHOSEOK + 1.4), (x + 0.22, H_CHOSEOK)]
    v.poly(pts_l + pts_r, "A-OBJ", closed=True)


def door_leaves(v, a, b, n, y0=FL, y1=4.5):
    seg = (b - a) / n
    for i in range(n):
        p, q = a + seg * i, a + seg * (i + 1)
        rect(v, p, y0, q, y1, "A-OBJ")
        rect(v, p + 0.08, y0 + 0.1, q - 0.08, y0 + 0.75, "A-THIN")      # 궁판
        rect(v, p + 0.08, y0 + 0.85, q - 0.08, y1 - 0.1, "A-THIN")
        lattice(v, p + 0.08, y0 + 0.85, q - 0.08, y1 - 0.1, 0.16)
        v.line(p + 0.08, y0 + 0.8, q - 0.08, y0 + 0.8, "A-THIN")
    # 광창(교창)
    rect(v, a, y1, b, y1 + 0.2, "A-OBJ")
    rect(v, a, y1 + 0.2, b, 5.2, "A-OBJ")
    x = a + 0.12
    while x < b - 0.05:
        v.line(x, y1 + 0.2, x, 5.2, "A-THIN")
        x += 0.12


def wall_elev(v, a, b, window=False):
    rect(v, a, H_CHOSEOK, b, FL, "A-OBJ")                                # 하인방
    if window:
        rect(v, a, FL, b, 2.3, "A-OBJ")                                  # 머름
        x = a + 0.4
        while x < b - 0.3:
            v.line(x, FL, x, 2.3, "A-THIN")
            x += 0.4
        m = (b - a) * 0.2
        rect(v, a + m, 2.3, b - m, 3.8, "A-OBJ")                          # 띠살창
        x = a + m + 0.1
        while x < b - m - 0.05:
            v.line(x, 2.3, x, 3.8, "A-THIN")
            x += 0.1
        for y in (2.75, 3.35):
            v.line(a + m, y, b - m, y, "A-THIN")
        v.line(a + m, 2.3 + 0.75, b - m, 2.3 + 0.75, "A-THIN")
    v.line(a, 3.8, b, 3.8, "A-THIN")
    rect(v, a, 4.5, b, 4.7, "A-OBJ")                                      # 중·상인방
    v.line(a, 4.7, b, 4.7, "A-OBJ")


def changbang(v, half):
    rect(v, -half - 0.3, 5.2, half + 0.3, H_COL_TOP, "A-OBJ")            # 창방
    rect(v, -half - 0.35, H_COL_TOP, half + 0.35, H_GONGPO_BASE, "A-OBJ")  # 평방
    for y in (5.35, 5.55):
        v.line(-half - 0.3, y, half + 0.3, y, "A-THIN")


# ---------------------------------------------------------------------------
# 정면도
# ---------------------------------------------------------------------------
def draw_front(v, annotate=True):
    k = v.k
    ground(v, -15.0, 15.0)
    gidan_elev(v, W / 2 + 1.5, [(0, 3.6, 3), (-8.4, 2.4, 2), (8.4, 2.4, 2)])
    leaves = [3, 4, 4, 4, 3]
    for i in range(5):
        a, b = XS[i] + 0.22, XS[i + 1] - 0.22
        rect(v, a, H_CHOSEOK, b, FL, "A-OBJ")
        door_leaves(v, a, b, leaves[i])
    for x in XS:
        column_elev(v, x)
    changbang(v, W / 2)
    for i, x in enumerate(XS):
        bracket(v, x)
        if i < 5:
            for t in (1 / 3, 2 / 3):
                if i == 2:          # 어칸 중앙은 현판
                    continue
                bracket(v, XS[i] + BAYS_X[i] * t)
    roof_front(v, W / 2, ridge_half=7.0)
    # 현판
    rect(v, -1.75, 5.85, 1.75, 6.95, "A-OBJ", fill=1)
    rect(v, -1.62, 5.97, 1.62, 6.83, "A-OBJ")
    v.text(0, 6.2, HALL_NAME, 3.6 * 100 / v.scale, "A-TEXT", "c")
    if annotate:
        right = 13.0
        lv = [(0, "GL ±0"), (H_GIDAN, "기단 +900"), (FL, "FL +1,500"), (H_COL_TOP, "기둥 +5,700"),
              (7.0, "처마 +7,000"), (11.6, "용마루 +11,600"), (12.6, "최고 +12,600")]
        for y, t in lv:
            level_mark(v, right, y, t)
        for i in range(5):
            dim_h(v, XS[i], XS[i + 1], -1.0 - 1.5 * k)
        dim_h(v, XS[0], XS[-1], -1.0 - 7.5 * k)
        leader(v, 1.0, 6.4, 4.2, 8.6, f"현판: {HALL_NAME}", 2.4)
        leader(v, -4.6, 6.6, -7.0, 8.4, "다포식 공포", 2.4)
        leader(v, -3.2, 9.6, -6.0, 13.0, "팔작지붕 · 한식 기와", 2.4)
        leader(v, 0.2, 12.0, 2.2, 13.3, "용마루 · 취두", 2.4)
        leader(v, -6.2, 3.4, -12.6, 3.9, "꽃살 분합문(빗살)", 2.4)
        leader(v, -10.2, 2.4, -12.6, 2.4, "배흘림 원기둥 Ø500", 2.4)
        leader(v, -11.0, 0.45, -12.6, 1.15, "장대석 기단", 2.4)


# ---------------------------------------------------------------------------
# 측면도
# ---------------------------------------------------------------------------
def draw_side(v, annotate=True):
    k = v.k
    c = D / 2
    ys = [y - c for y in YS]
    ground(v, -11.5, 11.5)
    half = D / 2
    # 기단(비대칭: 전면 1.8, 후면 1.2)
    v_g0, v_g1 = GIDAN[1] - c, GIDAN[3] - c
    rect(v, v_g0, 0, v_g1, H_GIDAN, "A-OBJ")
    for y in (0.3, 0.6):
        v.line(v_g0, y, v_g1, y, "A-THIN")
    v.line(v_g0, H_GIDAN - 0.06, v_g1, H_GIDAN - 0.06, "A-THIN")
    # 측면 계단(측문 앞)
    sx0, sx1 = 0.3 - c, 2.7 - c
    rect(v, sx0, 0, sx1, H_GIDAN, "A-OBJ", fill=1)
    for i in (1, 2):
        v.line(sx0, 0.3 * i, sx1, 0.3 * i, "A-OBJ")
    for j in range(4):
        a, b = ys[j] + 0.22, ys[j + 1] - 0.22
        if j == 0:
            rect(v, a, H_CHOSEOK, b, FL, "A-OBJ")
            door_leaves(v, a, b, 2)
        else:
            wall_elev(v, a, b, window=(j in (1, 2)))
            rect(v, a, 4.7, b, 5.2, "A-OBJ")
    for y in ys:
        column_elev(v, y)
    changbang(v, half)
    for j, y in enumerate(ys):
        bracket(v, y)
        if j < 4:
            for t in (1 / 3, 2 / 3):
                bracket(v, ys[j] + BAYS_Y[j] * t)
    roof_front(v, half, ridge_half=3.6, hapgak=True, ridge_y=11.6, ridge_h=0.5)
    if annotate:
        right = 11.6
        lv = [(0, "GL ±0"), (H_GIDAN, "+900"), (FL, "FL +1,500"), (H_COL_TOP, "+5,700"),
              (10.0, "합각 하단 +10,000"), (12.1, "용마루 +12,100")]
        for y, t in lv:
            level_mark(v, right + 0.4, y, t)
        for j in range(4):
            dim_h(v, ys[j], ys[j + 1], -1.0 - 1.5 * k)
        dim_h(v, ys[0], ys[-1], -1.0 - 7.5 * k)
        v.text(ys[0], -1.0 - 12 * k, "← 정면(남)", 2.4, "A-TEXT", "c")
        v.text(ys[-1], -1.0 - 12 * k, "배면(북) →", 2.4, "A-TEXT", "c")
        leader(v, 0.0, 10.9, -4.5, 13.0, "합각(풍판) · 박공", 2.4)
        leader(v, -1.2, 3.0, -9.5, 4.2, "띠살창 · 머름", 2.4, anchor="r")
        leader(v, -5.7, 3.3, -9.5, 2.6, "측문(2분합)", 2.4, anchor="r")


# ---------------------------------------------------------------------------
# 횡단면도 (어칸 중심 X축 절단, 서측을 바라봄)
# ---------------------------------------------------------------------------
def draw_section(v, annotate=True):
    k = v.k
    ground(v, -5.0, 19.4)
    g0, g1 = GIDAN[1], GIDAN[3]
    # 기단 (절단, 채움)
    rect(v, g0, 0, g1, H_GIDAN, "A-CUT", fill=0.82)
    # 전면 계단
    pts = [(g0, H_GIDAN), (g0, 0.6), (g0 - 0.4, 0.6), (g0 - 0.4, 0.3), (g0 - 0.8, 0.3), (g0 - 0.8, 0.0),
           (g0 - 1.2, 0.0), (g0 - 1.2, -0.0)]
    v.poly([(g0, H_GIDAN), (g0, 0.6), (g0 - 0.4, 0.6), (g0 - 0.4, 0.3), (g0 - 0.8, 0.3), (g0 - 0.8, 0.0)],
           "A-CUT")
    _ = pts
    # 초석 + 기둥(입면으로 보임)
    for s in (0.0, D):
        rect(v, s - 0.4, H_GIDAN, s + 0.4, H_CHOSEOK, "A-OBJ", fill=0.7)
        rect(v, s - 0.25, H_CHOSEOK, s + 0.25, H_COL_TOP, "A-OBJ")
    # 내고주(Y4열) / 감주된 Y2열 (뒤편 X2열 기둥이 보임)
    rect(v, YS[3] - 0.4, H_GIDAN, YS[3] + 0.4, H_CHOSEOK, "A-OBJ", fill=0.7)
    rect(v, YS[3] - 0.27, H_CHOSEOK, YS[3] + 0.27, 8.2, "A-OBJ")
    rect(v, YS[1] - 0.25, FL, YS[1] + 0.25, 7.0, "A-HID")
    # 마루
    rect(v, 0.25, FL - 0.15, D - 0.25, FL, "A-CUT", fill=0.25)
    s = 0.25
    while s < D - 0.3:
        rect(v, s, FL - 0.35, s + 0.18, FL - 0.15, "A-THIN")
        s += 1.4
    for s in (2.0, 5.0, 8.0, 11.0):
        rect(v, s - 0.12, H_GIDAN, s + 0.12, FL - 0.35, "A-THIN")   # 동바리

    # 전·후면 창호 절단
    def cut_door(s0):
        rect(v, s0 - 0.12, H_CHOSEOK, s0 + 0.12, FL, "A-CUT", fill=0.25)
        rect(v, s0 - 0.04, FL, s0 + 0.04, 4.5, "A-CUT", fill=0.5)
        rect(v, s0 - 0.12, 4.5, s0 + 0.12, 4.7, "A-CUT", fill=0.25)
        rect(v, s0 - 0.04, 4.7, s0 + 0.04, 5.2, "A-OBJ")
        rect(v, s0 - 0.15, 5.2, s0 + 0.15, H_COL_TOP, "A-CUT", fill=0.25)
        rect(v, s0 - 0.2, H_COL_TOP, s0 + 0.2, H_GONGPO_BASE, "A-CUT", fill=0.25)
    cut_door(0.0)
    cut_door(D)
    bracket(v, 0.0)
    bracket(v, D)
    # 후불벽 (절단)
    rect(v, YS[3] - 0.12 - 0.27, FL, YS[3] - 0.27, 7.4, "A-CUT", fill=0.55)

    # 가구(架構)
    rect(v, YS[1] - 0.4, 6.9, YS[1] + 0.4, 7.7, "A-CUT", fill=0.25)               # 대량(절단)
    rect(v, -0.3, 6.35, YS[1] - 0.4, 6.85, "A-OBJ")                              # 전퇴보
    rect(v, YS[3] + 0.27, 6.35, D + 0.3, 6.85, "A-OBJ")                          # 후퇴보
    rect(v, YS[1] - 0.4, 7.4, YS[3] + 0.27, 8.2, "A-OBJ")                        # 대들보
    for s in (4.6, 9.8):
        rect(v, s - 0.18, 8.2, s + 0.18, 8.55, "A-OBJ")                          # 동자주
    rect(v, 4.2, 8.55, 10.2, 9.05, "A-OBJ")                                      # 종보
    v.poly([(6.8, 9.05), (7.6, 9.05), (7.35, 10.67), (7.05, 10.67)], "A-OBJ", closed=True)  # 대공
    for s, cy in ((0.0, 7.27), (D, 7.27), (4.6, 9.23), (9.8, 9.23), (7.2, 10.85)):
        v.circle(s, cy, 0.18, "A-CUT", fill=0.25)                                # 도리(절단)
    for s in (-0.9, D + 0.9):
        v.circle(s, 7.1, 0.14, "A-CUT", fill=0.25)                               # 외목도리
    # 지붕(서까래 ~ 기와) 절단
    rafter = [(-EAVE_OUT, 7.0), (-0.9, 7.24), (0.0, 7.45), (4.6, 9.41), (7.2, 11.03),
              (9.8, 9.41), (D, 7.45), (D + 0.9, 7.24), (D + EAVE_OUT, 7.0)]
    roof_top = [(x, y + (0.45 if abs(x - 7.2) > 7.2 + 1.5 else 0.75 if abs(x - 7.2) <= 7.2 else 0.6))
                for x, y in rafter]
    roof_top[0] = (-EAVE_OUT - 0.1, 7.5)
    roof_top[-1] = (D + EAVE_OUT + 0.1, 7.5)
    v.poly(rafter + list(reversed(roof_top)), "A-CUT", closed=True, fill=0.82)
    v.poly([(r[0], r[1] + 0.18) for r in rafter], "A-THIN")
    rect(v, 6.85, 11.75, 7.55, 12.25, "A-CUT", fill=0.55)                       # 용마루
    # 우물반자
    v.line(YS[1] + 0.4, 8.25, YS[3] - 0.27, 8.25, "A-CUT")
    s = YS[1] + 0.4
    while s < YS[3] - 0.3:
        rect(v, s, 8.18, s + 0.08, 8.32, "A-THIN", fill=0.3)
        s += 0.6
    # 불단(절단)
    rect(v, 9.6, FL, 11.15, FL + 0.4, "A-CUT", fill=0.82)
    rect(v, 9.8, FL + 0.4, 10.95, FL + 0.9, "A-CUT", fill=0.82)
    rect(v, 9.55, FL + 0.9, 11.2, FL + 1.2, "A-CUT", fill=0.82)
    # 본존불 좌상(외형)
    b = FL + 1.2
    v.poly([(9.7, b), (11.1, b), (11.0, b + 0.45), (9.8, b + 0.45)], "A-OBJ", closed=True)   # 연화대
    v.poly([(9.75, b + 0.45), (10.9, b + 0.45), (10.95, b + 1.9), (10.75, b + 2.2), (10.25, b + 2.2),
            (10.0, b + 1.9), (9.95, b + 1.15), (9.6, b + 1.0), (9.6, b + 0.6)], "A-OBJ", closed=True)
    v.circle(10.5, b + 2.5, 0.3, "A-OBJ")
    v.circle(10.5, b + 2.85, 0.1, "A-OBJ")
    v.poly(arc_pts(10.9, b + 1.9, 1.35, -60, 140), "A-THIN")                    # 광배
    # 닫집
    v.poly([(9.3, 6.4), (11.3, 6.4), (11.3, 6.75), (9.0, 6.75), (9.3, 6.4)], "A-OBJ", closed=True)
    v.poly([(9.1, 6.75), (10.2, 7.25), (11.3, 6.75)], "A-OBJ")
    v.line(11.3, 7.25, 11.3, 6.4, "A-THIN")
    # 사람(축척)
    for s0 in (2.0, 3.0, 4.0, 5.0, 6.0, 7.0):
        person_seated(v, s0, FL, facing=1)
    rect(v, 8.3, FL, 8.85, FL + 1.05, "A-FURN")
    person_standing(v, 9.1, FL)
    # 방송조명 배턴
    for s0, lab in ((YS[1] - 0.4, "L1"), (5.6, "L2"), (8.4, "L3")):
        v.line(s0, 8.25, s0, 7.0, "B-LGHT")
        rect(v, s0 - 0.08, 6.92, s0 + 0.08, 7.08, "B-LGHT", fill=(0.05, 0.35, 0.75))
        v.poly([(s0 - 0.12, 6.9), (s0 + 0.12, 6.9), (s0 + 0.2, 6.55), (s0 - 0.2, 6.55)], "B-LGHT", closed=True)
        v.text(s0, 6.15, lab, 2.2, "B-LGHT", "c", color=LAYERS["B-LGHT"][1])
    # 카메라 C1
    cx, cy = 1.1, FL + 1.5
    for dx in (-0.35, 0.0, 0.35):
        v.line(cx, cy - 0.15, cx + dx, FL, "B-BRDC")
    rect(v, cx - 0.3, cy - 0.15, cx + 0.3, cy + 0.2, "B-BRDC", fill=(0.8, 0.15, 0.1))
    v.line(cx + 0.3, cy + 0.02, 9.6, b + 2.4, "B-BRDH")
    v.line(cx + 0.3, cy + 0.02, 9.6, FL + 0.2, "B-BRDH")
    v.text(cx, cy + 0.45, "C1", 2.2, "B-BRDC", "c", color=LAYERS["B-BRDC"][1])

    if annotate:
        left = -4.6
        lv = [(0, "GL ±0"), (H_GIDAN, "기단 +900"), (FL, "FL +1,500"), (H_COL_TOP, "+5,700"),
              (8.25, "반자 +8,250"), (11.6, "+11,600"), (12.25, "용마루 +12,250")]
        for y, t in lv:
            level_mark(v, left, y, t, left=True)
        ys = [y for y, _ in lv]
        for a, bb in zip(ys[:-1], ys[1:]):
            dim_v(v, a, bb, left + 1.2)
        dim_v(v, FL, 8.25, 12.6, label="반자높이 6,750")
        dim_v(v, FL, 7.4, 13.6, label="보 밑 5,900")
        for j in range(4):
            dim_h(v, YS[j], YS[j + 1], -1.0 - 1.5 * k)
        dim_h(v, YS[0], YS[-1], -1.0 - 7.5 * k)
        dim_h(v, -EAVE_OUT, 0, 5.0, label="처마 2,600", h=2.0)
        T = "A-TEXT"
        leader(v, 7.35, 11.95, 15.6, 13.0, "용마루", 2.2)
        leader(v, 11.6, 8.95, 15.6, 12.3, "한식기와 / 강회다짐 / 적심 / 서까래", 2.2)
        leader(v, 7.2, 10.85, 15.6, 11.6, "종도리 · 대공", 2.2)
        leader(v, 9.8, 9.23, 15.6, 10.9, "중도리", 2.2)
        leader(v, 9.9, 8.8, 15.6, 10.2, "종보 · 동자주", 2.2)
        leader(v, 10.9, 7.8, 15.6, 9.5, "대들보", 2.2)
        leader(v, 11.0, 8.25, 15.6, 8.8, "우물반자 (방송조명 윈치 내장)", 2.2)
        leader(v, 11.27, 4.5, 15.6, 5.2, "후불벽(후불탱화)", 2.2)
        leader(v, 10.4, FL + 1.0, 15.6, 3.2, "불단(수미단) H1,200", 2.2)
        leader(v, 10.5, b + 2.5, 15.6, 6.2, "본존불 좌상 (규격 별도 협의)", 2.2)
        leader(v, 9.4, 6.6, 15.6, 7.3, "닫집", 2.2)
        leader(v, 3.4, FL - 0.25, 6.0, 0.35, "우물마루 / 하부 배선 공간(점검구)", 2.2)
        leader(v, 0.0, 6.4, 2.0, 5.2, "공포(다포)", 2.2)
        leader(v, YS[1], 7.3, -2.6, 9.4, "대량(감주 보강)", 2.2, anchor="l")
        v.text(-EAVE_OUT, 6.55, "낙수선", 2.0, "A-HID", "c")
        v.line(-EAVE_OUT, 6.9, -EAVE_OUT, 0.0, "A-HID")
        v.text(1.0, -1.0 - 12 * k, "← 정면(남)", 2.4, T, "c")
        v.text(D - 1.0, -1.0 - 12 * k, "배면(북) →", 2.4, T, "c")


# ---------------------------------------------------------------------------
# 방송·조명 설비 계획도 (평면 위 오버레이)
# ---------------------------------------------------------------------------
def camera(v, x, y, ang, label, lx, ly, anchor="c"):
    col = LAYERS["B-BRDC"][1]
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    px, py = -uy, ux
    pts = [(x + ux * 0.35 + px * 0.22, y + uy * 0.35 + py * 0.22),
           (x + ux * 0.35 - px * 0.22, y + uy * 0.35 - py * 0.22),
           (x - ux * 0.35 - px * 0.22, y - uy * 0.35 - py * 0.22),
           (x - ux * 0.35 + px * 0.22, y - uy * 0.35 + py * 0.22)]
    v.poly(pts, "B-BRDC", closed=True, fill=col)
    for da in (-20, 20):
        b = math.radians(ang + da)
        v.line(x + ux * 0.35, y + uy * 0.35, x + math.cos(b) * 4.0, y + math.sin(b) * 4.0, "B-BRDH")
    v.text(lx, ly, label, 2.6, "B-BRDC", anchor, color=col)


def draw_broadcast(v):
    draw_plan(v, light=True, annotate=True)
    col = LAYERS["B-BRDC"][1]
    lcol = LAYERS["B-LGHT"][1]
    # 조명 배턴
    for y, lab in ((YS[1] - 0.4, "L1"), (5.6, "L2"), (9.0, "L3")):
        v.line(-9.0, y, 9.0, y, "B-LGHT")
        v.line(-9.0, y + 0.08, 9.0, y + 0.08, "B-LGHT")
        x = -8.4
        while x <= 8.5:
            v.circle(x, y, 0.16, "B-LGHT", fill=lcol)
            x += 1.2
        v.text(9.25, y + 0.2, lab, 2.2, "B-LGHT", "l", color=lcol)
    # 케이블 경로(마루 하부)
    path = [(8.6, 12.2), (8.6, 7.75), (-7.0, 7.75)]
    v.poly(path, "B-BRDH")
    v.poly([(0, 7.75), (0, 0.5)], "B-BRDH")
    v.poly([(-9.0, 0.5), (9.0, 0.5)], "B-BRDH")
    # 바닥 매립 박스
    for i, (x, y) in enumerate([(0, 0.5), (-9.0, 0.5), (9.0, 0.5), (0, 7.75), (-7.0, 7.75), (4.6, 7.75)]):
        rect(v, x - 0.18, y - 0.18, x + 0.18, y + 0.18, "B-BRDC", fill=1)
        v.line(x - 0.18, y - 0.18, x + 0.18, y + 0.18, "B-BRDC")
        v.line(x - 0.18, y + 0.18, x + 0.18, y - 0.18, "B-BRDC")
        v.text(x + 0.3, y - 0.12, f"FB{i + 1}", 1.8, "B-BRDC", "l", color=col)
    # 카메라
    camera(v, 0.0, 1.5, 90, "C1", -0.45, 1.25, "r")
    camera(v, -8.6, 1.7, 58, "C2", -9.35, 2.35)
    camera(v, 8.6, 1.7, 122, "C3", 9.35, 2.35)
    camera(v, 4.6, 8.7, 250, "C4", 5.1, 8.2, "l")
    # 지미집/핸드헬드 동선
    v.text(0.62, 2.3, "지미집·핸드헬드 동선(중앙 통로)", 1.8, "B-BRDC", "l", color=col, rot=90)
    # 중계연결반·장비랙
    rect(v, 7.0, 12.2, 9.8, 13.8, "B-BRDC", fill=(1, 0.92, 0.9))
    v.text(8.4, 13.2, "TP 중계연결반", 2.2, "B-BRDC", "c", color=col)
    v.text(8.4, 12.55, "장비랙 · 무선 수신", 1.9, "B-BRDC", "c", color=col)
    v.poly([(9.8, 13.0), (12.9, 13.0)], "B-BRDC")
    v.poly([(12.9, 13.0), (12.5, 13.25), (12.5, 12.75)], "B-BRDC", closed=True, fill=col)
    v.text(12.9, 13.45, "외부 접속함→중계차", 1.9, "B-BRDC", "r", color=col)
    # 스피커 / 마이크 / 리턴모니터
    def spk(x, y, ang):
        a = math.radians(ang)
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        v.poly([(x + px * 0.3, y + py * 0.3), (x - px * 0.3, y - py * 0.3), (x + ux * 0.45, y + uy * 0.45)],
               "B-BRDC", closed=True, fill=1)
    for x, y, ang in ((-6.6, 2.65, -90), (6.6, 2.65, -90), (-9.75, 10.4, 0), (9.75, 10.4, 180)):
        spk(x, y, ang)
    for x, y in ((0, 8.6), (-8.4, 8.8)):
        v.circle(x, y, 0.14, "B-BRDC", fill=col)
        v.text(x + 0.3, y - 0.1, "MIC", 1.8, "B-BRDC", "l", color=col)
    for x in (-1.3, 1.3):
        rect(v, x - 0.35, 7.3, x + 0.35, 7.45, "B-BRDC", fill=col)
    v.text(1.75, 7.25, "RM", 1.8, "B-BRDC", "l", color=col)


# ---------------------------------------------------------------------------
# 배치도 (개념) 1:500
# ---------------------------------------------------------------------------
def draw_site(v):
    k = v.k
    gx0, gy0, gx1, gy1 = GIDAN
    # 대지 경계(가정)
    v.poly([(-48, -42), (48, -42), (48, 28), (-48, 28)], "A-GRID", closed=True)
    v.text(-47, 26.0, "대지 경계(가정) — 측량도 수령 후 확정", 2.4, "A-TEXT", "l")
    # 대웅전
    rect(v, gx0, gy0, gx1, gy1, "A-OBJ", fill=0.85)
    rect(v, XS[0], 0, XS[-1], D, "A-CUT", fill=0.55)
    rect(v, XS[0] - EAVE_OUT, -EAVE_OUT, XS[-1] + EAVE_OUT, D + EAVE_OUT, "A-HID")
    v.text(0, 6.0, "대웅전", 3.2, "A-TEXT", "c")
    v.text(0, 2.0, f"({HALL_NAME})", 2.6, "A-TEXT", "c")
    # 마당·석탑·진입
    rect(v, -16, -30, 16, -3.2, "A-THIN")
    v.text(0, -8.0, "중정(마당) · 야외 법회/야외 촬영", 2.4, "A-TEXT", "c")
    rect(v, -1.6, -18.6, 1.6, -15.4, "A-OBJ")
    rect(v, -1.0, -18.0, 1.0, -16.0, "A-THIN")
    v.text(2.6, -17.4, "석탑(기존/계획)", 2.2, "A-TEXT", "l")
    rect(v, -3.0, -42, 3.0, -30, "A-THIN")
    v.text(0, -38, "진입로", 2.4, "A-TEXT", "c")
    # 부속동
    rect(v, 22, -14, 42, 4, "A-OBJ")
    v.text(32, -4.0, "부속동(강의실·요사)", 2.4, "A-TEXT", "c")
    v.text(32, -7.5, "— 별도 계획", 2.0, "A-TEXT", "c")
    # 중계차·주차
    rect(v, -44, -36, -22, -24, "B-BRDC")
    for i in range(1, 5):
        v.line(-44 + i * 4.4, -36, -44 + i * 4.4, -31, "A-THIN")
    rect(v, -44, -24, -30, -20, "B-BRDC", fill=(1, 0.92, 0.9))
    v.text(-37, -22.6, "중계차(OB VAN) 전용 1면", 2.0, "B-BRDC", "c", color=LAYERS["B-BRDC"][1])
    v.text(-33, -34.5, "주차", 2.4, "A-TEXT", "c")
    v.poly([(-30, -22), (-22, -12), (-14.5, 8.0), (-12.2, 8.0)], "B-BRDH")
    rect(v, -12.9, 7.4, -12.2, 8.6, "B-BRDC", fill=LAYERS["B-BRDC"][1])
    v.text(-14.0, 9.6, "외부 전원·신호 접속함", 2.0, "B-BRDC", "r", color=LAYERS["B-BRDC"][1])
    v.text(-25.0, -16.0, "케이블 경로(지중 관로)", 2.0, "B-BRDC", "r", color=LAYERS["B-BRDC"][1])
    # 경사로 검토
    v.poly([(gx1, -1.0), (gx1 + 9.0, -1.0), (gx1 + 9.0, 0.6), (gx1, 0.6)], "A-HID", closed=True)
    v.text(gx1 + 5.0, -2.9, "무장애 경사로 검토(1:12, L≈11m)", 1.8, "A-HID", "c")
    # 축선
    v.line(0, -42, 0, gy0 - 0.5, "A-GRID")
    v.line(0, gy1 + 0.5, 0, gy1 + 4, "A-GRID")
    v.text(0.8, -27.0, "가람 중심축", 2.0, "A-GRID", "l")
    north_arrow(v, 40, 18, 12)


# ---------------------------------------------------------------------------
# 시트(PDF)
# ---------------------------------------------------------------------------
A3 = (420, 297)
TB_X = 336   # 표제란 시작 x(mm)


def sheet_frame(c, no, title, scale_txt, notes=None, legend=None):
    c.setDash([])
    c.setLineWidth(0.7 * mm)
    c.setStrokeColorRGB(0, 0, 0)
    c.setDash([])
    c.rect(10 * mm, 10 * mm, 400 * mm, 277 * mm)
    c.setLineWidth(0.35 * mm)
    c.line(TB_X * mm, 10 * mm, TB_X * mm, 287 * mm)

    def T(x, y, s, size=2.6, bold=False, col=(0, 0, 0)):
        c.setFillColorRGB(*col)
        c.setFont(FONT, size * mm / 0.72)
        c.drawString(x * mm, y * mm, s)

    # 표제란(하단)
    rows = [
        ("프로젝트", PROJECT),
        ("현판명", HALL_NAME),
        ("발주(사찰)", "                         (기입)"),
        ("설계단계", "기획설계(안) — 시공용 아님"),
        ("도면명", title),
        ("도면번호", no),
        ("축척", scale_txt),
        ("작성일", DATE),
        ("작성", "발주자 기획안 (PD 검토용)"),
    ]
    y = 128
    c.setLineWidth(0.18 * mm)
    for lab, val in rows:
        c.line(TB_X * mm, y * mm, 410 * mm, y * mm)
        T(TB_X + 2, y - 6.2, lab, 2.2, col=(0.35, 0.35, 0.35))
        size = 3.6 if lab in ("도면명", "도면번호") else 2.4
        if lab == "프로젝트":
            T(TB_X + 18, y - 6.2, "BTN설법학교 대웅전", 2.6)
            T(TB_X + 18, y - 9.6, "신축 계획(안)", 2.4)
        else:
            T(TB_X + 18, y - 6.6 if size > 3 else y - 6.2, val, size)
        y -= 11
    c.line((TB_X + 16) * mm, 128 * mm, (TB_X + 16) * mm, (y + 11) * mm)
    # 검토란
    y += 11
    c.line(TB_X * mm, (y - 11) * mm, 410 * mm, (y - 11) * mm)
    T(TB_X + 2, y - 15.5, "건축사무소 검토 / 날인", 2.2, col=(0.35, 0.35, 0.35))
    c.rect((TB_X + 2) * mm, 12 * mm, 70 * mm, (y - 18 - 12) * mm)
    # 상단: 비고/범례
    yy = 280
    T(TB_X + 2, yy, "비 고", 3.0)
    yy -= 6
    base_notes = [
        "1. 치수 단위 mm, 그리드는 기둥 중심선.",
        "2. 본 도면은 발주자의 공간·규모·용도",
        "   의도를 전달하는 기획 단계 계획안임.",
        "3. 구조·법규·인허가·문화재 심의 검토",
        "   및 실시설계는 건축사무소에서 수행.",
    ]
    for n in base_notes + (notes or []):
        T(TB_X + 2, yy, n, 2.2)
        yy -= 4.4
    if legend:
        yy -= 3
        T(TB_X + 2, yy, "범 례", 3.0)
        yy -= 6
        for sym, txt, col in legend:
            c.setFillColorRGB(*col)
            c.setStrokeColorRGB(*col)
            c.setLineWidth(0.3 * mm)
            if sym == "cam":
                c.rect((TB_X + 3) * mm, (yy - 0.3) * mm, 5 * mm, 3 * mm, fill=1, stroke=0)
            elif sym == "batten":
                c.line((TB_X + 2) * mm, (yy + 1.2) * mm, (TB_X + 9) * mm, (yy + 1.2) * mm)
                c.circle((TB_X + 5.5) * mm, (yy + 1.2) * mm, 1.0 * mm, fill=1, stroke=0)
            elif sym == "cable":
                c.setDash([2 * mm, 1 * mm])
                c.line((TB_X + 2) * mm, (yy + 1.2) * mm, (TB_X + 9) * mm, (yy + 1.2) * mm)
                c.setDash([])
            elif sym == "fb":
                c.rect((TB_X + 4) * mm, (yy - 0.2) * mm, 2.8 * mm, 2.8 * mm, fill=0, stroke=1)
                c.line((TB_X + 4) * mm, (yy - 0.2) * mm, (TB_X + 6.8) * mm, (yy + 2.6) * mm)
                c.line((TB_X + 4) * mm, (yy + 2.6) * mm, (TB_X + 6.8) * mm, (yy - 0.2) * mm)
            elif sym == "sp":
                p = c.beginPath()
                p.moveTo((TB_X + 4) * mm, (yy - 0.3) * mm)
                p.lineTo((TB_X + 4) * mm, (yy + 2.7) * mm)
                p.lineTo((TB_X + 7.5) * mm, (yy + 1.2) * mm)
                p.close()
                c.drawPath(p, stroke=1, fill=0)
            elif sym == "mic":
                c.circle((TB_X + 5.5) * mm, (yy + 1.2) * mm, 1.0 * mm, fill=1, stroke=0)
            T(TB_X + 12, yy, txt, 2.2)
            yy -= 5.2


def view_caption(c, x, y, title, scale_txt):
    c.setDash([])
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(FONT, 4.2 * mm / 0.72)
    c.drawString(x * mm, y * mm, title)
    w = pdfmetrics.stringWidth(title, FONT, 4.2 * mm / 0.72)
    c.setFont(FONT, 2.8 * mm / 0.72)
    c.drawString(x * mm + w + 3 * mm, y * mm, scale_txt)
    c.setLineWidth(0.5 * mm)
    c.line(x * mm, (y - 1.8) * mm, x * mm + w, (y - 1.8) * mm)


def scale_bar(c, x, y, scale, meters=(0, 1, 2, 5, 10)):
    c.setLineWidth(0.2 * mm)
    c.setDash([])
    c.setStrokeColorRGB(0, 0, 0)
    for a, b in zip(meters[:-1], meters[1:]):
        x0 = x + a * 1000 / scale
        x1 = x + b * 1000 / scale
        c.setFillColorRGB(0, 0, 0) if meters.index(a) % 2 == 0 else c.setFillColorRGB(1, 1, 1)
        c.rect(x0 * mm, y * mm, (x1 - x0) * mm, 1.6 * mm, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(FONT, 2.0 * mm / 0.72)
    for m in meters:
        c.drawCentredString((x + m * 1000 / scale) * mm, (y + 2.6) * mm, f"{m}")
    c.drawString((x + meters[-1] * 1000 / scale + 2) * mm, (y + 0.2) * mm, "m")


def cover(c):
    sheet_frame(c, "A-000", "표지 · 설계개요", "NONE")

    def T(x, y, s, size=3.0, col=(0, 0, 0)):
        c.setFillColorRGB(*col)
        c.setFont(FONT, size * mm / 0.72)
        c.drawString(x * mm, y * mm, s)

    T(22, 262, "BTN설법학교 대웅전 신축 계획(안)", 9.0)
    T(22, 250, "기획설계 도면 — 건축사무소 설계 의뢰용", 4.2, (0.3, 0.3, 0.3))
    c.setLineWidth(0.8 * mm)
    c.line(22 * mm, 245 * mm, 320 * mm, 245 * mm)

    area = W * D
    gx0, gy0, gx1, gy1 = GIDAN
    garea = (gx1 - gx0) * (gy1 - gy0)
    rows = [
        ("건물명", f"대웅전 (현판명: {HALL_NAME})"),
        ("용도", "종교시설(사찰 법당) — 예불 · 설법 강의 · 방송 녹화/중계"),
        ("구조", "전통 한식 목구조 (육송 기준), 장대석 기단, 초석 위 원기둥"),
        ("규모", "지상 1층 / 정면 5칸 × 측면 4칸"),
        ("주칸", f"정면 {' + '.join(f'{b:.1f}' for b in BAYS_X)} = {W:.1f}m  |  "
                 f"측면 {' + '.join(f'{b:.1f}' for b in BAYS_Y)} = {D:.1f}m"),
        ("바닥면적", f"{area:,.2f}㎡ ({area / 3.3058:,.1f}평) — 기둥 중심선 기준"),
        ("기단면적", f"{garea:,.2f}㎡ ({garea / 3.3058:,.1f}평) — 기단 {gx1 - gx0:.1f} × {gy1 - gy0:.1f}m"),
        ("높이", "기단 0.9m / 마루 FL+1.5m / 반자 +8.25m / 최고 약 12.6m (취두)"),
        ("지붕·공포", "팔작지붕, 한식 기와 / 다포식 공포, 처마 내밀기 2.6m"),
        ("수용", f"좌식 방석 약 {len(SEATS)}석 (의자 배치 시 약 {int(len(SEATS) * 0.6)}석)"),
        ("특화", "감주법(어칸 내고주 생략)으로 시야 확보, 방송조명 배턴 3열, 카메라 4포지션,"),
        ("", "마루 하부 배선, 중계연결반(TP), 중계차 외부 접속"),
    ]
    y = 236
    for a, b in rows:
        T(22, y, a, 3.0, (0.35, 0.35, 0.35))
        T(50, y, b, 3.0)
        y -= 7.2

    # 도면 목록
    T(22, y - 4, "도면 목록", 4.0)
    y -= 12
    lst = [("A-000", "표지 · 설계개요", "-"), ("A-001", "배치도(개념)", "1:400"),
           ("A-101", "평면도", "1:100"), ("A-102", "방송·조명 설비 계획도", "1:100"),
           ("A-201", "정면도", "1:100"), ("A-202", "측면도", "1:100"),
           ("A-301", "횡단면도", "1:100"), ("A-901", "설계의뢰 체크리스트", "-")]
    for no, nm, sc in lst:
        T(22, y, no, 2.8)
        T(45, y, nm, 2.8)
        T(120, y, sc, 2.8)
        y -= 5.6

    # 오른쪽 열: 기획 의도
    x0 = 175
    yy = 236 - 7.2 * len(rows) - 4
    T(x0, yy, "기획 의도 (PD 노트)", 4.0)
    yy -= 8
    intent = [
        "· '설법학교' — 법당이 곧 강의실이자 스튜디오.",
        "  예불 공간의 위엄은 지키되, 강의·녹화가",
        "  매주 돌아가는 '운영 가능한 법당'이 목표.",
        "· 화면의 주인공은 불단과 법사. 정면 카메라(C1)",
        "  축선에 기둥이 걸리지 않도록 어칸 내고주 생략.",
        "· 조명·전원·신호선은 보이지 않게: 반자 속 윈치,",
        "  마루 하부 배선, 후면 장비 공간으로 정리.",
        "· 꽃살문 전면 개방 시 마당까지 이어지는",
        "  야외 대법회·중계 동선 확보.",
    ]
    for s in intent:
        T(x0, yy, s, 2.7)
        yy -= 5.0

    v = PDFView(c, 175, 30, 250)
    draw_front(v, annotate=False)
    T(175 - 15.5 * 4, 22, "정면 개념도 (S=1:250)", 2.4, (0.35, 0.35, 0.35))


def checklist(c):
    sheet_frame(c, "A-901", "설계의뢰 체크리스트", "NONE")

    def T(x, y, s, size=2.8, col=(0, 0, 0)):
        c.setFillColorRGB(*col)
        c.setFont(FONT, size * mm / 0.72)
        c.drawString(x * mm, y * mm, s)

    T(22, 268, "건축사무소 전달 사항 / 확정 필요 사항", 6.0)
    c.setLineWidth(0.6 * mm)
    c.line(22 * mm, 263 * mm, 320 * mm, 263 * mm)
    cols = [
        ("A. 발주자가 제공할 자료", [
            "□ 대지 측량도(지적·현황), 방위, 고저차",
            "□ 토지이용계획 / 전통사찰·문화재 보호구역 여부",
            "□ 기존 가람 배치도 및 사진",
            "□ 봉안 불상 규격(좌상 높이·폭)과 협시 구성",
            "□ 후불탱화·신중탱화 규격",
            "□ 총사업비 / 목표 준공 시점(법회 일정)",
        ]),
        ("B. 종단·스님 협의 후 확정", [
            "□ 불단·법상·신중단·영단 위치와 의례 동선",
            "□ 현판 서체·글씨(‘BTN설법학교’) 및 낙관",
            "□ 단청 여부와 등급(모로/금단청)",
            "□ 정면 칸수(5칸) · 측면 칸수(4칸) 최종 결정",
        ]),
        ("C. 건축사무소 검토 요청", [
            "□ 감주(어칸 내고주 생략) 시 대량 단면·구조 안정성",
            "□ 목조 법당 화재안전: 불꽃감지기·옥외소화전·",
            "   방수총, 목재 난연 처리, 전기 아크차단기",
            "□ 무장애 접근(기단 900 → 경사로 1:12) 위치",
            "□ 바닥 난방(마루 하부 공간과 배선 간섭)",
            "□ 적설·풍하중, 기와 하중 대비 가구 단면",
        ]),
        ("D. 방송 운영 요구사항 (BTN 녹화 기준)", [
            "□ 방송조명 전용 분전반 (LED 기준 약 15kW+예비)",
            "□ 조명 배턴 L1~L3 전동 윈치, 반자 내 점검 통로",
            "□ 마루 하부 케이블 경로 + 바닥 매립 박스 FB1~6",
            "□ 후면 장비 공간: 중계연결반(TP)·랙·환기",
            "□ 외부 접속함 ↔ 중계차 지중 관로, 차량 1면",
            "□ 저소음 공조(실내 NC-25 이하 목표), 잔향 검토",
            "□ 무대 정면 꽃살문 차광(녹화 시 암막 대응)",
        ]),
    ]
    xs = [22, 175]
    y_pos = [252, 252]
    for i, (h, items) in enumerate(cols):
        col = i % 2
        x = xs[col]
        y = y_pos[col]
        T(x, y, h, 3.6)
        y -= 7
        for it in items:
            T(x + 2, y, it, 2.8)
            y -= 5.4
        y_pos[col] = y - 8

    T(22, 40, "※ 본 패키지(PDF + DXF)는 발주자의 기획 의도 전달용입니다. DXF는 레이어별(A-*, B-*)로 정리되어", 2.8, (0.3, 0.3, 0.3))
    T(22, 34, "   건축사무소에서 바로 기본설계의 바탕도로 쓰실 수 있습니다. 치수는 모두 스크립트 변수로 일괄 수정 가능합니다.", 2.8,
      (0.3, 0.3, 0.3))


def main():
    font = _register_font()
    compute_seats()
    pdf_path = os.path.join(HERE, "BTN설법학교_대웅전_계획도면.pdf")
    c = canvas.Canvas(pdf_path, pagesize=(A3[0] * mm, A3[1] * mm))
    c.setTitle(PROJECT)
    c.setAuthor("기획안")
    c.setSubject("대웅전 기획설계 도면")

    # A-000
    cover(c)
    c.showPage()

    # A-001 배치도
    sheet_frame(c, "A-001", "배치도(개념)", "1:400 (A3)",
                notes=["4. 대지 형상·방위·주변 건물은 가정임.",
                       "5. 중계차 동선·외부 접속함 위치 확인."])
    v = PDFView(c, 173, 160, 400)
    draw_site(v)
    view_caption(c, 20, 20, "배치도(개념)", "S = 1:400")
    scale_bar(c, 120, 20, 400, (0, 5, 10, 20, 30))
    c.showPage()

    # A-101 평면도
    sheet_frame(c, "A-101", "평면도", "1:100 (A3)",
                notes=["4. 어칸 전면 내고주 2본 감주(減柱).",
                       "5. 불단·법상·의례단 위치는 협의 후 확정.",
                       f"6. 좌식 방석 0.9×0.9m 피치, {len(SEATS)}석."])
    v = PDFView(c, 188, 98, 100)
    draw_plan(v)
    north_arrow(v, 13.5, 17.2, 10)
    view_caption(c, 20, 20, "평면도", "S = 1:100")
    scale_bar(c, 90, 20, 100)
    c.showPage()

    # A-102 방송
    sheet_frame(c, "A-102", "방송·조명 설비 계획도", "1:100 (A3)",
                notes=["4. 방송설비는 운영 요구사항이며,",
                       "   상세는 방송·전기 설계자와 협의.",
                       "5. 조명 배턴: 우물반자 내 전동 윈치",
                       "   하강식. L1 전면 키 / L2 청중·보조",
                       "   / L3 강단 역광·탑.",
                       "6. 카메라: C1 메인 정면(어칸 축),",
                       "   C2·C3 좌우 사선, C4 리버스(청중).",
                       "7. 케이블은 전부 마루 하부 은폐.",
                       "8. RM: 법사용 리턴모니터·프롬프터.",
                       "9. TP 중계연결반 ↔ 외부 접속함 ↔",
                       "   중계차(배치도 A-001 참조)."],
                legend=[("cam", "카메라 포지션(C1~C4)", LAYERS["B-BRDC"][1]),
                        ("batten", "방송조명 배턴(L1~L3)", LAYERS["B-LGHT"][1]),
                        ("cable", "마루 하부 케이블 경로", LAYERS["B-BRDC"][1]),
                        ("fb", "바닥 매립 박스(FB)", LAYERS["B-BRDC"][1]),
                        ("sp", "스피커(SP)", LAYERS["B-BRDC"][1]),
                        ("mic", "마이크 단자(MIC)", LAYERS["B-BRDC"][1])])
    v = PDFView(c, 182, 98, 100)
    draw_broadcast(v)
    view_caption(c, 20, 20, "방송·조명 설비 계획도", "S = 1:100")
    scale_bar(c, 140, 20, 100)
    c.showPage()

    # A-201 정면도
    sheet_frame(c, "A-201", "정면도", "1:100 (A3)",
                notes=["4. 배면도는 정면도 준용(어칸 후문).",
                       "5. 앙곡·안허리곡 등 처마 곡은 개념",
                       "   표현이며 실시설계 시 결정.",
                       "6. 현판 서체·크기는 별도 협의."])
    v = PDFView(c, 178, 95, 100)
    draw_front(v)
    view_caption(c, 20, 20, "정면도", "S = 1:100")
    scale_bar(c, 90, 20, 100)
    c.showPage()

    # A-202 측면도
    sheet_frame(c, "A-202", "측면도", "1:100 (A3)",
                notes=["4. 동측면 기준, 서측면은 대칭.",
                       "5. 측문 전면 소형 계단 설치."])
    v = PDFView(c, 160, 95, 100)
    draw_side(v)
    view_caption(c, 20, 20, "측면도(동측)", "S = 1:100")
    scale_bar(c, 100, 20, 100)
    c.showPage()

    # A-301 횡단면도
    sheet_frame(c, "A-301", "횡단면도", "1:100 (A3)",
                notes=["4. 어칸 중심 절단, 서측을 바라봄.",
                       "5. 가구·부재 단면은 개념이며 구조",
                       "   검토 후 확정.",
                       "6. 반자 높이 6,750(FL 기준)으로",
                       "   방송조명 각도·열 배출 확보."])
    v = PDFView(c, 108, 95, 100)
    draw_section(v)
    view_caption(c, 20, 20, "횡단면도", "S = 1:100")
    scale_bar(c, 90, 20, 100)
    c.showPage()

    # A-901
    checklist(c)
    c.showPage()
    c.save()

    # DXF
    ddir = os.path.join(HERE, "dxf")
    os.makedirs(ddir, exist_ok=True)
    for name, fn, scale in (("A-001_site-plan", draw_site, 400),
                            ("A-101_floor-plan", draw_plan, 100),
                            ("A-102_broadcast-plan", draw_broadcast, 100),
                            ("A-201_front-elevation", draw_front, 100),
                            ("A-202_side-elevation", draw_side, 100),
                            ("A-301_section", draw_section, 100)):
        doc = new_dxf()
        dv = DXFView(doc, scale)
        fn(dv)
        doc.saveas(os.path.join(ddir, f"BTN_daeungjeon_{name}.dxf"))

    print("font:", font)
    print("seats:", len(SEATS))
    print("pdf:", pdf_path)


if __name__ == "__main__":
    main()
