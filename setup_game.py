"""Handle the loading and initialization of game sessions."""
from __future__ import annotations

import copy
import lzma
import pickle
import traceback
from typing import Optional

import tcod
from tcod import libtcodpy

import color
import entity_factories
import input_handlers

from engine import Engine
from procgen import generate_dungeon

background_image = tcod.image.load("menu_background.png")[:, :, :3]

def new_game() -> Engine:
	map_width = 80
	map_height = 43

	room_max_size = 10
	room_min_size = 6
	max_rooms = 30

	max_monsters_per_room = 2
	max_items_per_room = 2

	player = copy.deepcopy(enitity_factories.player)

	engine = Engine(player=player)

	engine.game_map = generate_dungeon(
		max_rooms=max_rooms,
		room_min_size=room_min_size,
		room_max_size=room_max_size,
		map_width=map_width,
		map_height=map_height,
		max_monsters_per_room=max_monsters_per_room,
		max_items_per_room=max_items_per_room,
		engine=engine,
	)
	engine.update_fov()

	engine.message_log.add_message(
		"Welcome...", color.welcome_text
	)

	return engine

def load_game(filename: str) -> Engine:
	"""Load an engine instance from a file."""
	with open(filename, "rb") as f:
		engine = pickle.loads(lzma.decompress(f.read()))
	assert isinstance(engine, Engine)
	return engine

class MainMenu(input_handlers.BaseEventHandler):
	"""Handle the main menu rendering and input"""

	def on_render(self, console: tcod.console.Console) -> None:
		"""Render the main menu on a background image"""

		console.draw_semigraphics(background_image, 0, 0)

		console.print(
			console.width // 2,
			console.height // 2 - 4,
			"DESOLATE ARCHIVE",
			fg=color.menu_title,
			alignment=libtcodpy.CENTER,
		)
		console.print(
			console.width // 2,
			console.height - 2,
			"sss",
			fg=color.menu_title,
			alignment=libtcodpy.CENTER,
		)

		menu_width = 24
		for i, text in enumerate(
			["[N] New Game", "[C] Continue", "[Q] Quit"]
		):
			console.print(
				console.width // 2,
				console.height // 2 - 2 + i,
				text.ljust(menu_width),
				fg=color.menu_text,
				bg=color.black,
				alignment=libtcodpy.CENTER,
				bg_blend=libtcodpy.BKGND_ALPHA(64),
			)

	def ev_keydown(
		self, event: tcod.event.KeyDown
	) -> Optional[input_handlers.BaseEventHandler]:
		if event.sym in (tcod.event.KeySym.Q, tcod.event.KeySym.ESCAPE):
			raise SystemExit()
		elif event.sym == tcod.event.KeySym.C:
			try:
				return input_handlers.MainGameEventHandler(load_game("savegame.sav"))
			except FileNotFoundError:
				return input_handlers.PopupMessage(self, "No saved games to load.")
			except Exception as exc:
				traceback.print_exc()
				return input_handlers.PopupMessage(self, f"Failed to load save:\n{exc}")
		elif event.sym == tcod.event.KeySym.N:
			return input_handlers.MainGameEventHandler(new_game())

		return None
