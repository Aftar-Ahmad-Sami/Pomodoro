"""52/17 Pomodoro timer for Windows.

Work for 52 minutes, then take a 17 minute break. Repeat.
Graphics are rendered with Pillow (supersampled for smooth edges) and
layered on a tkinter canvas.
"""

import ctypes
import math
import os
import shutil
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFilter, ImageTk

try:
    import winsound
except ImportError:  # Non-Windows fallback: no sound
    winsound = None

try:
    import winreg
    from winotify import Notification, audio
except ImportError:  # No toast support: fall back to sound + window pop only
    Notification = None

APP_ID = "Pomodoro.52-17"
WORK_MINUTES = 52
BREAK_MINUTES = 17
SESSIONS_PER_SET = 4
TICK_MS = 200

W, H = 380, 640  # logical window size, scaled by DPI
SS = 3  # supersampling factor for rendered graphics
LANCZOS = Image.Resampling.LANCZOS

BG_TOP = (24, 21, 38)
BG_BOTTOM = (10, 10, 16)
FG = "#f4f4f8"
MUTED = "#8b8ba3"
FAINT = "#5c5c74"
PALETTES = {
    "work": ((255, 107, 107), (255, 169, 77)),
    "break": ((46, 230, 168), (63, 169, 245)),
}

RING_CENTER = (190, 252)
RING_RADIUS = 118
RING_STROKE = 12


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def register_toast_identity():
    """Registers the app's name and icon for toasts; unpackaged apps need this
    per-user registry entry, otherwise Windows hides or mislabels them.
    Returns a stable icon path for the toast image."""
    icon_dir = os.path.join(os.environ["LOCALAPPDATA"], "Pomodoro")
    os.makedirs(icon_dir, exist_ok=True)
    icon = os.path.join(icon_dir, "icon.png")
    shutil.copyfile(resource_path(os.path.join("assets", "icon.png")), icon)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Pomodoro")
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon)
    return icon


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def hex_color(rgb):
    return "#%02x%02x%02x" % rgb


def diagonal_gradient(w, h, c1, c2):
    v = Image.linear_gradient("L")
    mask = Image.blend(v, v.transpose(Image.Transpose.ROTATE_90), 0.5).resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), mask)


# ---------- Rendering ----------


