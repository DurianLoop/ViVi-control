import random
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

from PIL import Image, ImageSequence, ImageTk


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WINDOW_KEY = "#fff4f8"
MAX_HEIGHT = 300
IDLE_STATES = ("idle", "relax", "sleep", "special_loop")


@dataclass
class PetFrame:
    image: Image.Image
    duration_ms: int
    width: int
    height: int


def find_asset_dir() -> Path:
    expected = {
        "sit.gif",
        "move.gif",
        "interact.gif",
        "jump.gif",
        "fly.gif",
        "special.gif",
        "special0.gif",
        "sleep.gif",
    }
    ranked: list[tuple[int, int, int, Path]] = []
    for folder in {path.parent for path in ROOT.rglob("*.gif")}:
        names = {path.name for path in folder.glob("*.gif")}
        score = len(expected & names)
        if not score:
            continue
        rel_parts = folder.relative_to(ROOT).parts
        hidden_penalty = 1 if any(part.startswith(".") for part in rel_parts) else 0
        archive_penalty = 1 if "archive" in {part.lower() for part in rel_parts} else 0
        ranked.append((score, -hidden_penalty, -archive_penalty, folder))

    if ranked:
        ranked.sort(key=lambda item: (item[0], item[1], item[2], -len(str(item[3]))), reverse=True)
        if ranked[0][0] >= 3:
            return ranked[0][3]

    messagebox.showerror(
        "Missing assets",
        "Could not find sit.gif, move.gif, and interact.gif under the current folder.",
    )
    sys.exit(1)


