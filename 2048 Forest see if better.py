# gem_2048_complete.py
# Full single-file 2048-style "Gem Edition" with:
# - original features preserved (animations, floating +points, hammer/ad buttons)
# - timer + move counter (timer freezes on loss)
# - improved Game Over card (clear layout, Restart & Leaderboard buttons)
# - separate Leaderboard scene with 20 realistic fake players
# - user's entry ("You") has top block 4096 and is highlighted
# - leaderboard scrollable with mouse wheel; back button moved to top-left
# - highscore persisted to SAVE_FILE
#
# Requirements: pygame
# Run: python gem_2048_complete.py

import pygame
import random
import json
import math
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ---------------- CONFIG ----------------
GRID_SIZE = 4
ANIM_TIME = 140
MERGE_POP_TIME = 120
SPAWN_POP_TIME = 120
FLOAT_TEXT_TIME = 700
NEW_TILE_PROB_4 = 0.1
START_TILES = 2
FPS = 120
BASE_W, BASE_H = 560, 720
SAVE_FILE = Path('2048_save.json')
APP_TITLE = ""  # no "2048" sign

# theme
BG_GRAD_TOP = (20, 20, 30)
BG_GRAD_BOTTOM = (50, 0, 70)
BOARD_BG = (35, 32, 45)
EMPTY_CELL = (58, 54, 69)

TILE_COLORS = {
    2:   ((100, 180, 255), (255, 255, 255)),
    4:   ((120, 220, 120), (255, 255, 255)),
    8:   ((255, 140, 140), (255, 255, 255)),
    16:  ((200, 120, 255), (255, 255, 255)),
    32:  ((255, 200, 80),  (50, 50, 50)),
    64:  ((255, 100, 50),  (255, 255, 255)),
    128: ((80, 200, 200),  (0, 0, 0)),
    256: ((250, 250, 120), (50, 50, 50)),
    512: ((255, 170, 0),   (0, 0, 0)),
    1024:((255, 80, 180),  (255, 255, 255)),
    2048:((255, 255, 255), (0, 0, 0)),
    4096:((255, 245, 200), (0, 0, 0)),
}

STAT_LABEL = (195, 190, 210)
STAT_VALUE = (245, 240, 255)

# ---------- Helpers ----------
def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def ease_out_quart(t: float) -> float:
    return 1 - pow(1 - t, 4)

def draw_rounded_rect(surface, color, rect, radius):
    x, y, w, h = rect
    pygame.draw.rect(surface, color, (x+radius, y, w-2*radius, h))
    pygame.draw.rect(surface, color, (x, y+radius, w, h-2*radius))
    pygame.draw.circle(surface, color, (x+radius, y+radius), radius)
    pygame.draw.circle(surface, color, (x+w-radius, y+radius), radius)
    pygame.draw.circle(surface, color, (x+radius, y+h-radius), radius)
    pygame.draw.circle(surface, color, (x+w-radius, y+h-radius), radius)

