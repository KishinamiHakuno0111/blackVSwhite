"""Tk desktop UI. Rules and AI are deliberately independent of widgets."""

import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .ai import LEVELS, WIN
from .engine import BLACK, WHITE, EMPTY, SIZE, CELLS, Game, coordinate, flipped_bits, squares
from .worker import SearchWorker

COLORS = {
    "background": "#F3F1EA", "surface": "#FCFBF7", "ink": "#203C32",
    "muted": "#56685F", "border": "#CED4C9", "accent": "#245D48",
    "accent_hover": "#194C39", "board": "#205747", "board_alt": "#245D4D",
    "grid": "#3D7460", "gold": "#F0D48D", "black": "#15221D",
    "white": "#F8F5E9", "error": "#9D3E2D",
}
FONT = "Microsoft YaHei UI"
NAMES = {BLACK: "黑棋", WHITE: "白棋"}
MODES = ("人机对战", "双人对战", "AI 演示")


class BoardCanvas(tk.Canvas):
    def __init__(self, master, on_move, on_hover, **kwargs):
        super().__init__(master, background=COLORS["background"], highlightthickness=2,
                         highlightbackground=COLORS["background"], highlightcolor=COLORS["accent"],
                         takefocus=True, **kwargs)
        self.on_move, self.on_hover = on_move, on_hover
        self.position = None
        self.enabled = True
        self.show_legal = True
        self.last_move = self.hint = self.hover = None
        self.keyboard_square = (SIZE // 2 - 1) * SIZE + SIZE // 2 - 1
        self.keyboard_visible = False
        self.origin = (0.0, 0.0)
        self.cell = 1.0
        self.bind("<Configure>", lambda event: self.draw())
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)
        self.bind("<FocusIn>", self._focus)
        self.bind("<FocusOut>", lambda event: self.draw())
        for key in ("Left", "Right", "Up", "Down", "Return", "space"):
            self.bind(f"<{key}>", self._key)

    def set_state(self, position, enabled, last_move=None, hint=None, show_legal=True):
        self.position, self.enabled = position, enabled
        self.last_move, self.hint, self.show_legal = last_move, hint, show_legal
        self.draw()

    def center(self, move):
        x, y = self.origin
        return x + (move % SIZE + 0.5) * self.cell, y + (move // SIZE + 0.5) * self.cell

    def square_at(self, x, y):
        left, top = self.origin
        if not left <= x < left + SIZE * self.cell or not top <= y < top + SIZE * self.cell:
            return None
        return int((y - top) // self.cell) * SIZE + int((x - left) // self.cell)

    def _click(self, event):
        self.focus_set()
        move = self.square_at(event.x, event.y)
        if move is not None:
            self.keyboard_square = move
            self.keyboard_visible = False
            if self.enabled:
                self.on_move(move)
        self.draw()

    def _motion(self, event):
        move = self.square_at(event.x, event.y)
        if move != self.hover:
            self.hover = move
            legal = self.position is not None and move is not None and self.position.legal() & (1 << move)
            self.configure(cursor="hand2" if self.enabled and legal else "arrow")
            self.on_hover(move)
            self.draw()

    def _leave(self, event):
        self.hover = None
        self.on_hover(None)
        self.draw()

    def _focus(self, event):
        self.keyboard_visible = True
        self.draw()

    def _key(self, event):
        row, col = divmod(self.keyboard_square, SIZE)
        if event.keysym == "Left":
            col = max(0, col - 1)
        elif event.keysym == "Right":
            col = min(SIZE - 1, col + 1)
        elif event.keysym == "Up":
            row = max(0, row - 1)
        elif event.keysym == "Down":
            row = min(SIZE - 1, row + 1)
        elif self.enabled:
            self.on_move(self.keyboard_square)
        self.keyboard_square = row * SIZE + col
        self.keyboard_visible = True
        self.on_hover(self.keyboard_square)
        self.draw()
        return "break"

    def draw(self):
        self.delete("all")
        if self.position is None:
            return
        width, height = self.winfo_width(), self.winfo_height()
        size = max(100, min(width - 62, height - 56))
        self.cell = size / SIZE
        self.origin = ((width - size) / 2, (height - size) / 2 + 2)
        left, top = self.origin
        legal = self.position.legal()
        self.create_rectangle(left - 5, top - 5, left + size + 5, top + size + 5,
                              fill=COLORS["ink"], outline="")
        for i in range(SIZE):
            self.create_text(left + (i + .5) * self.cell, top - 21, text=chr(65 + i),
                             font=(FONT, 10), fill=COLORS["muted"])
            self.create_text(left - 22, top + (i + .5) * self.cell, text=str(i + 1),
                             font=(FONT, 10), fill=COLORS["muted"])
        radius = self.cell * .375
        for move in range(CELLS):
            row, col = divmod(move, SIZE)
            x, y = self.center(move)
            half = self.cell / 2
            self.create_rectangle(x - half, y - half, x + half, y + half,
                                  fill=COLORS["board" if (row + col) % 2 == 0 else "board_alt"],
                                  outline=COLORS["grid"], width=1)
            color = self.position.at(move)
            if color != EMPTY:
                self.create_oval(x - radius + 1, y - radius + 3, x + radius + 1, y + radius + 3,
                                 fill="#174335", outline="")
                self.create_oval(x - radius, y - radius, x + radius, y + radius,
                                 fill=COLORS["black" if color == BLACK else "white"],
                                 outline="#0C1914" if color == BLACK else "#D3D6C9", width=1.3)
                inset = max(2, self.cell * .045)
                self.create_arc(x - radius + inset, y - radius + inset, x + radius - inset,
                                y + radius - inset, start=40, extent=105, style="arc",
                                outline="#3D4B43" if color == BLACK else "#FFFFFF", width=1)
                if move == self.last_move:
                    marker = max(2.5, self.cell * .055)
                    self.create_oval(x - marker, y - marker, x + marker, y + marker,
                                     fill=COLORS["gold"] if color == BLACK else COLORS["accent"], outline="")
            elif legal & (1 << move):
                if move == self.hover and self.enabled:
                    self.create_oval(x - radius, y - radius, x + radius, y + radius,
                                     fill="#679A82", outline=COLORS["gold"], width=2)
                elif self.show_legal:
                    dot = max(3.5, self.cell * .078)
                    self.create_oval(x - dot, y - dot, x + dot, y + dot,
                                     outline="#C3D8B1", width=1.6)
            if move == self.hint:
                self.create_oval(x - radius, y - radius, x + radius, y + radius,
                                 outline=COLORS["gold"], width=3)
                self.create_text(x, y, text="建议", fill=COLORS["gold"], font=(FONT, 10, "bold"))
            if move == self.keyboard_square and self.keyboard_visible and self.focus_get() == self:
                self.create_rectangle(x - half + 3, y - half + 3, x + half - 3, y + half - 3,
                                      outline=COLORS["gold"], width=2, dash=(4, 2))


class ChessApp:
    def __init__(self, root: tk.Tk, worker=None):
        self.root = root
        self.root.title("黑白棋 · 8×8")
        self.root.geometry("1180x850")
        self.root.minsize(1000, 780)
        self.root.configure(background=COLORS["background"])
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.worker = worker if worker is not None else SearchWorker()
        self.game = Game()
        self.mode, self.human_color, self.level = MODES[0], BLACK, "深入"
        self.paused = self.busy = self.ai_failed = self.closed = False
        self.search_kind = None
        self.search_position = None
        self.dead_worker_seen = False
        self.poll_id = self.next_ai_id = None
        self.hint_move = None
        self.mode_var = tk.StringVar(value=self.mode)
        self.color_var = tk.StringVar(value="黑棋 · 先手")
        self.level_var = tk.StringVar(value=self.level)
        self.status_var = tk.StringVar()
        self.detail_var = tk.StringVar()
        self.hover_var = tk.StringVar(value="小圆圈：可落点     棋子内圆点：上一步")
        self.stats_var = tk.StringVar(value="等待对局\nAI 将在自己的回合自动落子。")
        self.show_legal_var = tk.BooleanVar(value=True)
        self._style()
        self._build()
        self.root.bind("<Control-n>", lambda event: self.new_game())
        self.root.bind("<Control-z>", lambda event: self.undo())
        self.root.bind("<Control-s>", lambda event: self.save_game())
        self.root.bind("<Control-o>", lambda event: self.load_game())
        self.root.bind("<F1>", lambda event: self.show_rules())
        self._render()

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["background"])
        style.configure("TButton", font=(FONT, 10), padding=(10, 8), background=COLORS["surface"],
                        foreground=COLORS["ink"], bordercolor=COLORS["border"], focuscolor=COLORS["accent"])
        style.map("TButton", background=[("active", "#E4E9DD"), ("disabled", "#EBEDE5")],
                  foreground=[("disabled", "#78857C")])
        style.configure("Compact.TButton", padding=(8, 4))
        style.configure("Accent.TButton", background=COLORS["accent"], foreground="#FFFFFF", borderwidth=0)
        style.map("Accent.TButton", background=[("active", COLORS["accent_hover"])],
                  foreground=[("active", "#FFFFFF")])
        style.configure("TCombobox", padding=5, font=(FONT, 10), foreground=COLORS["ink"],
                        fieldbackground=COLORS["surface"], background=COLORS["surface"])
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["surface"])],
                  foreground=[("readonly", COLORS["ink"])])
        style.configure("TCheckbutton", background=COLORS["background"], foreground=COLORS["muted"],
                        font=(FONT, 10))
        style.configure("Search.Horizontal.TProgressbar", background=COLORS["accent"],
                        troughcolor=COLORS["border"], borderwidth=0, thickness=3)
        self.root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    def _label(self, parent, text="", **kwargs):
        options = dict(background=COLORS["background"], foreground=COLORS["ink"],
                       font=(FONT, 10), anchor="w", justify="left")
        options.update(kwargs)
        return tk.Label(parent, text=text, **options)

    def _build(self):
        outer = ttk.Frame(self.root, padding=(26, 18, 26, 18))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 18))
        identity = ttk.Frame(header)
        identity.pack(side="left")
        self._label(identity, "黑白棋", font=(FONT, 26, "bold")).pack(anchor="w")
        self._label(identity, "8 × 8   /   每一步，改变局面", foreground=COLORS["muted"]).pack(anchor="w", pady=(3, 0))
        for title, command in reversed((("保存对局", self.save_game), ("载入对局", self.load_game), ("规则", self.show_rules))):
            ttk.Button(header, text=title, command=command).pack(side="right", padx=(8, 0))

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=292)
        body.rowconfigure(0, weight=1)
        play_area = ttk.Frame(body)
        play_area.grid(row=0, column=0, sticky="nsew", padx=(0, 26))
        play_area.rowconfigure(1, weight=1)
        play_area.columnconfigure(0, weight=1)
        scores = ttk.Frame(play_area)
        scores.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        scores.columnconfigure((0, 1), weight=1, uniform="score")
        self.score_labels, self.player_labels = {}, {}
        for color in (BLACK, WHITE):
            bg = COLORS["ink"] if color == BLACK else COLORS["surface"]
            fg = COLORS["white"] if color == BLACK else COLORS["ink"]
            card = tk.Frame(scores, background=bg, padx=18, pady=10,
                            highlightthickness=1, highlightbackground=COLORS["border"])
            card.grid(row=0, column=color, sticky="ew", padx=(0, 6) if color == BLACK else (6, 0))
            name = tk.Label(card, background=bg, foreground=fg, font=(FONT, 10), anchor="w")
            name.pack(side="left")
            value = tk.Label(card, background=bg, foreground=fg, font=(FONT, 26, "bold"))
            value.pack(side="right")
            self.player_labels[color], self.score_labels[color] = name, value
        self.board = BoardCanvas(play_area, self.play_move, self._hover, width=650, height=600)
        self.board.grid(row=1, column=0, sticky="nsew")
        self._label(play_area, textvariable=self.hover_var, foreground=COLORS["muted"],
                    font=(FONT, 9), anchor="center").grid(row=2, column=0, sticky="ew", pady=(7, 0))

        side = ttk.Frame(body, width=292)
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(6, weight=1)
        self._label(side, "对局设置", font=(FONT, 13, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        settings = ttk.Frame(side)
        settings.grid(row=1, column=0, sticky="ew")
        settings.columnconfigure((0, 1), weight=1, uniform="settings")
        self._label(settings, "对战模式", foreground=COLORS["muted"], font=(FONT, 9)).grid(row=0, column=0, sticky="w")
        self._label(settings, "你的棋色", foreground=COLORS["muted"], font=(FONT, 9)).grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.mode_combo = ttk.Combobox(settings, textvariable=self.mode_var, values=MODES, state="readonly", width=12)
        self.mode_combo.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        self.color_combo = ttk.Combobox(settings, textvariable=self.color_var, values=("黑棋 · 先手", "白棋 · 后手"), state="readonly", width=12)
        self.color_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 10))
        self._label(settings, "AI / 0.3、1、3 秒", foreground=COLORS["muted"], font=(FONT, 9)).grid(row=2, column=0, sticky="w")
        level = ttk.Combobox(settings, textvariable=self.level_var, values=tuple(LEVELS), state="readonly", width=12)
        level.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(0, 8))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda event: self.color_combo.configure(state="readonly" if self.mode_var.get() == MODES[0] else "disabled"))
        ttk.Button(settings, text="开始新局", style="Accent.TButton", command=self.new_game).grid(row=4, column=0, columnspan=2, sticky="ew")
        self._label(settings, "以上设置在开始新局后生效", foreground=COLORS["muted"], font=(FONT, 9)).grid(row=5, column=0, columnspan=2, sticky="w", pady=(5, 12))

        actions = ttk.Frame(side)
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        actions.columnconfigure((0, 1), weight=1, uniform="actions")
        self.undo_button = ttk.Button(actions, text="悔棋", style="Compact.TButton", command=self.undo)
        self.undo_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.hint_button = ttk.Button(actions, text="推荐落点", style="Compact.TButton", command=self.request_hint)
        self.hint_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.pause_button = ttk.Button(actions, text="暂停演示", style="Compact.TButton", command=self.toggle_pause)
        self.pause_button.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(7, 0))
        ttk.Checkbutton(actions, text="显示可落点", variable=self.show_legal_var,
                        command=self._render).grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(7, 0))

        analysis = tk.Frame(side, background=COLORS["surface"], padx=12, pady=10,
                            highlightbackground=COLORS["border"], highlightthickness=1)
        analysis.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self._label(analysis, "AI 思考", background=COLORS["surface"], font=(FONT, 10, "bold")).pack(anchor="w")
        self._label(analysis, textvariable=self.stats_var, background=COLORS["surface"],
                    foreground=COLORS["muted"], font=(FONT, 9), wraplength=266, height=2).pack(fill="x", pady=(4, 8))
        progress_track = tk.Frame(analysis, height=4, background=COLORS["border"])
        progress_track.pack(fill="x")
        self.progress_bar = ttk.Progressbar(progress_track, mode="indeterminate", style="Search.Horizontal.TProgressbar")
        self.progress_bar.place(x=0, y=0, relwidth=1, height=4)
        self._label(side, "落子记录", font=(FONT, 11, "bold")).grid(row=4, column=0, sticky="w")
        self.move_count_var = tk.StringVar()
        self._label(side, textvariable=self.move_count_var, foreground=COLORS["muted"], font=(FONT, 9)).grid(row=5, column=0, sticky="w", pady=(3, 6))
        log_frame = ttk.Frame(side)
        log_frame.grid(row=6, column=0, sticky="nsew")
        self.move_list = tk.Listbox(log_frame, height=5, font=(FONT, 10), background=COLORS["surface"],
                                   foreground=COLORS["ink"], selectbackground=COLORS["accent"], selectforeground="white",
                                   borderwidth=0, highlightthickness=1, highlightbackground=COLORS["border"],
                                   activestyle="none", exportselection=False)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.move_list.yview)
        self.move_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.move_list.pack(side="left", fill="both", expand=True)
        self._label(side, "方向键移动 · Enter 落子 · Ctrl+Z 悔棋", foreground=COLORS["muted"],
                    font=(FONT, 9)).grid(row=7, column=0, sticky="w", pady=(10, 0))

        footer = tk.Frame(outer, background=COLORS["surface"], padx=16, pady=10,
                          highlightthickness=1, highlightbackground=COLORS["border"])
        footer.pack(side="bottom", fill="x", pady=(16, 0), before=body)
        self._label(footer, textvariable=self.status_var, background=COLORS["surface"],
                    font=(FONT, 12, "bold")).pack(side="left")
        self._label(footer, textvariable=self.detail_var, background=COLORS["surface"],
                    foreground=COLORS["muted"], font=(FONT, 9)).pack(side="right")

    def _is_human(self):
        return self.mode == MODES[1] or (self.mode == MODES[0] and self.game.position.turn == self.human_color)

    def _render(self, status=None):
        position = self.game.position
        over = position.is_over
        for color, count in enumerate(position.counts):
            self.score_labels[color].configure(text=f"{count:02d}")
            role = "玩家" if self.mode == MODES[1] else "你" if self.mode == MODES[0] and color == self.human_color else "AI"
            marker = " · 当前回合" if color == position.turn and not over else ""
            self.player_labels[color].configure(text=f"{NAMES[color]} · {role}{marker}")
        last = self.game.history[-1] if self.game.history else None
        self.board.set_state(position, self._is_human() and not self.busy and not over,
                             last.move if last else None, self.hint_move, self.show_legal_var.get())
        can_undo = bool(self.game.history)
        if self.mode == MODES[0]:
            can_undo = any(record.color == self.human_color for record in self.game.history)
        self.undo_button.configure(state="normal" if can_undo else "disabled")
        self.hint_button.configure(state="normal" if self._is_human() and not self.busy and not over else "disabled",
                                   text="分析中…" if self.busy and self.search_kind == "hint" else "推荐落点")
        self.pause_button.configure(text="重试 AI" if self.ai_failed else "继续演示" if self.paused else "暂停演示",
                                    state="normal" if self.ai_failed or (self.mode == MODES[2] and not over) else "disabled")
        self.move_count_var.set(f"已落 {len(self.game.history)} 步 · 空位 {position.empty_count}")
        if status:
            self.status_var.set(status)
        elif over:
            winner = position.winner
            self.status_var.set("对局结束 · 平局" if winner is None else f"对局结束 · {NAMES[winner]}获胜")
        elif self.busy:
            self.status_var.set("正在寻找推荐落点…" if self.search_kind == "hint" else f"{NAMES[position.turn]} AI 正在思考…")
        elif self.paused and self.mode == MODES[2]:
            self.status_var.set("演示已暂停")
        else:
            self.status_var.set(f"轮到{NAMES[position.turn]} · {'点击棋盘落子' if self._is_human() else 'AI 即将落子'}")
        if over:
            b, w = position.counts
            self.detail_var.set(f"黑 {b} : {w} 白 · 双方均无合法落点")
        elif last and last.skipped is not None:
            self.detail_var.set(f"{NAMES[last.skipped]}无处可下，已自动跳过")
        else:
            self.detail_var.set(f"{self.mode} · {position.legal().bit_count()} 个合法落点")

    def _refresh_history(self):
        self.move_list.delete(0, "end")
        for i, record in enumerate(self.game.history, 1):
            self.move_list.insert("end", f" {i:02d}   {NAMES[record.color]}   {coordinate(record.move):>3}    翻 {record.flipped} 子")
            if record.skipped is not None:
                self.move_list.insert("end", f"        {NAMES[record.skipped]}自动跳过")
        if self.game.history:
            self.move_list.see("end")

    def _hover(self, move):
        if move is None:
            self.hover_var.set("小圆圈：可落点     棋子内圆点：上一步")
            return
        position = self.game.position
        count = flipped_bits(position.pieces(position.turn), position.pieces(1 - position.turn), move).bit_count()
        description = f"可翻转 {count} 枚棋子" if count else "已有棋子" if position.at(move) != EMPTY else "此处不能落子"
        self.hover_var.set(f"{coordinate(move)}  ·  {description}")

    def new_game(self):
        self._cancel_search()
        self.game = Game()
        self.mode = self.mode_var.get()
        self.human_color = BLACK if self.color_var.get().startswith("黑") else WHITE
        self.level = self.level_var.get()
        self.paused = self.ai_failed = False
        self.hint_move = None
        self.stats_var.set("等待对局\nAI 将在自己的回合自动落子。")
        self._refresh_history()
        self._render()
        self._schedule_ai()

    def play_move(self, move):
        if self.busy or not self._is_human() or self.game.position.is_over:
            return
        try:
            self.game.play(move)
        except ValueError:
            self._render("此处不能落子 · 请选有小圆圈的位置")
            return
        self.hint_move = None
        self._refresh_history()
        self._render()
        self._schedule_ai()

    def undo(self):
        if not self.game.history:
            return
        if self.mode == MODES[0] and not any(r.color == self.human_color for r in self.game.history):
            return
        self._cancel_search()
        self.game.undo()
        if self.mode == MODES[0]:
            while self.game.history and self.game.position.turn != self.human_color:
                self.game.undo()
        if self.mode == MODES[2]:
            self.paused = True
        self.ai_failed = False
        self.hint_move = None
        self.stats_var.set("已撤回落子\n分析将在下一次 AI 回合更新。")
        self._refresh_history()
        self._render()
        self._schedule_ai()

    def request_hint(self):
        if not self.busy and self._is_human() and not self.game.position.is_over:
            self._start_search("hint")

    def toggle_pause(self):
        if self.ai_failed:
            self.ai_failed = False
            self.paused = False
        elif self.mode == MODES[2]:
            self.paused = not self.paused
        else:
            return
        if self.paused:
            self._cancel_search()
            self.stats_var.set("演示已暂停\n可以悔棋、保存，或继续观看。")
        self._render()
        self._schedule_ai()

    def _schedule_ai(self):
        if self.next_ai_id is not None:
            self.root.after_cancel(self.next_ai_id)
            self.next_ai_id = None
        if not self.closed and not self.busy and not self.paused and not self.ai_failed and not self._is_human() and not self.game.position.is_over:
            self.next_ai_id = self.root.after(350, self._begin_ai)

    def _begin_ai(self):
        self.next_ai_id = None
        if not self.paused and not self.busy and not self._is_human() and not self.game.position.is_over:
            self._start_search("move")

    def _start_search(self, kind):
        self.search_kind, self.search_position = kind, self.game.position
        self.dead_worker_seen = False
        self.busy = True
        self.hint_move = None
        self.stats_var.set(f"{NAMES[self.search_position.turn]} · {self.level}模式\n正在计算，请稍候…")
        try:
            self.worker.start(self.search_position, LEVELS[self.level])
        except Exception:
            self._search_error("无法启动 AI 进程")
            return
        self.progress_bar.start(16)
        self._render()
        self.poll_id = self.root.after(50, self._poll_search)

    def _analysis_text(self, result, final=False):
        color = NAMES[self.search_position.turn]
        phase = "终局已解" if result.solved else f"完成 {result.depth} 层" if final else f"已搜索 {result.depth} 层"
        if abs(result.score) >= WIN:
            margin = (abs(result.score) - WIN) // 100
            score = f"预计{'胜' if result.score > 0 else '负'} {margin} 子"
        elif result.solved and result.score == 0:
            score = "预计平局"
        else:
            score = f"局面评价 {result.score:+d}"
        place = coordinate(result.move) if result.move is not None else "跳过"
        self.stats_var.set(f"{color} {place} · {phase} · {result.elapsed:.1f}s\n{score} · {result.nodes:,} 节点")

    def _poll_search(self):
        self.poll_id = None
        if not self.busy or self.closed:
            return
        if self.game.position != self.search_position:
            self._cancel_search()
            self._render()
            return
        for kind, payload in self.worker.messages():
            if kind == "progress":
                self._analysis_text(payload)
            elif kind == "error":
                logging.error("AI search failed: %s", payload)
                self._search_error("AI 计算失败")
                return
            elif kind == "result":
                search_kind = self.search_kind
                self.worker.cancel()
                self.busy = False
                self.progress_bar.stop()
                self.progress_bar.configure(value=0)
                if payload.move is None or not self.game.position.legal() & (1 << payload.move):
                    self._search_error("AI 未返回合法落点")
                    return
                self._analysis_text(payload, final=True)
                if search_kind == "hint":
                    self.hint_move = payload.move
                    self._render(f"推荐 {coordinate(payload.move)} · 点击金色圆圈落子")
                else:
                    self.game.play(payload.move)
                    self._refresh_history()
                    self._render()
                    self._schedule_ai()
                return
        if not self.worker.alive:
            # A process can send its last packet between the empty pipe poll and
            # is_alive(). Allow one more poll before declaring an unexpected exit.
            if self.dead_worker_seen:
                self._search_error("AI 进程意外结束")
                return
            self.dead_worker_seen = True
        self.poll_id = self.root.after(50, self._poll_search)

    def _search_error(self, text):
        is_move = self.search_kind == "move"
        self._cancel_search()
        self.ai_failed = is_move
        self.stats_var.set(f"{text}\n{'请点击「重试 AI」，或悔棋。' if is_move else '你仍可继续下棋，或重新请求提示。'}")
        self._render(text)

    def _cancel_search(self):
        for name in ("poll_id", "next_ai_id"):
            token = getattr(self, name)
            if token is not None:
                self.root.after_cancel(token)
                setattr(self, name, None)
        self.worker.cancel()
        self.busy = False
        self.progress_bar.stop()
        self.progress_bar.configure(value=0)

    def save_game(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="保存对局", defaultextension=".json",
                                          initialfile="黑白棋8x8对局.json", filetypes=[("黑白棋存档", "*.json")])
        if path:
            try:
                self.game.save(path, {"mode": self.mode, "human_color": self.human_color, "level": self.level})
            except (OSError, ValueError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=self.root)
                return
            self._render(f"已保存 · {Path(path).name}")

    def restore(self, path):
        """Read and validate everything before replacing the active game."""
        game, settings = Game.load(path)
        mode, color, level = settings.get("mode", MODES[0]), settings.get("human_color", BLACK), settings.get("level", "深入")
        if (not isinstance(mode, str) or mode not in MODES or type(color) is not int
                or color not in (BLACK, WHITE) or not isinstance(level, str) or level not in LEVELS):
            raise ValueError("存档中的对局设置无效")
        self._cancel_search()
        self.game, self.mode, self.human_color, self.level = game, mode, color, level
        self.mode_var.set(mode)
        self.color_var.set("黑棋 · 先手" if color == BLACK else "白棋 · 后手")
        self.color_combo.configure(state="readonly" if mode == MODES[0] else "disabled")
        self.level_var.set(level)
        self.paused = mode == MODES[2]
        self.ai_failed = False
        self.hint_move = None
        self.stats_var.set("已载入对局\n" + ("演示已暂停，点击继续后运行。" if self.paused else "轮到 AI 时将自动开始计算。"))
        self._refresh_history()
        self._render()
        self._schedule_ai()

    def load_game(self):
        path = filedialog.askopenfilename(parent=self.root, title="载入对局", filetypes=[("黑白棋存档", "*.json")])
        if path:
            try:
                self.restore(path)
            except (OSError, ValueError, UnicodeError) as exc:
                messagebox.showerror("载入失败", str(exc), parent=self.root)

    def show_rules(self):
        messagebox.showinfo("8×8 黑白棋规则",
                            "黑棋先行，双方轮流落子。\n\n"
                            "落下的棋子必须在横、竖或斜线方向，与已有己方棋子夹住连续的对方棋子；"
                            "被夹住的棋子全部翻为己方颜色。\n\n"
                            "没有合法落点时自动跳过。双方都无法落子即结束，即使棋盘尚未填满。棋子较多的一方获胜。\n\n"
                            "人机模式的悔棋会回到你上一次落子之前。推荐落点只显示建议，不会替你落子。\n"
                            "AI 演示可以随时暂停。新局设置在点击「开始新局」后生效。\n\n"
                            "AI 面板的局面评价以标注的棋色为准，正数较有利，不代表胜率。\n\n"
                            "快捷键：Ctrl+N 新局 / Ctrl+Z 悔棋 / Ctrl+S 保存 / Ctrl+O 载入 / F1 规则。",
                            parent=self.root)

    def close(self):
        if not self.closed:
            self.closed = True
            self._cancel_search()
            self.root.destroy()


def main():
    root = tk.Tk()
    ChessApp(root)
    root.mainloop()