def render_background(s, accent):
    w, h = round(W * s), round(H * s)
    grad = Image.linear_gradient("L").resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), BG_BOTTOM), Image.new("RGB", (w, h), BG_TOP), grad)

    # Soft accent glow behind the ring, blurred at low resolution for speed
    q = 4
    glow = Image.new("L", (w // q, h // q), 0)
    cx, cy = RING_CENTER[0] * s / q, RING_CENTER[1] * s / q
    r = 150 * s / q
    ImageDraw.Draw(glow).ellipse((cx - r, cy - r, cx + r, cy + r), fill=62)
    glow = glow.filter(ImageFilter.GaussianBlur(70 * s / q)).resize((w, h), Image.Resampling.BILINEAR)
    return Image.composite(Image.new("RGB", (w, h), accent), img, glow)


def render_ring(s, fraction, colors):
    pad = 28
    size = round((RING_RADIUS + pad) * 2 * s)
    big = size * SS
    c = big / 2
    r = RING_RADIUS * s * SS
    sw = round(RING_STROKE * s * SS)
    box = (c - r - sw / 2, c - r - sw / 2, c + r + sw / 2, c + r + sw / 2)

    track = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(track).ellipse(box, outline=(255, 255, 255, 20), width=sw)

    arc = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(arc)
    extent = 360 * fraction
    end_angle = -90 + extent
    if extent > 0.05:
        steps = max(1, math.ceil(extent / 1.5))
        for i in range(steps):
            a0 = -90 + extent * i / steps
            a1 = -90 + extent * (i + 1) / steps
            col = lerp(colors[0], colors[1], (a0 + 90) / 360)
            d.arc(box, a0, a1 + 0.6, fill=col + (255,), width=sw)
        for ang in (-90, end_angle):
            col = lerp(colors[0], colors[1], (ang + 90) / 360)
            x = c + r * math.cos(math.radians(ang))
            y = c + r * math.sin(math.radians(ang))
            d.ellipse((x - sw / 2, y - sw / 2, x + sw / 2, y + sw / 2), fill=col + (255,))

    # Bright knob marking the current position
    x = c + r * math.cos(math.radians(end_angle))
    y = c + r * math.sin(math.radians(end_angle))
    k = sw * 0.3
    d.ellipse((x - k, y - k, x + k, y + k), fill=(255, 255, 255, 255))

    track = track.resize((size, size), LANCZOS)
    arc = arc.resize((size, size), LANCZOS)
    glow = arc.filter(ImageFilter.GaussianBlur(10 * s))
    glow.putalpha(glow.getchannel("A").point(lambda v: int(v * 0.9)))
    return Image.alpha_composite(Image.alpha_composite(track, glow), arc)


def render_button(s, kind, colors, hover, primary):
    diam = 68 if primary else 48
    pad = 22 if primary else 4
    size = round((diam + pad * 2) * s)
    big = size * SS
    c = big / 2
    rad = diam * s * SS / 2
    u = diam * s * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    circle = (c - rad, c - rad, c + rad, c + rad)

    if primary:
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).ellipse(circle, fill=255)
        c1, c2 = colors
        if hover:
            c1, c2 = lerp(c1, (255, 255, 255), 0.15), lerp(c2, (255, 255, 255), 0.15)
        img.paste(diagonal_gradient(big, big, c1, c2), (0, 0), mask)
        icon_color = (255, 255, 255, 255)
    else:
        fill = (255, 255, 255, 30 if hover else 14)
        ImageDraw.Draw(img).ellipse(circle, fill=fill, outline=(255, 255, 255, 34), width=round(s * SS))
        icon_color = (236, 236, 245, 255) if hover else (196, 196, 214, 255)

    d = ImageDraw.Draw(img)
    if kind == "play":
        d.polygon([(c - 0.11 * u, c - 0.17 * u), (c - 0.11 * u, c + 0.17 * u), (c + 0.18 * u, c)], fill=icon_color)
    elif kind == "pause":
        bw, bh, gap = 0.085 * u, 0.30 * u, 0.075 * u
        for x0 in (c - gap / 2 - bw, c + gap / 2):
            d.rounded_rectangle((x0, c - bh / 2, x0 + bw, c + bh / 2), radius=bw * 0.35, fill=icon_color)
    elif kind == "skip":
        d.polygon([(c - 0.15 * u, c - 0.14 * u), (c - 0.15 * u, c + 0.14 * u), (c + 0.07 * u, c)], fill=icon_color)
        d.rounded_rectangle((c + 0.09 * u, c - 0.14 * u, c + 0.15 * u, c + 0.14 * u), radius=0.02 * u, fill=icon_color)
    elif kind == "reset":
        r = 0.18 * u
        lw = round(0.055 * u)
        d.arc((c - r - lw / 2, c - r - lw / 2, c + r + lw / 2, c + r + lw / 2), -40, 255, fill=icon_color, width=lw)
        tip_y = c - r
        d.polygon([(c + 0.10 * u, tip_y), (c - 0.02 * u, tip_y - 0.10 * u), (c - 0.02 * u, tip_y + 0.10 * u)], fill=icon_color)

    img = img.resize((size, size), LANCZOS)
    if primary:
        # Colored halo under the primary button
        halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        hr = rad / SS
        hc = size / 2
        ImageDraw.Draw(halo).ellipse((hc - hr, hc - hr + 4 * s, hc + hr, hc + hr + 4 * s), fill=colors[0] + (150 if hover else 110,))
        halo = halo.filter(ImageFilter.GaussianBlur(12 * s))
        img = Image.alpha_composite(halo, img)
    return img


def render_toggle(s, on, colors):
    w, h = 38, 22
    bw, bh = round(w * s * SS), round(h * s * SS)
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if on:
        mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=bh / 2, fill=255)
        img.paste(diagonal_gradient(bw, bh, *colors), (0, 0), mask)
    else:
        d.rounded_rectangle((0, 0, bw - 1, bh - 1), radius=bh / 2, fill=(255, 255, 255, 34))
    m = bh * 0.14
    kd = bh - 2 * m
    kx = bw - m - kd if on else m
    d.ellipse((kx, m, kx + kd, m + kd), fill=(255, 255, 255, 255) if on else (190, 190, 206, 255))
    return img.resize((round(w * s), round(h * s)), LANCZOS)