def initials_from_name(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()

# ---------- Realistic leaderboard generation ----------
FAKE_NAMES = [
    "ShadowFox", "LunaWolf", "NeonTiger", "PixelMage", "CrimsonBlade",
    "StarryKnight", "SilentStorm", "FrostFang", "GoldenPhoenix", "IronClaw",
    "VelvetViper", "EchoShade", "SolarFlame", "MysticOwl", "QuantumBear",
    "AzureScribe", "OnyxRaven", "CinderSoul", "IvoryMoth", "ObsidianMonk",
    "CeruleanCat", "VioletWisp", "SableRider", "GildedHawk", "TempestPup"
]

# Your requested "You" top block is 4096
PLAYER_TOP_BLOCK = 4096
PLAYER_KNOWN_SCORE = 5552  # prior detail you gave

def realistic_leaderboard(num_entries=20, player_top_block=PLAYER_TOP_BLOCK, player_score=PLAYER_KNOWN_SCORE):
    """
    Generate realistic leaderboard where the player has the highest block (player_top_block)
    and fake players have blocks <= player_top_block (mostly smaller).
    Scores scale sensibly with blocks.
    """
    entries = []
    # We'll create a pool of possible blocks for fake players: from 128 -> 2048 (none >= player_top_block)
    possible_blocks = [2**k for k in range(7, 12)]  # 128,256,512,1024,2048
    # Tweak to ensure variety
    for i in range(num_entries - 1):
        name = random.choice(FAKE_NAMES) + (str(random.randint(1,99)) if random.random() < 0.35 else "")
        # pick block (bias toward mid-512/1024)
        block = random.choices(possible_blocks, weights=[5,12,20,18,8], k=1)[0]
        # score roughly correlated: base = block * factor + noise
        # choose factor between 2.5 and 4.5 depending on block (smaller blocks -> larger factor variance)
        base_factor = {128: 18, 256: 12, 512: 8, 1024:6, 2048:4}.get(block, 7)
        score = int(block * base_factor * (0.8 + random.random()*0.6))
        score = max(200, score)
        color = (random.randint(60,200), random.randint(60,200), random.randint(60,200))
        entries.append({"name": name, "score": score, "block": block, "color": color})
    # Insert the player (You) at a realistic position depending on their score
    entries.append({"name": "You", "score": player_score, "block": player_top_block, "color": (100,220,180)})
    entries.sort(key=lambda e: e["score"], reverse=True)
    # ensure top block is the player's (there won't be bigger than player_top_block)
    # and clamp size
    return entries[:num_entries]

LEADERBOARD = realistic_leaderboard(20)

# ---------- Model ----------
class Tile:
    __slots__ = ("value","row","col","prev_row","prev_col","merge_from",
                 "spawn_time","scale_time","moving","move_time",
                 "target_row","target_col","id")
    _next_id = 0
    def __init__(self, value, row, col):
        self.value = value
        self.row = row
        self.col = col
        self.prev_row = row
        self.prev_col = col
        self.merge_from = None
        self.spawn_time = 0
        self.scale_time = 0
        self.moving = False
        self.move_time = 0
        self.target_row = row
        self.target_col = col
        self.id = Tile._next_id
        Tile._next_id += 1

class Game2048:
    def __init__(self):
        self.grid: List[List[Optional[Tile]]] = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.score = 0
        self.highscore = 0
        self.highest_block = 0
        self.moves = 0
        self.start_time = 0
        self.elapsed_on_loss = 0
        self.load_save()
        self.reset()

    def load_save(self):
        if SAVE_FILE.exists():
            try:
                data = json.loads(SAVE_FILE.read_text())
                self.highscore = int(data.get("highscore", 0))
            except Exception:
                self.highscore = 0
        else:
            self.highscore = 0

    def save(self):
        try:
            SAVE_FILE.write_text(json.dumps({"highscore": self.highscore}))
        except Exception:
            pass

    def reset(self):
        self.grid = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.score = 0
        self.moves = 0
        self.highest_block = 0
        Tile._next_id = 0
        self.start_time = pygame.time.get_ticks()
        self.elapsed_on_loss = 0
        for _ in range(START_TILES):
            self.spawn_random(initial=True)

    def empty_cells(self):
        return [(r,c) for r in range(GRID_SIZE) for c in range(GRID_SIZE) if self.grid[r][c] is None]

    def spawn_random(self, initial=False):
        empties = self.empty_cells()
        if not empties:
            return False
        r,c = random.choice(empties)
        val = 4 if (not initial and random.random() < NEW_TILE_PROB_4) else 2
        t = Tile(val, r, c)
        t.spawn_time = pygame.time.get_ticks()
        self.grid[r][c] = t
        if val > self.highest_block:
            self.highest_block = val
        return True

    def can_move(self):
        if self.empty_cells(): return True
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                t = self.grid[r][c]
                if t is None: continue
                for dr,dc in ((1,0),(-1,0),(0,1),(0,-1)):
                    nr, nc = r+dr, c+dc
                    if 0<=nr<GRID_SIZE and 0<=nc<GRID_SIZE:
                        u = self.grid[nr][nc]
                        if u and u.value == t.value:
                            return True
        return False

    def activate_hammer(self):
        # clear a 2x2 top-left block
        if GRID_SIZE >= 2:
            for r in range(2):
                for c in range(2):
                    self.grid[r][c] = None
        self.spawn_random()

    def move(self, direction: str) -> bool:
        dr, dc = {
            'up': (-1,0), 'down': (1,0),
            'left': (0,-1), 'right': (0,1)
        }[direction]
        moved = False
        now = pygame.time.get_ticks()

        def traverse_line(line):
            nonlocal moved
            values = [self.grid[r][c] for r,c in line if self.grid[r][c] is not None]
            new_tiles: List[Optional[Tile]] = []
            skip = False
            for i in range(len(values)):
                if skip:
                    skip = False
                    continue
                if i+1 < len(values) and values[i].value == values[i+1].value:
                    new_val = values[i].value * 2
                    pos = line[len(new_tiles)]
                    new_t = Tile(new_val, *pos)
                    new_t.scale_time = now
                    new_t.spawn_time = now
                    new_t.merge_from = True
                    self.score += new_val
                    if new_val > self.highest_block:
                        self.highest_block = new_val
                    new_tiles.append(new_t)
                    skip = True
                    moved = True
                else:
                    t = values[i]
                    new_tiles.append(Tile(t.value, *line[len(new_tiles)]))
                    if (t.row, t.col) != line[len(new_tiles)-1]:
                        moved = True
            while len(new_tiles) < GRID_SIZE:
                new_tiles.append(None)
            return new_tiles

        if direction in ('left','right'):
            for r in range(GRID_SIZE):
                if direction == 'left':
                    line = [(r,c) for c in range(GRID_SIZE)]
                else:
                    line = [(r,c) for c in range(GRID_SIZE-1,-1,-1)]
                new_line = traverse_line(line)
                for idx,(rr,cc) in enumerate(line):
                    self.grid[rr][cc] = new_line[idx]
        else:
            for c in range(GRID_SIZE):
                if direction == 'up':
                    line = [(r,c) for r in range(GRID_SIZE)]
                else:
                    line = [(r,c) for r in range(GRID_SIZE-1,-1,-1)]
                new_line = traverse_line(line)
                for idx,(rr,cc) in enumerate(line):
                    self.grid[rr][cc] = new_line[idx]

        if moved:
            if self.score > self.highscore:
                self.highscore = self.score
                self.save()
            self.spawn_random()
            self.moves += 1
        return moved

# ---------- Floating +points ----------
class FloatingPlus:
    def __init__(self, text: str, r: int, c: int, start_time: int):
        self.text = text
        self.r = r
        self.c = c
        self.start_time = start_time
        self.alive = True

    def draw(self, surface, cell_size, board_x, board_y, font, now):
        dt = now - self.start_time
        if dt > FLOAT_TEXT_TIME:
            self.alive = False
            return
        k = dt / FLOAT_TEXT_TIME
        alpha = int(255 * (1 - k))
        rise = int(cell_size * 0.6 * k)
        x = board_x + self.c * (cell_size + 0) + (cell_size//2)
        y = board_y + self.r * (cell_size + 0) - 6 - rise
        surf = font.render(self.text, True, (240,235,255))
        surf.set_alpha(alpha)
        rect = surf.get_rect(center=(x,y))
        surface.blit(surf, rect)

# ---------- UI (scenes: play, gameover, leaderboard with scrolling) ----------
class UI:
    def __init__(self, game: Game2048):
        pygame.init()
        self.win = pygame.display.set_mode((BASE_W, BASE_H), pygame.RESIZABLE)
        pygame.display.set_caption(APP_TITLE)
        self.clock = pygame.time.Clock()
        self.game = game
        self.running = True
        self.last_swipe_pos: Optional[Tuple[int,int]] = None
        self.hammer_btn = pygame.Rect(0,0,0,0)
        self.ad_btn = pygame.Rect(0,0,0,0)
        self._submitted_to_fake_lb = False
        self.scene = 'play'  # 'play','gameover','leaderboard'
        self.leaderboard = LEADERBOARD
        # leaderboard scrolling state
        self.lb_scroll = 0.0
        self.lb_max_scroll = 0.0
        # dynamic buttons
        self.btn_restart: Optional[pygame.Rect] = None
        self.btn_lb: Optional[pygame.Rect] = None
        self.btn_lb_back: Optional[pygame.Rect] = None

    def layout(self):
        w,h = self.win.get_size()
        margin = int(min(w,h)*0.06)
        top_bar_h = int(h * 0.16)
        board_size = min(w - margin*2, h - margin*2 - top_bar_h)
        cell_gap = max(6, board_size // 80)
        grid = board_size
        cell_size = (grid - cell_gap*(GRID_SIZE+1)) // GRID_SIZE
        board_rect = pygame.Rect((w - grid)//2, top_bar_h + margin, grid, grid)
        title_pos = (board_rect.centerx, margin + top_bar_h//3)
        score_rect = pygame.Rect(board_rect.left, margin//2, 140, top_bar_h//2)
        best_rect = pygame.Rect(board_rect.left + 150, margin//2, 140, top_bar_h//2)
        new_rect = pygame.Rect(board_rect.right - 160, margin//2, 160, top_bar_h//2)
        return {
            'board_rect': board_rect,
            'cell_size': cell_size,
            'gap': cell_gap,
            'title_pos': title_pos,
            'score_rect': score_rect,
            'best_rect': best_rect,
            'new_rect': new_rect,
        }

    def draw_gradient_bg(self):
        w,h = self.win.get_size()
        for y in range(h):
            t = y / max(1, h-1)
            r = int(lerp(BG_GRAD_TOP[0], BG_GRAD_BOTTOM[0], t))
            g = int(lerp(BG_GRAD_TOP[1], BG_GRAD_BOTTOM[1], t))
            b = int(lerp(BG_GRAD_TOP[2], BG_GRAD_BOTTOM[2], t))
            pygame.draw.line(self.win, (r,g,b), (0,y), (w,y))

    def fonts(self):
        w,h = self.win.get_size()
        base = max(16, min(w,h)//26)
        font_name = pygame.font.get_default_font()
        def try_font(name,size,bold=False):
            try:
                return pygame.font.SysFont(name,size,bold=bold)
            except Exception:
                return pygame.font.SysFont(font_name,size,bold=bold)
        return {
            'title': try_font("arialroundedmtbold", base*2+2, True),
            'score': try_font("arialroundedmtbold", base, True),
            'button': try_font("arialroundedmtbold", base, True),
            'cell': try_font("arialroundedmtbold", int(base*1.4), True),
            'bigcell': try_font("arialroundedmtbold", int(base*1.2), True),
            'small': try_font("arialroundedmtbold", int(base*0.8), True),
            'float': try_font("arialroundedmtbold", int(base*1.0), True),
            'hud': try_font("arialroundedmtbold", int(base*0.9), True),
            'gameover_big': try_font("arialroundedmtbold", int(base*2.6), True),
            'lb_name': try_font("arialroundedmtbold", int(base*0.95), True),
            'lb_small': try_font("arialroundedmtbold", int(base*0.8), True),
        }

    # ---------- PLAY draw ----------
    def draw_top_bar(self, lay, fonts):
        # small app label on upper-left
        label = fonts['small'].render(APP_TITLE, True, (220,220,230))
        self.win.blit(label, (lay['board_rect'].left, 8))

        # Score & Best stat boxes
        def draw_stat_box(rect, label_text, value):
            draw_rounded_rect(self.win, (60,56,74), rect, 12)
            inner = rect.inflate(-10,-10)
            draw_rounded_rect(self.win, (82,76,99), inner, 8)
            lab_surf = fonts['small'].render(label_text, True, STAT_LABEL)
            val_surf = fonts['score'].render(str(value), True, STAT_VALUE)
            self.win.blit(lab_surf, lab_surf.get_rect(center=(inner.centerx, inner.top+12)))
            self.win.blit(val_surf, val_surf.get_rect(center=(inner.centerx, inner.centery+8)))

        draw_stat_box(lay['score_rect'], "SCORE", self.game.score)
        draw_stat_box(lay['best_rect'], "BEST", self.game.highscore)

        # NEW GAME button
        draw_rounded_rect(self.win, (120,100,160), lay['new_rect'], 10)
        txt = fonts['button'].render("NEW GAME", True, (249,246,242))
        self.win.blit(txt, txt.get_rect(center=lay['new_rect'].center))

        # Time (bottom left) & Moves (bottom right)
        elapsed = (self.game.elapsed_on_loss if self.scene == 'gameover' else (pygame.time.get_ticks() - self.game.start_time)//1000)
        minutes, seconds = divmod(elapsed, 60)
        time_text = fonts['score'].render(f"Time: {minutes:02}:{seconds:02}", True, (245,245,250))
        moves_text = fonts['score'].render(f"Moves: {self.game.moves}", True, (230,230,235))
        self.win.blit(time_text, (18, self.win.get_height() - 60))
        self.win.blit(moves_text, (self.win.get_width() - moves_text.get_width() - 18, self.win.get_height() - 60))

        # Bottom-center Power-Up button
        btn_w, btn_h = 180, 50
        btn_x = (self.win.get_width() - btn_w)//2
        btn_y = self.win.get_height() - btn_h - 18
        self.ad_btn = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        pygame.draw.rect(self.win, (70,130,200), self.ad_btn, border_radius=10)
        ad_text = fonts['small'].render("🎁 Power-Up", True, (255,255,255))
        self.win.blit(ad_text, ad_text.get_rect(center=self.ad_btn.center))

    def cell_rect(self, lay, r, c):
        board = lay['board_rect']
        size = lay['cell_size']
        gap = lay['gap']
        x = board.x + gap + c*(size+gap)
        y = board.y + gap + r*(size+gap)
        return pygame.Rect(x, y, size, size)

    def draw_board(self, lay):
        draw_rounded_rect(self.win, BOARD_BG, lay['board_rect'], 16)
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                rect = self.cell_rect(lay, r, c)
                draw_rounded_rect(self.win, EMPTY_CELL, rect, 12)

    def draw_tiles(self, lay, fonts):
        now = pygame.time.get_ticks()
        positions = {}
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                t = self.game.grid[r][c]
                if not t: continue
                start_rect = self.cell_rect(lay, t.prev_row, t.prev_col)
                end_rect = self.cell_rect(lay, t.row, t.col) if not t.moving else self.cell_rect(lay, t.target_row, t.target_col)
                if t.moving:
                    dt = min(1.0, max(0.0, (now - t.move_time)/ANIM_TIME))
                    k = ease_out_quart(dt)
                    x = int(lerp(start_rect.x, end_rect.x, k))
                    y = int(lerp(start_rect.y, end_rect.y, k))
                    rect = pygame.Rect(x,y,end_rect.w,end_rect.h)
                    if dt >= 1:
                        t.row, t.col = t.target_row, t.target_col
                        t.prev_row, t.prev_col = t.row, t.col
                        t.moving = False
                        t.move_time = 0
                else:
                    rect = self.cell_rect(lay, t.row, t.col)
                positions[t.id] = rect

        tiles = [self.game.grid[r][c] for r in range(GRID_SIZE) for c in range(GRID_SIZE) if self.game.grid[r][c]]
        tiles.sort(key=lambda z: (z.value, z.id))
        for t in tiles:
            rect = positions.get(t.id, self.cell_rect(lay, t.row, t.col))
            color, text_color = TILE_COLORS.get(t.value, ((60,58,51),(249,246,242)))
            # spawn/merge scale
            scale = 1.0
            if t.scale_time:
                dt = (now - t.scale_time)/MERGE_POP_TIME
                if dt < 1:
                    scale = 1.0 + 0.12*math.sin(dt*math.pi)
                else:
                    t.scale_time = 0
            elif t.spawn_time:
                dt = (now - t.spawn_time)/SPAWN_POP_TIME
                if dt < 1:
                    scale = 0.6 + 0.4*ease_out_quart(dt)
            if scale != 1.0:
                cx,cy = rect.center
                new_w = int(rect.w*scale); new_h = int(rect.h*scale)
                rect = pygame.Rect(cx - new_w//2, cy - new_h//2, new_w, new_h)
            draw_rounded_rect(self.win, color, rect, max(8, rect.w//9))
            font = fonts['cell'] if t.value < 1024 else fonts['bigcell']
            txt = font.render(str(t.value), True, text_color)
            self.win.blit(txt, txt.get_rect(center=rect.center))
            if t.merge_from and t.spawn_time:
                dt = now - t.spawn_time
                if dt < FLOAT_TEXT_TIME:
                    k = dt / FLOAT_TEXT_TIME
                    alpha = int(255*(1-k))
                    rise = int(rect.h * 0.6 * k)
                    ftxt = "+{}".format(t.value)
                    surf = fonts['float'].render(ftxt, True, (240,235,255))
                    surf.set_alpha(alpha)
                    self.win.blit(surf, surf.get_rect(center=(rect.centerx, rect.top - 6 - rise)))
                else:
                    t.merge_from = None

    # ---------- PLAY input ----------
    def handle_events_play(self, lay):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                pass
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.last_swipe_pos = event.pos
                if lay['new_rect'].collidepoint(event.pos):
                    self.game.reset()
                    self._submitted_to_fake_lb = False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.last_swipe_pos:
                dx = event.pos[0] - self.last_swipe_pos[0]
                dy = event.pos[1] - self.last_swipe_pos[1]
                self.last_swipe_pos = None
                if abs(dx) < 20 and abs(dy) < 20:
                    # tap: check buttons
                    if self.ad_btn.collidepoint(event.pos):
                        self.handle_powerup_click()
                        return
                    if lay['new_rect'].collidepoint(event.pos):
                        self.game.reset()
                        self._submitted_to_fake_lb = False
                    return
                if abs(dx) > abs(dy):
                    self.game.move('right' if dx > 0 else 'left')
                else:
                    self.game.move('down' if dy > 0 else 'up')
                    return
                if abs(dx) > abs(dy):
                    self.game.move('right' if dx > 0 else 'left')
                else:
                    self.game.move('down' if dy > 0 else 'up')
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    self.game.move('left')
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.game.move('right')
                elif event.key in (pygame.K_UP, pygame.K_w):
                    self.game.move('up')
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.game.move('down')
                elif event.key == pygame.K_r:
                    self.game.reset()
                    self._submitted_to_fake_lb = False

    def handle_powerup_click(self):
        # Simulate ad
        print("[Ad] Watching ad...")
        overlay = pygame.Surface(self.win.get_size(), pygame.SRCALPHA)
        overlay.fill((0,0,0,180))
        ad_text = pygame.font.SysFont(None, 48).render("Watching ad...", True, (255,255,255))
        overlay.blit(ad_text, ad_text.get_rect(center=(self.win.get_width()//2, self.win.get_height()//2)))
        self.win.blit(overlay, (0,0))
        pygame.display.update()
        pygame.time.delay(1000)  # simulate ad duration

        # Determine highest value
        highest = self.game.highest_block

        # Collect tiles to remove
        tiles_to_remove = [(r,c) for r in range(GRID_SIZE) for c in range(GRID_SIZE)
                        if self.game.grid[r][c] and self.game.grid[r][c].value != highest]

        # Animate shrink + fade
        steps = 6
        for step in range(steps):
            self.draw_gradient_bg()
            lay = self.layout()
            fonts = self.fonts()
            self.draw_top_bar(lay, fonts)
            self.draw_board(lay)
            now = pygame.time.get_ticks()
            for r,c in tiles_to_remove:
                t = self.game.grid[r][c]
                if t:
                    rect = self.cell_rect(lay, t.row, t.col)
                    scale = max(0, 1 - 0.15*(step+1))
                    cx,cy = rect.center
                    new_w = int(rect.w*scale)
                    new_h = int(rect.h*scale)
                    draw_rounded_rect(self.win, TILE_COLORS[t.value][0], pygame.Rect(cx-new_w//2, cy-new_h//2, new_w, new_h), max(8,new_w//9))
            self.draw_tiles(lay, fonts)
            pygame.display.update()
            pygame.time.delay(50)

        # Remove tiles
        for r,c in tiles_to_remove:
            self.game.grid[r][c] = None


    # ---------- GAMEOVER draw (improved layout) ----------
        # ---------- GAMEOVER draw (fixed layout) ----------
    def draw_game_over(self, lay, fonts):
        board = lay['board_rect']
        overlay = pygame.Surface((board.w, board.h), pygame.SRCALPHA)
        overlay.fill((10, 10, 15, 200))
        self.win.blit(overlay, board.topleft)

        # card (taller for spacing)
        card_w = int(board.w * 0.66)
        card_h = int(board.h * 0.68)
        card_x = board.left + (board.w - card_w)//2
        card_y = board.top + (board.h - card_h)//2
        card_rect = pygame.Rect(card_x, card_y, card_w, card_h)
        draw_rounded_rect(self.win, (26,24,36), card_rect, 14)
        inner = card_rect.inflate(-6,-6)
        draw_rounded_rect(self.win, (36,34,50), inner, 12)

        # Title
        title = fonts['gameover_big'].render("Game Over", True, (245,240,250))
        self.win.blit(title, title.get_rect(center=(card_rect.centerx, card_rect.top + 44)))

        # Stats (slightly bigger than original)
        stat_top = card_rect.top + 110
        score_surf = fonts['button'].render(f"Score: {self.game.score}", True, (225,220,235))
        self.win.blit(score_surf, score_surf.get_rect(center=(card_rect.centerx, stat_top)))
        stat_top += 50
        block_surf = fonts['button'].render(f"Highest Block: {self.game.highest_block}", True, (225,220,235))
        self.win.blit(block_surf, block_surf.get_rect(center=(card_rect.centerx, stat_top)))
        stat_top += 40
        moves_surf = fonts['button'].render(f"Moves: {self.game.moves}", True, (225,220,235))
        self.win.blit(moves_surf, moves_surf.get_rect(center=(card_rect.centerx, stat_top)))
        stat_top += 40
        minutes, seconds = divmod(self.game.elapsed_on_loss, 60)
        time_surf = fonts['button'].render(f"Time: {minutes:02}:{seconds:02}", True, (225,220,235))
        self.win.blit(time_surf, time_surf.get_rect(center=(card_rect.centerx, stat_top)))

        # Buttons: Restart & Leaderboard (slightly smaller)
        btn_w, btn_h = 130, 40  # slightly smaller
        gap = 20
        btn_y = card_rect.bottom - btn_h - 20
        center_x = card_rect.centerx
        rect_restart = pygame.Rect(center_x - btn_w - gap//2, btn_y, btn_w, btn_h)
        rect_lb = pygame.Rect(center_x + gap//2, btn_y, btn_w, btn_h)
        draw_rounded_rect(self.win, (120,100,160), rect_restart, 12)
        draw_rounded_rect(self.win, (70,130,200), rect_lb, 12)
        r_text = fonts['button'].render("Restart", True, (245,245,245))
        lb_text = fonts['button'].render("Leaderboard", True, (245,245,245))
        self.win.blit(r_text, r_text.get_rect(center=rect_restart.center))
        self.win.blit(lb_text, lb_text.get_rect(center=rect_lb.center))
        self.btn_restart = rect_restart
        self.btn_lb = rect_lb


        # info note
        note = fonts['small'].render("Developed by Zachariah Crosby", True, (210, 200, 190))
        self.win.blit(note, note.get_rect(center=(card_rect.centerx, card_rect.bottom - 8)))

        # submit once
        if not self._submitted_to_fake_lb:
            self._submit_player_to_local_lb()
            self._submitted_to_fake_lb = True


    def _submit_player_to_local_lb(self):
        user_name = "You"
        found = None
        for e in self.leaderboard:
            if e.get("name") == user_name:
                found = e
                break
        if found:
            updated = False
            if self.game.score > found["score"]:
                found["score"] = self.game.score
                updated = True
            if self.game.highest_block > found.get("block", 0):
                found["block"] = self.game.highest_block
                updated = True
            if updated:
                found["color"] = (100,220,180)
        else:
            self.leaderboard.append({"name":"You","score":self.game.score,"block":self.game.highest_block,"color":(100,220,180)})
        self.leaderboard.sort(key=lambda e: e["score"], reverse=True)
        if len(self.leaderboard) > 20:
            self.leaderboard = self.leaderboard[:20]

    # ---------- gameover input ----------
    def handle_events_gameover(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if self.btn_restart and self.btn_restart.collidepoint(pos):
                    self.game.reset()
                    self.scene = 'play'
                    self._submitted_to_fake_lb = False
                    self.game.elapsed_on_loss = 0
                elif self.btn_lb and self.btn_lb.collidepoint(pos):
                    self.scene = 'leaderboard'
                    # reset scroll so user sees top at first
                    self.lb_scroll = 0.0

    # ---------- leaderboard scene (scrollable) ----------
    def draw_leaderboard_scene(self, lay, fonts):
        w,h = self.win.get_size()
        pad = 28
        card = pygame.Rect(pad, pad+12, w - pad*2, h - pad*2 - 12)
        draw_rounded_rect(self.win, (28,26,40), card, 14)
        inner = card.inflate(-6,-6)
        draw_rounded_rect(self.win, (36,34,50), inner, 12)

        title = fonts['gameover_big'].render("Leaderboard", True, (245,240,250))
        self.win.blit(title, title.get_rect(center=(card.centerx, card.top + 42)))

        # Back button moved to top-left of card (less intrusive)
        btn_w, btn_h = 88, 34
        back_rect = pygame.Rect(card.left + 18, card.top + 18, btn_w, btn_h)
        draw_rounded_rect(self.win, (120,100,160), back_rect, 8)
        back_txt = fonts['small'].render("Back", True, (245,245,245))
        self.win.blit(back_txt, back_txt.get_rect(center=back_rect.center))
        self.btn_lb_back = back_rect

        # headers
        start_y = card.top + 96
        gap_y = 36
        col_x_name = card.left + 80
        col_x_score = card.centerx + 30
        col_x_block = card.right - 140
        header_name = fonts['lb_name'].render("Player", True, (220,210,200))
        header_score = fonts['lb_name'].render("Score", True, (220,210,200))
        header_block = fonts['lb_name'].render("Top Block", True, (220,210,200))
        self.win.blit(header_name, (col_x_name, start_y))
        self.win.blit(header_score, (col_x_score, start_y))
        self.win.blit(header_block, (col_x_block, start_y))

        # determine scrolling area
        visible_h = card.h - 160
        entry_h = gap_y
        total_h = len(self.leaderboard) * entry_h
        # compute max scroll
        self.lb_max_scroll = max(0, total_h - visible_h)

        # clamp lb_scroll
        if self.lb_scroll < 0:
            self.lb_scroll = 0
        if self.lb_scroll > self.lb_max_scroll:
            self.lb_scroll = self.lb_max_scroll

        # draw entries using scroll offset
        y0 = start_y + 26 - int(self.lb_scroll)
        for i, e in enumerate(self.leaderboard):
            if y0 + i*entry_h > card.bottom - 28:
                # beyond visible bottom (still iterate to allow scrolling)
                pass
        # Now render visible range
        for i, e in enumerate(self.leaderboard):
            y = start_y + 26 + i*gap_y - int(self.lb_scroll)
            # skip if not visible region
            if y < card.top + 96 or y > card.bottom - 40:
                continue
            # avatar
            av_x = card.left + 30
            av_y = y + 6
            pygame.draw.circle(self.win, e['color'], (av_x, av_y), 14)
            initials = initials_from_name(e['name'])
            ix = fonts['small'].render(initials, True, (12,12,12))
            self.win.blit(ix, ix.get_rect(center=(av_x,av_y)))
            # highlight "You"
            if e['name'] == "You":
                # light highlight row background
                highlight_rect = pygame.Rect(card.left + 60, y - 6, card.width - 120, gap_y - 4)
                s = pygame.Surface((highlight_rect.w, highlight_rect.h), pygame.SRCALPHA)
                s.fill((80,160,120,40))
                self.win.blit(s, (highlight_rect.x, highlight_rect.y))
            name_surf = fonts['lb_small'].render(f"{i+1}. {e['name']}", True, (235,235,235))
            score_surf = fonts['lb_small'].render(str(e['score']), True, (220,220,220))
            block_surf = fonts['lb_small'].render(str(e['block']), True, (200,200,200))
            self.win.blit(name_surf, (av_x + 30, y))
            self.win.blit(score_surf, (col_x_score, y))
            self.win.blit(block_surf, (col_x_block, y))

        # small scrollbar on the right of card if needed
        if self.lb_max_scroll > 0:
            bar_x = card.right - 18
            bar_h = card.h - 160
            bar_y = card.top + 96
            # draw track
            pygame.draw.rect(self.win, (60,60,70), (bar_x, bar_y, 8, bar_h), border_radius=4)
            # thumb height proportional
            thumb_h = max(32, int(bar_h * (bar_h / (total_h if total_h>0 else 1))))
            thumb_pos = int((bar_h - thumb_h) * (self.lb_scroll / self.lb_max_scroll)) if self.lb_max_scroll else 0
            pygame.draw.rect(self.win, (160,160,180), (bar_x+1, bar_y + thumb_pos, 6, thumb_h), border_radius=4)

    def handle_events_leaderboard(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if self.btn_lb_back and self.btn_lb_back.collidepoint(pos):
                    self.scene = 'gameover'  # return to gameover
            elif event.type == pygame.MOUSEWHEEL:
                # adjust scroll: typically event.y positive on wheel up
                # invert to make wheel up = scroll up (decrease offset)
                scroll_amount = -event.y * 28  # 28 px per tick
                self.lb_scroll += scroll_amount
                # clamp
                if self.lb_scroll < 0: self.lb_scroll = 0
                if self.lb_scroll > self.lb_max_scroll: self.lb_scroll = self.lb_max_scroll

    # ---------- main run loop ----------
    def run(self):
        while self.running:
            self.clock.tick(FPS)
            lay = self.layout()
            fonts = self.fonts()

            if self.scene == 'play':
                self.handle_events_play(lay)
                self.draw_gradient_bg()
                self.draw_top_bar(lay, fonts)
                self.draw_board(lay)
                self.draw_tiles(lay, fonts)
                if not self.game.can_move():
                    self.scene = 'gameover'
                    self.game.elapsed_on_loss = (pygame.time.get_ticks() - self.game.start_time)//1000
                    self._submitted_to_fake_lb = False
                pygame.display.flip()

            elif self.scene == 'gameover':
                self.handle_events_gameover()
                self.draw_gradient_bg()
                self.draw_top_bar(lay, fonts)
                self.draw_board(lay)
                self.draw_tiles(lay, fonts)
                self.draw_game_over(lay, fonts)
                pygame.display.flip()

            elif self.scene == 'leaderboard':
                self.handle_events_leaderboard()
                self.draw_gradient_bg()
                self.draw_leaderboard_scene(lay, fonts)
                pygame.display.flip()

        pygame.quit()

# ---------- Google Play stub ----------
def submit_score_to_google_play(score: int):
    print(f"[Stub] Submit score {score} to Google Play (not integrated)")

# ---------- Entry ----------
if __name__ == "__main__":
    game = Game2048()
    ui = UI(game)
    ui.run()
