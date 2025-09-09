"""Handle the loading and initialization of game sessions."""
from __future__ import annotations

import copy
from typing import Optional

import tcod

import color
import entity_factories
import input_handlers

from engine import Engine
from procgen import generate_dungeon

background_image = tcod.image.load(menu_background.png)[:, :, 3]

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

class MainMenu(input_handlers.BaseEventHandler):
	"""Handle the main menu rendering and input"""

	def on_render(self, console: tcod.Console) -> None:
		"""Render the main menu on a background image"""
		console.draw_semigraphics(backgroun_image, 0, 0)

		console.print(
			console.width // 2,
			console.height // 2 - 4,
			"DESOLATE ARCHIVE",
			fg=color.menu_title,
			alignment=tcod.CENTER,
		)
		console.print(
			console.width // 2,
			console.height - 2,
			"sss",
			fg=color.menu_title,
			alignment=tcod.CENTER,
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
				alignment=tcod.CENTER,
				bg_blend=tcod.BKGND_ALPHA(64),
			)

	def ev_keydown(
		self, event: tcod.event.KeyDown
	) -> Optional[input_handlers.BaseEventHandler]:
		if event.sym in (tcod.event.KeySym.Q, tcod.event.KeySym.ESCAPE):
			raise SystemExit()
		elif event.sym == tcod.event.KeySym.C:
			# TODO Load
			pass
		elif event.sym == tcod.event.KeySym.N
			return input_handlers.MainGameEventHandler(new_game())

		return None