def render_dot(s, filled, color):
    size = round(10 * s)
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if filled:
        d.ellipse((0, 0, big - 1, big - 1), fill=color + (255,))
    else:
        d.ellipse((0, 0, big - 1, big - 1), outline=(255, 255, 255, 60), width=round(1.5 * s * SS))
    return img.resize((size, size), LANCZOS)


# ---------- App ----------


class PomodoroApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.s = root.winfo_fpixels("1i") / 96

        self.phase = "work"
        self.duration = WORK_MINUTES * 60
        self.remaining = float(self.duration)
        self.end_time = None  # monotonic timestamp while running, None while paused
        self.sessions_done = 0

        self.always_on_top = False
        self.auto_start = True
        self.hover = None
        self._images = {}
        self._ring_key = None
        self._bg_phase = None

        self.toast_icon = None
        if Notification:
            try:
                self.toast_icon = register_toast_identity()
            except OSError:
                pass

        self._setup_window()
        self._build_ui()
        self._render()
        self.root.after(TICK_MS, self._tick)

    def px(self, v):
        return v * self.s

    def _setup_window(self):
        self.root.configure(bg=hex_color(BG_TOP))
        self.root.resizable(False, False)
        self.root.geometry(f"{round(W * self.s)}x{round(H * self.s)}")
        try:
            self.root.iconbitmap(default=resource_path(os.path.join("assets", "icon.ico")))
        except tk.TclError:
            pass
        self._style_titlebar()

    def _style_titlebar(self):
        """Dark title bar matching the background (Windows 11)."""
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            dwm = ctypes.windll.dwmapi
            dark = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)  # DWMWA_USE_IMMERSIVE_DARK_MODE
            r, g, b = BG_TOP
            caption = ctypes.c_int(r | g << 8 | b << 16)
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)  # DWMWA_CAPTION_COLOR
        except (AttributeError, OSError):
            pass

    def _cached(self, key, factory):
        if key not in self._images:
            self._images[key] = ImageTk.PhotoImage(factory())
        return self._images[key]

    # ---------- UI ----------

    def _build_ui(self):
        families = set(tkfont.families())

        def pick(*names):
            return next((n for n in names if n in families), "Segoe UI")

        display = pick("Segoe UI Variable Display Light", "Segoe UI Light")
        semibold = pick("Segoe UI Variable Text Semibold", "Segoe UI Semibold")
        text = pick("Segoe UI Variable Text", "Segoe UI")

        px = self.px
        c = self.canvas = tk.Canvas(
            self.root, width=px(W), height=px(H), highlightthickness=0, bd=0, bg=hex_color(BG_TOP)
        )
        c.pack()

        self.bg_item = c.create_image(0, 0, anchor="nw")

        # Header: logo + name
        try:
            logo = Image.open(resource_path(os.path.join("assets", "icon.png"))).resize(
                (round(px(24)), round(px(24))), LANCZOS
            )
            self._logo = ImageTk.PhotoImage(logo)
            c.create_image(px(28), px(36), image=self._logo, anchor="w")
        except OSError:
            pass
        c.create_text(px(60), px(36), text="Pomodoro", font=(semibold, 11), fill=FG, anchor="w")
        c.create_text(px(W - 28), px(36), text=f"{WORK_MINUTES} / {BREAK_MINUTES}", font=(text, 10), fill=FAINT, anchor="e")

        # Ring and its text
        cx, cy = RING_CENTER
        self.ring_item = c.create_image(px(cx), px(cy))
        self.phase_text = c.create_text(px(cx), px(cy - 52), font=(semibold, 10))
        self.time_text = c.create_text(px(cx), px(cy + 2), font=(display, 46), fill=FG)
        self.sub_text = c.create_text(px(cx), px(cy + 52), font=(text, 10), fill=MUTED)

        # Session progress dots
        self.dot_items = []
        spacing = 20
        start = cx - spacing * (SESSIONS_PER_SET - 1) / 2
        for i in range(SESSIONS_PER_SET):
            self.dot_items.append(c.create_image(px(start + i * spacing), px(418)))
        self.sessions_text = c.create_text(px(cx), px(444), font=(text, 10), fill=MUTED)

        # Controls
        self.buttons = {
            "reset": c.create_image(px(cx - 92), px(522)),
            "toggle": c.create_image(px(cx), px(522)),
            "skip": c.create_image(px(cx + 92), px(522)),
        }
        actions = {"reset": self.reset, "toggle": self.toggle, "skip": self.skip}
        for name, item in self.buttons.items():
            c.tag_bind(item, "<Enter>", lambda e, n=name: self._set_hover(n))
            c.tag_bind(item, "<Leave>", lambda e: self._set_hover(None))
            c.tag_bind(item, "<Button-1>", lambda e, a=actions[name]: a())

        # Option toggles
        self.toggles = {}
        for name, label, x in (("auto_start", "Auto-start", 62), ("always_on_top", "Always on top", 200)):
            sw = c.create_image(px(x), px(600), anchor="w")
            lbl = c.create_text(px(x + 46), px(600), text=label, font=(text, 10), fill=MUTED, anchor="w")
            self.toggles[name] = sw
            for item in (sw, lbl):
                c.tag_bind(item, "<Button-1>", lambda e, n=name: self._flip(n))
                c.tag_bind(item, "<Enter>", lambda e: c.config(cursor="hand2"))
                c.tag_bind(item, "<Leave>", lambda e: c.config(cursor=""))

        self.root.bind("<space>", lambda e: self.toggle())
        self.root.bind("r", lambda e: self.reset())
        self.root.bind("s", lambda e: self.skip())

    def _set_hover(self, name):
        self.hover = name
        self.canvas.config(cursor="hand2" if name else "")
        self._render_controls()

    def _flip(self, name):
        setattr(self, name, not getattr(self, name))
        if name == "always_on_top":
            self._apply_topmost()
        self._render_controls()

    def _render_controls(self):
        s, phase = self.s, self.phase
        colors = PALETTES[phase]
        for name, item in self.buttons.items():
            kind = ("pause" if self.running else "play") if name == "toggle" else name
            hover = self.hover == name
            primary = name == "toggle"
            key = ("btn", kind, phase if primary else None, hover)
            img = self._cached(key, lambda: render_button(s, kind, colors, hover, primary))
            self.canvas.itemconfig(item, image=img)
        for name, item in self.toggles.items():
            on = getattr(self, name)
            img = self._cached(("toggle", on, phase), lambda: render_toggle(s, on, colors))
            self.canvas.itemconfig(item, image=img)

    def _render(self):
        s, phase = self.s, self.phase
        colors = PALETTES[phase]

        if self._bg_phase != phase:
            self._bg_phase = phase
            bg = self._cached(("bg", phase), lambda: render_background(s, colors[0]))
            self.canvas.itemconfig(self.bg_item, image=bg)

        fraction = min(1.0, max(0.0, 1 - self.remaining / self.duration))
        ring_key = (phase, round(fraction * 360 * 4))
        if ring_key != self._ring_key:
            self._ring_key = ring_key
            self._ring_img = ImageTk.PhotoImage(render_ring(s, fraction, colors))
            self.canvas.itemconfig(self.ring_item, image=self._ring_img)

        secs = max(0, math.ceil(self.remaining - 0.05))
        mins, sec = divmod(secs, 60)
        label = "Focus" if phase == "work" else "Break"
        if self.running:
            sub = "until break" if phase == "work" else "until focus"
        elif self.remaining >= self.duration:
            sub = "press space to start"
        else:
            sub = "paused"

        c = self.canvas
        c.itemconfig(self.phase_text, text="  ".join(label.upper()), fill=hex_color(colors[0]))
        c.itemconfig(self.time_text, text=f"{mins:02d}:{sec:02d}")
        c.itemconfig(self.sub_text, text=sub)

        filled = self.sessions_done % SESSIONS_PER_SET
        if self.sessions_done and filled == 0:
            filled = SESSIONS_PER_SET
        for i, item in enumerate(self.dot_items):
            on = i < filled
            img = self._cached(("dot", on, phase), lambda: render_dot(s, on, colors[0]))
            c.itemconfig(item, image=img)

        n = self.sessions_done
        if n:
            h, m = divmod(n * WORK_MINUTES, 60)
            focused = f"{h}h {m:02d}m" if h else f"{m}m"
            stats = f"{n} session{'s' if n != 1 else ''}  ·  {focused} focused"
        else:
            stats = "No sessions yet"
        c.itemconfig(self.sessions_text, text=stats)

        self._render_controls()
        self.root.title(f"{mins:02d}:{sec:02d} · {label}")

    # ---------- Timer logic ----------

    @property
    def running(self) -> bool:
        return self.end_time is not None

    def toggle(self):
        if self.running:
            self.remaining = max(0.0, self.end_time - time.monotonic())
            self.end_time = None
        else:
            self.end_time = time.monotonic() + self.remaining
        self._render()

    def reset(self):
        """Restarts the focus session. During a break, ends the break and starts over from focus."""
        if self.phase == "break":
            self.phase = "work"
            self.duration = WORK_MINUTES * 60
        self.end_time = None
        self.remaining = float(self.duration)
        self._render()

    def skip(self):
        self._switch_phase(completed=False)

    def _tick(self):
        if self.running:
            self.remaining = self.end_time - time.monotonic()
            if self.remaining <= 0:
                self._switch_phase(completed=True)
            else:
                self._render()
        self.root.after(TICK_MS, self._tick)

    def _switch_phase(self, completed: bool):
        if completed and self.phase == "work":
            self.sessions_done += 1

        self.phase = "break" if self.phase == "work" else "work"
        self.duration = (WORK_MINUTES if self.phase == "work" else BREAK_MINUTES) * 60
        self.remaining = float(self.duration)
        self.end_time = time.monotonic() + self.remaining if (completed and self.auto_start) else None

        if completed:
            self._notify()
        self._render()

    # ---------- Notifications ----------

    def _notify(self):
        if winsound:
            alias = "SystemExclamation" if self.phase == "break" else "SystemAsterisk"
            winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)

        self._send_toast()

        # Pop the window to the front so the user notices the phase change
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(1500, self._apply_topmost)
        self.root.focus_force()

    def _send_toast(self):
        if not Notification:
            return
        # Text is embedded in a PowerShell script by winotify: avoid $ and backticks
        if self.phase == "break":
            title = f"Break time · {BREAK_MINUTES} min"
            msg = f"Focus session {self.sessions_done} done. Step away from the screen and stretch."
        else:
            title = f"Back to focus · {WORK_MINUTES} min"
            msg = f"Break is over. Time for session {self.sessions_done + 1}."
        if not self.auto_start:
            msg += " Press Start when you are ready."
        try:
            toast = Notification(app_id=APP_ID, title=title, msg=msg, icon=self.toast_icon or "")
            toast.set_audio(audio.Silent, loop=False)  # winsound already plays the chime
            toast.show()
        except OSError:
            pass  # A failed toast must never stop the timer

    def _apply_topmost(self):
        self.root.attributes("-topmost", self.always_on_top)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp rendering on high-DPI screens
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Pomodoro.52-17")  # own taskbar icon
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    PomodoroApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