def strip_alpha_matte(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a <= 6:
                pixels[x, y] = (0, 0, 0, 0)
            elif a < 255:
                boost = 255 / a
                pixels[x, y] = (
                    min(255, int(r * boost)),
                    min(255, int(g * boost)),
                    min(255, int(b * boost)),
                    a,
                )
    return rgba


def resize_clean(image: Image.Image, ratio: float) -> Image.Image:
    if ratio >= 0.999:
        return image
    resized = image.resize(
        (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
        Image.Resampling.LANCZOS,
    )
    alpha = resized.getchannel("A")
    alpha = alpha.point(lambda value: 0 if value < 72 else 255)
    resized.putalpha(alpha)
    return resized


def normalize_frame(frame: Image.Image) -> Image.Image:
    rgba = strip_alpha_matte(frame)
    bbox = rgba.getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    if rgba.height > MAX_HEIGHT:
        rgba = resize_clean(rgba, MAX_HEIGHT / rgba.height)
    canvas = Image.new("RGBA", (rgba.width + 4, rgba.height + 4), (0, 0, 0, 0))
    canvas.alpha_composite(rgba, (2, 2))
    return canvas


def load_gif(path: Path, flip: bool = False) -> list[PetFrame]:
    frames: list[PetFrame] = []
    with Image.open(path) as gif:
        for raw in ImageSequence.Iterator(gif):
            image = normalize_frame(raw)
            if flip:
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            duration = max(45, int(raw.info.get("duration", gif.info.get("duration", 90)) or 90))
            frames.append(PetFrame(image, duration, image.width, image.height))
    if not frames:
        raise ValueError(f"No frames loaded from {path}")
    max_width = max(frame.width for frame in frames)
    max_height = max(frame.height for frame in frames)
    padded = []
    for frame in frames:
        canvas = Image.new("RGBA", (max_width, max_height), (0, 0, 0, 0))
        canvas.alpha_composite(frame.image, ((max_width - frame.width) // 2, max_height - frame.height))
        padded.append(PetFrame(canvas, frame.duration_ms, max_width, max_height))
    return padded


def load_animations() -> dict[str, list[PetFrame]]:
    asset_dir = find_asset_dir()
    file_map = {
        "start": "start.gif",
        "idle": "sit.gif",
        "relax": "relax.gif",
        "sleep": "sleep.gif",
        "walk_right": "move.gif",
        "walk_left": "move.gif",
        "jump": "jump.gif",
        "fly": "fly.gif",
        "hide": "hide.gif",
        "interact": "interact.gif",
        "special": "special.gif",
        "special_long": "special0.gif",
        "special_loop": "special1.gif",
        "sweat": "sweat.gif",
        "die": "die.gif",
    }

    animations: dict[str, list[PetFrame]] = {}
    for state, filename in file_map.items():
        path = asset_dir / filename
        if path.exists():
            animations[state] = load_gif(path, flip=(state == "walk_left"))

    if "idle" not in animations or "walk_right" not in animations:
        messagebox.showerror("Missing assets", "Required GIFs are missing: sit.gif and move.gif.")
        sys.exit(1)
    return pad_animations_to_stage(animations)


def pad_animations_to_stage(animations: dict[str, list[PetFrame]]) -> dict[str, list[PetFrame]]:
    stage_width = max(frame.width for frames in animations.values() for frame in frames)
    stage_height = max(frame.height for frames in animations.values() for frame in frames)
    staged: dict[str, list[PetFrame]] = {}
    for name, frames in animations.items():
        staged_frames = []
        for frame in frames:
            canvas = Image.new("RGBA", (stage_width, stage_height), (0, 0, 0, 0))
            canvas.alpha_composite(frame.image, ((stage_width - frame.width) // 2, stage_height - frame.height))
            staged_frames.append(PetFrame(canvas, frame.duration_ms, stage_width, stage_height))
        staged[name] = staged_frames
    return staged


class DesktopPet:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=WINDOW_KEY, bd=0, highlightthickness=0)
        self.root.wm_attributes("-transparentcolor", WINDOW_KEY)

        self.animations = load_animations()
        self.display_scale = tk.DoubleVar(value=1.0)
        self.photo_cache: dict[tuple[int, str], list[ImageTk.PhotoImage]] = {}

        self.state = "start" if "start" in self.animations else "idle"
        self.frame_index = 0
        self.dx = 0
        self.dy = 0
        self.drag_start: tuple[int, int] | None = None
        self.drag_origin: tuple[int, int] | None = None
        self.drag_action = "fly" if "fly" in self.animations else "interact"
        self.drag_mode = tk.StringVar(value="fly")
        self.locked_until = time.monotonic() + 1.1
        self.one_shot = self.state == "start"
        self.ground_y: int | None = None
        self.edge_hide = tk.BooleanVar(value=False)
        self.hidden_edge: str | None = None
        self.tail_visible = 44
        self.last_pointer_reaction = 0.0
        self.last_click_at = 0.0
        self.clicks = 0
        self.auto_mode = tk.BooleanVar(value=True)
        self.follow_mouse = tk.BooleanVar(value=True)
        self.key_panel = tk.StringVar(value="F8")
        self.key_interact = tk.StringVar(value="F9")
        self.key_hide = tk.StringVar(value="F10")
        self.hotkey_bindings: list[str] = []
        self.status = tk.StringVar(value="Starting")
        self.window_pos = (0, 0)

        self.label = tk.Label(self.root, bg=WINDOW_KEY, bd=0, highlightthickness=0, padx=0, pady=0)
        self.label.pack()
        self.label.bind("<ButtonPress-1>", self.start_drag)
        self.label.bind("<ButtonRelease-1>", self.stop_drag)
        self.label.bind("<B1-Motion>", self.drag)
        self.label.bind("<Double-Button-1>", self.react)
        self.label.bind("<Enter>", self.pointer_enter)
        self.label.bind("<Leave>", self.pointer_leave)
        self.label.bind("<Button-3>", self.show_menu)

        self.menu = tk.Menu(self.root, tearoff=0)
        for label, state in [
            ("Pat", "interact"),
            ("Jump", "jump"),
            ("Fly", "fly"),
            ("Hide", "hide"),
            ("Special", "special"),
            ("Long Special", "special_long"),
            ("Faint", "die"),
        ]:
            self.menu.add_command(label=label, command=lambda value=state: self.play_once(value))
        self.menu.add_separator()
        self.menu.add_command(label="Show Panel", command=self.show_panel)
        self.menu.add_command(label="Quit", command=self.root.destroy)

        self.panel = ControlPanel(self)
        self.apply_hotkeys()
        self.place_initially()
        self.tick()

    def place_initially(self) -> None:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width, height = self.scaled_size(self.animations[self.state][0])
        x = max(0, screen_w - width - 24)
        y = max(0, screen_h - height - 56)
        self.window_pos = (x, y)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def show_panel(self) -> None:
        self.panel.show()

    def current_scale_percent(self) -> int:
        return max(55, min(145, int(float(self.display_scale.get()) * 100)))

    def get_photos(self, state: str) -> list[ImageTk.PhotoImage]:
        scale_percent = self.current_scale_percent()
        key = (scale_percent, state)
        if key in self.photo_cache:
            return self.photo_cache[key]

        scale = scale_percent / 100
        images = []
        for frame in self.animations[state]:
            if scale_percent == 100:
                image = frame.image
            else:
                image = frame.image.resize(
                    (max(1, int(frame.width * scale)), max(1, int(frame.height * scale))),
                    Image.Resampling.LANCZOS,
                )
                alpha = image.getchannel("A").point(lambda value: 0 if value < 72 else 255)
                image.putalpha(alpha)
            images.append(ImageTk.PhotoImage(image))
        self.photo_cache[key] = images
        return images

    def rebuild_photos(self) -> None:
        scale = max(0.55, min(1.45, float(self.display_scale.get())))
        self.photo_cache.clear()
        self.get_photos(self.state)
        self.status.set(f"Size {int(scale * 100)}%")

    def scaled_size(self, frame: PetFrame) -> tuple[int, int]:
        scale = max(0.55, min(1.45, float(self.display_scale.get())))
        return max(1, int(frame.width * scale)), max(1, int(frame.height * scale))

    def apply_hotkeys(self) -> None:
        for sequence in self.hotkey_bindings:
            self.root.unbind_all(sequence)
        self.hotkey_bindings = []
        bindings = [
            (self.key_panel.get().strip(), lambda _event: self.show_panel()),
            (self.key_interact.get().strip(), lambda _event: self.react()),
            (self.key_hide.get().strip(), lambda _event: self.hide_to_nearest_edge()),
        ]
        for key, callback in bindings:
            if not key:
                continue
            sequence = f"<{key}>"
            try:
                self.root.bind_all(sequence, callback)
                self.hotkey_bindings.append(sequence)
            except tk.TclError:
                self.status.set(f"Bad hotkey: {key}")

    def start_drag(self, event: tk.Event) -> None:
        if self.hidden_edge:
            self.wake_from_edge()
            return
        now = time.monotonic()
        self.clicks = self.clicks + 1 if now - self.last_click_at < 0.7 else 1
        self.last_click_at = now
        x, y = self.window_pos
        self.drag_start = (event.x_root - x, event.y_root - y)
        self.drag_origin = (event.x_root, event.y_root)
        mode = self.drag_mode.get()
        if mode == "Random":
            self.drag_action = random.choice([state for state in ("fly", "interact", "sweat") if state in self.animations])
        else:
            self.drag_action = mode if mode in self.animations else "interact"
        self.status.set("Picked up")
        if self.clicks >= 4:
            self.play_once(random.choice([state for state in ("sweat", "die") if state in self.animations]))
            self.clicks = 0
        else:
            self.set_loop(self.drag_action, hold=random.uniform(1.0, 2.0))

    def stop_drag(self, event: tk.Event) -> None:
        distance = 0
        if self.drag_origin:
            distance = abs(event.x_root - self.drag_origin[0]) + abs(event.y_root - self.drag_origin[1])
        self.drag_start = None
        self.drag_origin = None
        self.ground_y = None
        x, _ = self.window_pos
        width, _ = self.scaled_size(self.animations[self.state][0])
        screen_w = self.root.winfo_screenwidth()
        if self.edge_hide.get() and (x <= 2 or x + width >= screen_w - 2):
            self.hide_to_nearest_edge()
        elif distance > 420:
            self.play_once(random.choice([state for state in ("fly", "special", "sweat") if state in self.animations]))
        elif distance > 160:
            self.play_once(random.choice([state for state in ("jump", "sweat", "interact") if state in self.animations]))
        else:
            self.play_once("interact", seconds=0.9)

    def drag(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        off_x, off_y = self.drag_start
        x, y = event.x_root - off_x, event.y_root - off_y
        self.window_pos = (x, y)
        self.root.geometry(f"+{x}+{y}")
        if self.state != self.drag_action:
            self.set_loop(self.drag_action, hold=1.2)
        self.locked_until = time.monotonic() + 1.2

    def pointer_enter(self, _event: tk.Event) -> None:
        if self.hidden_edge:
            self.wake_from_edge()
            return
        now = time.monotonic()
        if now - self.last_pointer_reaction > 2.2 and not self.one_shot and self.drag_start is None:
            self.last_pointer_reaction = now
            self.play_once(random.choice([state for state in ("interact", "sweat") if state in self.animations]), seconds=1.0)

    def pointer_leave(self, _event: tk.Event) -> None:
        if not self.one_shot and self.drag_start is None and random.random() < 0.35:
            self.set_loop(random.choice(["walk_left", "walk_right"]))

    def show_menu(self, event: tk.Event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)

    def react(self, _event: tk.Event | None = None) -> None:
        if self.hidden_edge:
            self.wake_from_edge()
            return
        self.play_once(random.choice([state for state in ("interact", "jump", "special", "sweat", "fly") if state in self.animations]))

    def play_once(self, state: str, seconds: float | None = None) -> None:
        if state not in self.animations:
            return
        self.state = state
        self.frame_index = 0
        self.dx = 0
        self.dy = -8 if state in {"jump", "fly"} else 0
        self.hidden_edge = None
        self.ground_y = self.window_pos[1] if state == "jump" else None
        self.one_shot = True
        if seconds is None:
            seconds = sum(frame.duration_ms for frame in self.animations[state]) / 1000
        self.locked_until = time.monotonic() + seconds
        self.status.set(state.replace("_", " ").title())

    def set_loop(self, state: str, hold: float | None = None) -> None:
        if state not in self.animations:
            state = "idle"
        self.state = state
        self.frame_index = 0
        self.one_shot = False
        self.dx = -4 if state == "walk_left" else 4 if state == "walk_right" else 0
        self.dy = 0
        self.hidden_edge = None
        self.ground_y = None
        self.locked_until = time.monotonic() + (hold if hold is not None else random.uniform(3.0, 7.8))
        self.status.set(state.replace("_", " ").title())

    def choose_next_state(self) -> None:
        if self.hidden_edge:
            return
        if not self.auto_mode.get():
            self.set_loop(random.choice([state for state in IDLE_STATES if state in self.animations]), hold=3.0)
            return

        pointer_x = self.root.winfo_pointerx()
        pointer_y = self.root.winfo_pointery()
        x, y = self.window_pos
        width, height = self.scaled_size(self.animations[self.state][self.frame_index])
        pet_center_x = x + width // 2
        pet_center_y = y + height // 2
        pointer_distance = abs(pointer_x - pet_center_x) + abs(pointer_y - pet_center_y)

        if pointer_distance < 260 and random.random() < 0.16:
            self.play_once(random.choice([state for state in ("interact", "sweat") if state in self.animations]))
            return
        if self.follow_mouse.get() and pointer_distance > 360 and random.random() < 0.18:
            self.set_loop("walk_right" if pointer_x > pet_center_x else "walk_left")
            return

        options = [
            "idle",
            "relax",
            "sleep",
            "special_loop",
            "walk_left",
            "walk_right",
            "interact",
            "jump",
            "fly",
            "sweat",
        ]
        weights = [16, 24, 10, 10, 18, 18, 4, 2, 1, 1]
        available = [(state, weight) for state, weight in zip(options, weights) if state in self.animations]
        choice = random.choices([state for state, _ in available], [weight for _, weight in available], k=1)[0]
        if choice in IDLE_STATES or choice.startswith("walk_"):
            self.set_loop(choice)
        else:
            self.play_once(choice)

    def hide_to_nearest_edge(self) -> None:
        if "hide" in self.animations:
            self.set_loop("hide", hold=8.0)
        self.dx = 0
        width, _ = self.scaled_size(self.animations[self.state][self.frame_index])
        x, _ = self.window_pos
        screen_w = self.root.winfo_screenwidth()
        if x + width // 2 < screen_w // 2:
            self.hidden_edge = "left"
        else:
            self.hidden_edge = "right"
        self.position_hidden_edge()
        self.status.set("Hiding")

    def position_hidden_edge(self) -> None:
        if not self.hidden_edge:
            return
        width, height = self.scaled_size(self.animations[self.state][self.frame_index])
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        _, current_y = self.window_pos
        y = max(0, min(current_y, screen_h - height))
        if self.hidden_edge == "left":
            x = -max(0, width - self.tail_visible)
        else:
            x = screen_w - self.tail_visible
        self.window_pos = (x, y)
        self.root.geometry(f"+{x}+{y}")

    def wake_from_edge(self) -> None:
        edge = self.hidden_edge
        if not edge:
            return
        self.hidden_edge = None
        screen_w = self.root.winfo_screenwidth()
        width, height = self.scaled_size(self.animations[self.state][self.frame_index])
        _, current_y = self.window_pos
        y = max(0, min(current_y, self.root.winfo_screenheight() - height))
        x = 8 if edge == "left" else max(0, screen_w - width - 8)
        self.window_pos = (x, y)
        self.root.geometry(f"+{x}+{y}")
        self.play_once("sweat" if "sweat" in self.animations else "interact")

    def walk_out_from_edge(self) -> None:
        edge = self.hidden_edge
        if not edge:
            return
        self.hidden_edge = None
        screen_w = self.root.winfo_screenwidth()
        width, height = self.scaled_size(self.animations[self.state][self.frame_index])
        _, current_y = self.window_pos
        y = max(0, min(current_y, self.root.winfo_screenheight() - height))
        if edge == "left":
            self.window_pos = (4, y)
            self.root.geometry(f"+4+{y}")
            self.set_loop("walk_right", hold=random.uniform(2.2, 4.2))
        else:
            x = max(0, screen_w - width - 4)
            self.window_pos = (x, y)
            self.root.geometry(f"+{x}+{y}")
            self.set_loop("walk_left", hold=random.uniform(2.2, 4.2))
        self.status.set("Peeking out")

    def move_window(self) -> None:
        if self.drag_start is not None or self.hidden_edge:
            return
        x, y = self.window_pos
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width, height = self.scaled_size(self.animations[self.state][self.frame_index])

        if self.ground_y is not None:
            y += self.dy
            self.dy += 1
            if y >= self.ground_y:
                y = self.ground_y
                self.dy = 0
        x = max(0, min(x + self.dx, screen_w - width))
        y = max(0, min(y, screen_h - height))
        if x in (0, max(0, screen_w - width)) and self.dx:
            if self.edge_hide.get():
                self.hide_to_nearest_edge()
                return
            self.set_loop("walk_right" if self.dx < 0 else "walk_left")
        self.window_pos = (x, y)
        self.root.geometry(f"+{x}+{y}")

    def keep_visible(self) -> None:
        if self.hidden_edge:
            return
        self.root.update_idletasks()
        x, y = self.window_pos
        width, height = self.scaled_size(self.animations[self.state][self.frame_index])
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        safe_x = max(0, min(x, max(0, screen_w - width)))
        safe_y = max(0, min(y, max(0, screen_h - height)))
        if safe_x != x or safe_y != y:
            self.window_pos = (safe_x, safe_y)
            self.root.geometry(f"+{safe_x}+{safe_y}")

    def tick(self) -> None:
        frames = self.animations[self.state]
        photos = self.get_photos(self.state)
        frame = frames[self.frame_index]
        self.label.configure(image=photos[self.frame_index])
        self.label.image = photos[self.frame_index]
        width, height = self.scaled_size(frame)
        x, y = self.window_pos
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        if self.hidden_edge:
            self.position_hidden_edge()
        else:
            self.move_window()
            self.keep_visible()

        self.frame_index += 1
        if self.frame_index >= len(frames):
            self.frame_index = 0
            if self.one_shot and time.monotonic() >= self.locked_until:
                self.set_loop(random.choice([state for state in IDLE_STATES if state in self.animations]))

        if not self.one_shot and time.monotonic() >= self.locked_until:
            if self.hidden_edge and random.random() < 0.28:
                self.walk_out_from_edge()
            else:
                self.choose_next_state()

        self.root.after(frame.duration_ms, self.tick)

    def run(self) -> None:
        self.root.mainloop()


class ControlPanel:
    def __init__(self, pet: DesktopPet) -> None:
        self.pet = pet
        self.size_after_id: str | None = None
        self.window = tk.Toplevel(pet.root)
        self.window.title("Vivi Control")
        self.window.geometry("+40+80")
        self.window.configure(bg="#fff7fb")
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        self.window.resizable(False, False)

        shell = tk.Frame(self.window, bg="#fff7fb", padx=14, pady=12)
        shell.pack(fill="both", expand=True)

        tk.Label(
            shell,
            text="Vivi Control",
            bg="#fff7fb",
            fg="#9b385f",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="soft desk pet settings",
            bg="#fff7fb",
            fg="#b36b86",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 8))

        status_card = tk.Frame(shell, bg="#ffe4ef", padx=10, pady=6)
        status_card.pack(fill="x", pady=(0, 10))
        tk.Label(
            status_card,
            textvariable=pet.status,
            bg="#ffe4ef",
            fg="#6c2f48",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            status_card,
            text="F8 panel  F9 pat  F10 edge",
            bg="#ffe4ef",
            fg="#8b6474",
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        actions = tk.Frame(shell, bg="#fff7fb")
        actions.pack(fill="x")
        for index, (label, state) in enumerate(
            [
                ("Pat", "interact"),
                ("Jump", "jump"),
                ("Fly", "fly"),
                ("Hide", "hide"),
                ("Special", "special"),
                ("Nap", "sleep"),
                ("Edge Hide", "edge_hide"),
            ]
        ):
            button = tk.Button(
                actions,
                text=label,
                command=lambda value=state: self.run_action(value),
                bg="#ffd6e5",
                activebackground="#ffc1d8",
                fg="#5c2e42",
                bd=0,
                relief="flat",
                padx=10,
                pady=6,
                font=("Segoe UI", 9, "bold"),
            )
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=3, pady=3)
        for column in range(3):
            actions.columnconfigure(column, weight=1)

        toggles = tk.Frame(shell, bg="#fff7fb")
        toggles.pack(fill="x", pady=(10, 6))
        tk.Checkbutton(
            toggles,
            text="Auto mood",
            variable=pet.auto_mode,
            bg="#fff7fb",
            activebackground="#fff7fb",
            fg="#5c2e42",
            selectcolor="#ffe4ef",
        ).pack(anchor="w")
        tk.Checkbutton(
            toggles,
            text="Follow pointer",
            variable=pet.follow_mouse,
            bg="#fff7fb",
            activebackground="#fff7fb",
            fg="#5c2e42",
            selectcolor="#ffe4ef",
        ).pack(anchor="w")
        tk.Checkbutton(
            toggles,
            text="Edge peek",
            variable=pet.edge_hide,
            bg="#fff7fb",
            activebackground="#fff7fb",
            fg="#5c2e42",
            selectcolor="#ffe4ef",
        ).pack(anchor="w")

        size_box = tk.Frame(shell, bg="#fff7fb")
        size_box.pack(fill="x", pady=(8, 4))
        tk.Label(size_box, text="Size", bg="#fff7fb", fg="#6c4b5b").pack(anchor="w")
        tk.Scale(
            size_box,
            from_=55,
            to=145,
            orient="horizontal",
            showvalue=True,
            bg="#fff7fb",
            fg="#6c4b5b",
            troughcolor="#ffe4ef",
            highlightthickness=0,
            command=self.change_size,
        ).pack(fill="x")
        size_box.winfo_children()[1].set(int(pet.display_scale.get() * 100))

        drag_box = tk.Frame(shell, bg="#fff7fb")
        drag_box.pack(fill="x", pady=(6, 4))
        tk.Label(drag_box, text="Drag animation", bg="#fff7fb", fg="#6c4b5b").pack(anchor="w")
        choices = ["Random"] + [state for state in ("fly", "interact", "sweat", "jump") if state in pet.animations]
        tk.OptionMenu(drag_box, pet.drag_mode, *choices).pack(fill="x")

        hotkeys = tk.Frame(shell, bg="#fff7fb")
        hotkeys.pack(fill="x", pady=(8, 4))
        tk.Label(hotkeys, text="Hotkeys", bg="#fff7fb", fg="#6c4b5b").grid(row=0, column=0, columnspan=3, sticky="w")
        self.hotkey_entry(hotkeys, "Panel", pet.key_panel, 1, 0)
        self.hotkey_entry(hotkeys, "Pat", pet.key_interact, 1, 1)
        self.hotkey_entry(hotkeys, "Hide", pet.key_hide, 1, 2)
        tk.Button(
            hotkeys,
            text="Apply",
            command=pet.apply_hotkeys,
            bg="#e8ddff",
            activebackground="#dac9ff",
            fg="#4b3d73",
            bd=0,
            padx=8,
            pady=4,
        ).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        for column in range(3):
            hotkeys.columnconfigure(column, weight=1)

        footer = tk.Frame(shell, bg="#fff7fb")
        footer.pack(fill="x", pady=(8, 0))
        tk.Button(
            footer,
            text="Bring Here",
            command=self.bring_pet_near_panel,
            bg="#e8ddff",
            activebackground="#dac9ff",
            fg="#4b3d73",
            bd=0,
            padx=10,
            pady=6,
        ).pack(side="left")
        tk.Button(
            footer,
            text="Quit",
            command=pet.root.destroy,
            bg="#f3f0f2",
            activebackground="#e8e1e5",
            fg="#6c4b5b",
            bd=0,
            padx=10,
            pady=6,
        ).pack(side="right")

    def run_action(self, value: str) -> None:
        if value == "edge_hide":
            self.pet.hide_to_nearest_edge()
        elif value in IDLE_STATES:
            self.pet.set_loop(value)
        else:
            self.pet.play_once(value)

    def change_size(self, value: str) -> None:
        self.pet.display_scale.set(int(value) / 100)
        self.pet.status.set(f"Size {int(value)}%")
        if self.size_after_id is not None:
            self.window.after_cancel(self.size_after_id)
        self.size_after_id = self.window.after(160, self.apply_size)

    def apply_size(self) -> None:
        self.size_after_id = None
        self.pet.rebuild_photos()

    def hotkey_entry(self, parent: tk.Frame, label: str, variable: tk.StringVar, row: int, column: int) -> None:
        cell = tk.Frame(parent, bg="#fff7fb")
        cell.grid(row=row, column=column, sticky="ew", padx=2)
        tk.Label(cell, text=label, bg="#fff7fb", fg="#8b6474", font=("Segoe UI", 8)).pack(anchor="w")
        tk.Entry(
            cell,
            textvariable=variable,
            width=7,
            bg="#fffafd",
            fg="#5c2e42",
            relief="flat",
            justify="center",
        ).pack(fill="x", ipady=3)

    def bring_pet_near_panel(self) -> None:
        self.window.update_idletasks()
        x = self.window.winfo_x() + self.window.winfo_width() + 16
        y = self.window.winfo_y() + 24
        self.pet.window_pos = (x, y)
        self.pet.root.geometry(f"+{x}+{y}")
        self.pet.play_once("interact", seconds=1.0)

    def hide(self) -> None:
        self.window.withdraw()

    def show(self) -> None:
        self.window.deiconify()
        self.window.lift()


if __name__ == "__main__":
    DesktopPet().run()
