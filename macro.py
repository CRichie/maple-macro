import ctypes
import secrets
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

user32 = ctypes.windll.user32
random = secrets.SystemRandom()
KEYUP = 0x0002
EXTENDED = 0x0001
EXTENDED_KEYS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}
KEYS = {"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "space": 0x20, "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
        "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E,
        "home": 0x24, "end": 0x23, "pageup": 0x21, "pgup": 0x21,
        "pagedown": 0x22, "pgdn": 0x22,
        **{chr(i): i for i in range(65, 91)},
        **{str(i): 0x30 + i for i in range(10)},
        **{f"f{i}": 0x6F + i for i in range(1, 13)}}


def key_code(name):
    name = name.strip().lower()
    if name in KEYS:
        return KEYS[name]
    if len(name) == 1 and name.upper() in KEYS:
        return KEYS[name.upper()]
    raise ValueError(f"不支持的按键：{name}")


class Macro:
    def __init__(self, root):
        self.root = root
        self.stop = threading.Event()
        self.worker = None
        self.closed = False
        self.vars = {}
        root.title("练级键盘宏")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=14)
        frame.grid(sticky="nsew")
        fields = [
            ("攻击键", "attack", "a"),
            ("随机附加按键（逗号分隔）", "random_keys", ""),
            ("放置技能 1", "skill1", "s"),
            ("放置技能 2", "skill2", "d"),
            ("补放周期下限（秒）", "interval_min", "110"),
            ("补放周期上限（秒）", "interval_max", "120"),
            ("普通动作间隔下限（秒）", "action_min", "0.25"),
            ("普通动作间隔上限（秒）", "action_max", "0.8"),
            ("传送后等待下限（秒）", "teleport_min", "1.2"),
            ("传送后等待上限（秒）", "teleport_max", "1.8"),
            ("按键持续下限（秒）", "press_min", "0.06"),
            ("按键持续上限（秒）", "press_max", "0.10"),
            ("技能后等待下限（秒）", "skill_wait_min", "0.4"),
            ("技能后等待上限（秒）", "skill_wait_max", "0.6"),
            ("巡回每点停留下限（秒）", "stay_min", "5"),
            ("巡回每点停留上限（秒）", "stay_max", "10"),
            ("四个位置对应技能", "skills", "1,2,2,2"),
        ]
        for row, (label, name, default) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
            self.vars[name] = tk.StringVar(value=default)
            ttk.Entry(frame, textvariable=self.vars[name], width=38).grid(row=row, column=1, pady=3, padx=(12, 0))
        row = len(fields)
        ttk.Label(frame, text="光圈之间固定通过按上键传送。", wraplength=420).grid(row=row, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Label(frame, text="F8 启动 / F9 停止；游戏需处于前台。", wraplength=420).grid(row=row+1, columnspan=2, sticky="w")
        ttk.Label(frame, text="提示音由游戏提供；遇到验证请按 F9 并手动处理。", wraplength=420).grid(row=row+2, columnspan=2, sticky="w")
        buttons = ttk.Frame(frame)
        buttons.grid(row=row+3, columnspan=2, pady=10)
        ttk.Button(buttons, text="启动 (F8)", command=self.start).pack(side="left", padx=4)
        ttk.Button(buttons, text="停止 (F9)", command=self.halt).pack(side="left", padx=4)
        self.status = tk.StringVar(value="已停止")
        ttk.Label(frame, textvariable=self.status).grid(row=row+4, columnspan=2)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.hotkeys = threading.Thread(target=self.hotkey_loop, daemon=True)
        self.hotkeys.start()

    def config(self):
        get = lambda n: self.vars[n].get().strip()
        cfg = {n: key_code(get(n)) for n in ("attack", "skill1", "skill2")}
        for n in ("interval_min", "interval_max", "action_min", "action_max", "teleport_min", "teleport_max", "press_min", "press_max", "skill_wait_min", "skill_wait_max", "stay_min", "stay_max"):
            cfg[n] = float(get(n))
            if not 0 < cfg[n] <= 3600:
                raise ValueError(f"{n} 必须大于 0 且不超过 3600")
        if cfg["interval_min"] > cfg["interval_max"] or cfg["action_min"] > cfg["action_max"] or cfg["stay_min"] > cfg["stay_max"] or cfg["teleport_min"] > cfg["teleport_max"] or cfg["press_min"] > cfg["press_max"] or cfg["skill_wait_min"] > cfg["skill_wait_max"]:
            raise ValueError("时间下限不能大于上限")
        extra_keys = [x.strip() for x in get("random_keys").split(",") if x.strip()]
        cfg["random_actions"] = [cfg["attack"], cfg["attack"]] + [key_code(x) for x in extra_keys]
        cfg["paths"] = [[KEYS["up"]] for _ in range(4)]
        cfg["skills"] = [x.strip() for x in get("skills").split(",")]
        if len(cfg["skills"]) != 4 or any(x not in ("1", "2") for x in cfg["skills"]):
            raise ValueError("位置技能必须是 4 个 1 或 2，例如 1,2,2,2")
        return cfg

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            cfg = self.config()
        except ValueError as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        self.stop.clear()
        self.status.set("运行中：请切换至游戏；按 F9 停止")
        self.worker = threading.Thread(target=self.run, args=(cfg,), daemon=True)
        self.worker.start()

    def halt(self):
        self.stop.set()
        self.status.set("已停止")

    def press(self, code, duration=0.08):
        if self.stop.is_set():
            return False
        flags = EXTENDED if code in EXTENDED_KEYS else 0
        user32.keybd_event(code, 0, flags, 0)
        try:
            self.stop.wait(duration)
        finally:
            user32.keybd_event(code, 0, flags | KEYUP, 0)
        return not self.stop.is_set()

    def run(self, cfg):
        # Give the user a chance to focus the game after clicking Start.
        if self.stop.wait(3):
            return
        deadline = time.monotonic()
        excursion_at = None
        while not self.stop.is_set():
            if time.monotonic() >= deadline:
                cycle_started = time.monotonic()
                for path, skill in zip(cfg["paths"], cfg["skills"]):
                    if not self.press(cfg["skill" + skill], random.uniform(cfg["press_min"], cfg["press_max"])) or self.stop.wait(random.uniform(cfg["skill_wait_min"], cfg["skill_wait_max"])):
                        return
                    for code in path:
                        if not self.press(code, random.uniform(cfg["press_min"], cfg["press_max"])) or self.stop.wait(random.uniform(cfg["teleport_min"], cfg["teleport_max"])):
                            return
                deadline = cycle_started + random.uniform(cfg["interval_min"], cfg["interval_max"])
                # Reserve the longest possible tour and a small scheduling margin.
                tour_budget = sum(len(path) for path in cfg["paths"]) * (cfg["press_max"] + cfg["teleport_max"]) + 3 * cfg["stay_max"] + 1
                earliest = time.monotonic()
                latest = deadline - tour_budget
                excursion_at = random.uniform(earliest, latest) if latest >= earliest else None
            elif excursion_at is not None and time.monotonic() >= excursion_at:
                excursion_at = None
                for index, path in enumerate(cfg["paths"]):
                    for code in path:
                        if not self.press(code, random.uniform(cfg["press_min"], cfg["press_max"])) or self.stop.wait(random.uniform(cfg["teleport_min"], cfg["teleport_max"])):
                            return
                    if index < 3 and self.stop.wait(random.uniform(cfg["stay_min"], cfg["stay_max"])):
                        return
            else:
                code = random.choice(cfg["random_actions"])
                if not self.press(code, random.uniform(cfg["press_min"], cfg["press_max"])):
                    return
                self.stop.wait(random.uniform(cfg["action_min"], cfg["action_max"]))

    def hotkey_loop(self):
        previous = {0x77: False, 0x78: False}
        while not self.closed:
            for code, action in ((0x77, self.start), (0x78, self.halt)):
                down = bool(user32.GetAsyncKeyState(code) & 0x8000)
                if down and not previous[code]:
                    try:
                        self.root.after(0, action)
                    except RuntimeError:
                        return
                previous[code] = down
            time.sleep(0.05)

    def close(self):
        self.stop.set()
        self.closed = True
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Macro(root)
    root.mainloop()
