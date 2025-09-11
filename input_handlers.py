from __future__ import annotations

import os

import tcod.event
import color
import exceptions
import actions

from actions import (
	Action,
	BumpAction,
	PickupAction,
	WaitAction
)
from tcod import libtcodpy
from typing import Callable, Optional, TYPE_CHECKING, Tuple, Union

if TYPE_CHECKING:
	from engine import Engine
	from entity import Item

MOVE_KEYS = {
	# Arrow keys.
	tcod.event.KeySym.UP: (0, -1),
	tcod.event.KeySym.DOWN: (0, 1),
	tcod.event.KeySym.LEFT: (-1, 0),
	tcod.event.KeySym.RIGHT: (1, 0),
	tcod.event.KeySym.HOME: (-1, -1),
	tcod.event.KeySym.END: (-1, 1),
	tcod.event.KeySym.PAGEUP: (1, -1),
	tcod.event.KeySym.PAGEDOWN: (1, 1),
	# Numpad keys.
	tcod.event.KeySym.KP_1: (-1, 1),
	tcod.event.KeySym.KP_2: (0, 1),
	tcod.event.KeySym.KP_3: (1, 1),
	tcod.event.KeySym.KP_4: (-1, 0),
	tcod.event.KeySym.KP_6: (1, 0),
	tcod.event.KeySym.KP_7: (-1, -1),
	tcod.event.KeySym.KP_8: (0, -1),
	tcod.event.KeySym.KP_9: (1, -1),
	# Vi keys.
	tcod.event.KeySym.H: (-1, 0),
	tcod.event.KeySym.J: (0, 1),
	tcod.event.KeySym.K: (0, -1),
	tcod.event.KeySym.L: (1, 0),
	tcod.event.KeySym.Y: (-1, -1),
	tcod.event.KeySym.U: (1, -1),
	tcod.event.KeySym.B: (-1, 1),
	tcod.event.KeySym.N: (1, 1),
}

WAIT_KEYS = {
	tcod.event.KeySym.PERIOD,
	tcod.event.KeySym.KP_5,
	tcod.event.KeySym.CLEAR,
}

CONFIRM_KEYS = {
	tcod.event.KeySym.RETURN,
	tcod.event.KeySym.KP_ENTER
}

CURSOR_Y_KEYS = {
	tcod.event.KeySym.UP: -1,
	tcod.event.KeySym.DOWN: 1,
	tcod.event.KeySym.PAGEUP: -10,
	tcod.event.KeySym.PAGEDOWN: 10,
}

ActionOrHandler = Union[Action, "BaseEventHandler"]

class BaseEventHandler(tcod.event.EventDispatch[ActionOrHandler]):
	def handle_events(self, event: tcod.event.Event) -> BaseEventHandler:
		"""Handle an event and return the next active event handler."""
		state = self.dispatch(event)
		if isinstance(state, BaseEventHandler):
			return state
		assert not isinstance(state, Action), f"{self!r} cannot handle actions."
		return self

	def on_render(self, console: tcod.console.Console) -> None:
		raise NotImplementedError()

	def ev_quit(self, event: tcod.event.Quit) -> Optional[Action]:
		raise SystemExit()

class PopupMessage(BaseEventHandler):
	"""Display a popup text window."""

	def __init__(self, parent_handler: BaseEventHandler, text: str):
		self.parent = parent_handler
		self.text = text

	def on_render(self, console: tcod.console.Console) -> None:
		"""Render the parent and dim the result. Print message on top"""
		self.parent.on_render(console)
		console.rgb["fg"] //= 8
		console.rgb["bg"] //= 8

		console.print(
			console.width // 2,
			console.height // 2,
			self.text,
			fg=color.white,
			bg=color.black,
			alignment=tcod.CENTER,
		)

	def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[BaseEventHandler]:
		"""Any ket returns to the parent handler."""
		return self.parent

class EventHandler(BaseEventHandler):
	def __init__(self, engine: Engine):
		self.engine = engine

	def handle_events(self, event: tcod.event.Event) -> BaseEventHandler:
		"""Handle events for input handlers with an engine."""
		action_or_state = self.dispatch(event)
		if isinstance(action_or_state, BaseEventHandler):
			return action_or_state
		if self.handle_action(action_or_state):
			# A valid action was performed
			if not self.engine.player.is_alive:
				return GameOverEventHandler(self.engine)
			return MainGameEventHandler(self.engine)
		return self

	def handle_action(self, action: Optional[Action]) -> bool:
		"""Handle actions returned from event methods.

		Returns True if the action will advance the turn.
		"""
		if action is None:
			return False

		try:
			action.perform()
		except exceptions.Impossible as exc:
			self.engine.message_log.add_message(exc.args[0], color.impossible)
			return False

		self.engine.handle_enemy_turns()

		self.engine.update_fov()
		return True

	def ev_mousemotion(self, event: tcod.event.MouseMotion) -> None:
		if self.engine.game_map.in_bounds(event.tile.x, event.tile.y):
			self.engine.mouse_location = event.tile.x, event.tile.y

	def on_render(self, console: tcod.console.Console) -> None:
		self.engine.render(console)

class AskUserEventHandler(EventHandler):
	"""Handles user input for actions which require special input."""

	def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[ActionOrHandler]:
		"""By default any key exists this input handler."""
		if event.sym in { # Ignore modifier keys.
			tcod.event.KeySym.LSHIFT,
			tcod.event.KeySym.RSHIFT,
			tcod.event.KeySym.LCTRL,
			tcod.event.KeySym.RCTRL,
			tcod.event.KeySym.LALT,
			tcod.event.KeySym.RALT,
		}:
			return None

		return self.on_exit()

	def ev_mousebuttondown(
		self, event: tcod.event.MouseButtonDown
	) -> Optional[ActionOrHandler]:
		"""By default any mouse clikc exits this input handler."""
		return self.on_exit()

	def on_exit(self) -> Optional[ActionOrHandler]:
		"""Called when the user is trying to exit or cancel an action.

		By default this returns to the main event handler.
		"""
		return MainGameEventHandler(self.engine)

class InventoryEventHandler(AskUserEventHandler):
	"""This handler lets the user select an item.

	What happens then depends on the subclass.
	"""

	TITLE = "<missing title>"

	def on_render(self, console: tcod.Console) -> None:
		"""Render an inventory menu, which displays the items in the inventory, and the letter to select them.
		Will move to a different position based on where the player is located, so the player can always see where
		they are.
		"""
		super().on_render(console)
		number_of_items_in_inventory = len(self.engine.player.inventory.items)

		height = number_of_items_in_inventory + 2

		if height <= 3:
			height = 3

		if self.engine.player.x <= 30:
			x = 40
		else:
			x = 0

		y = 0

		width = len(self.TITLE) + 4

		console.draw_frame(
			x=x,
			y=y,
			width=width,
			height=height,
			title=self.TITLE,
			clear=True,
			fg=(255, 255, 255),
			bg=(0, 0, 0),
		)

		if number_of_items_in_inventory > 0:
			for i, item in enumerate(self.engine.player.inventory.items):
				item_key = chr(ord("a") + i)
				console.print(x + 1, y + i + 1, f"({item_key}) {item.name}")
		else:
			console.print(x + 1, y + 1, "(Empty)")

	def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[ActionOrHandler]:
		player = self.engine.player
		key = event.sym
		index = key - tcod.event.KeySym.A

		if 0 <= index <= 26:
			try:
				selected_item = player.inventory.items[index]
			except IndexError:
				self.engine.message_log.add_message("Invalid entry", color.invalid)

			return self.on_item_selected(selected_item)
		return super().ev_keydown(event)

	def on_item_selected(self, item: Item) -> Optional[Action]:
		"""Called when the user selects a valid item."""
		raise NotImplementedError()

class InventoryActivateHandler(InventoryEventHandler):
	"""Handle using an inventory item."""

	TITLE = "Select an item to use"

	def on_item_selected(self, item: Item) -> Optional[ActionOrHandler]:
		"""Return the action for the selected item."""
		return item.consumable.get_action(self.engine.player)

class InventoryDropHandler(InventoryEventHandler):
	"""Handle dropping an inventory item."""

	TITLE = "Select an item to drop"

	def on_item_selected(self, item: Item) -> Optional[ActionOrHandler]:
		"""Drop this item."""
		return actions.DropItem(self.engine.player, item)

class SelectIndexHandler(AskUserEventHandler):
	"""Handles asking the user for an index on the map."""

	def __init__(self, engine: Engine):
		"""Sets the cursor to the player when this handler is constructed."""
		super().__init__(engine)
		player = self.engine.player
		engine.mouse_location = player.x, player.y

	def on_render(self, console: tcod.Console) -> None:
			"""Highlight the tile under the cursor"""
			super().on_render(console)
			x, y = self.engine.mouse_location
			console.rgb["bg"][x, y] = color.white
			console.rgb["fg"][x, y] = color.black

	def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[ActionOrHandler]:
		"""Check for key movement on confirmation keys"""
		key = event.sym
		if key in MOVE_KEYS:
			modifier = 1 # holding modifier keys will speed up key movement
			if event.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT):
				modifier *= 5
			if event.mod & (tcod.event.Modifier.LCTRL | tcod.event.Modifier.RCTRL):
				modifier *= 10
			if event.mod & (tcod.event.Modifier.LALT | tcod.event.Modifier.RALT):
				modifier *= 20
    
			x, y = self.engine.mouse_location
			dx, dy = MOVE_KEYS[key]
			x += dx * modifier
			y += dy * modifier
			# clamp the cursor index to map size
			x = max(0, min(x, self.engine.game_map.width - 1))
			y = max(0, min(y, self.engine.game_map.height - 1))
			self.engine.mouse_location = x, y
			return None
		elif key in CONFIRM_KEYS:
			return self.on_index_selected(*self.engine.mouse_location)
		return super().ev_keydown(event)

	def ev_mousebuttondown(
		self, event: tcod.event.MouseButtonDown
	) -> Optional[ActionOrHandler]:
		"""Left click confirms selection."""
		if self.engine.game_map.in_bounds(*event.title):
			if event.button == 1:
				return self.on_index_selected(*event.title)
		return super().ev_mousebuttondown(event)

	def on_index_selected(self, x: int, y: int) -> Optional[ActionOrHandler]:
		"""Called when an index is selected."""
		raise NotImplementedError()

class LookHandler(SelectIndexHandler):
	"""Lets the player look around using the keyboard."""
	def on_index_selected(self, x: int, y: int) -> MainGameEventHandler:
		"""Return to main handler"""
		return MainGameEventHandler(self.engine)

class SingleRangedAttackHandler(SelectIndexHandler):
	"""Handles targeting a single enemy."""
	def __init__(
		self, engine: Engine, callback: Callable[[Tuple[int, int]], Optional[Action]]
	):
		super().__init__(engine)

		self.callback = callback

	def on_index_selected(self, x: int, y: int) -> Optional[Action]:
		return self.callback((x, y))

class AreaRangedAttackHandler(SelectIndexHandler):
	"""Handles targeting an area with a given radius."""

	def __init__(
		self,
		engine: Engine,
		radius: int,
		callback: Callable[[Tuple[int, int]], Optional[Action]],
	):
		super().__init__(engine)

		self.radius = radius
		self.callback = callback

	def on_render(self, console: tcod.Console) -> None:
		"""Highlight the tile under the cursor."""
		super().on_render(console)

		x, y = self.engine.mouse_location

		# Draw a rectangle around the targeted area
		console.draw_frame(
			x=x - self.radius - 1,
			y=y - self.radius - 1,
			width=self.radius ** 2,
			height=self.radius ** 2,
			fg=color.red,
			clear=False,
		)

	def on_index_selected(self, x: int, y: int) -> Optional[Action]:
		return self.callback((x, y))

class MainGameEventHandler(EventHandler):
	def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[ActionOrHandler]:
		action: Optional[Action] = None

		key = event.sym
		modifier = event.mod

		player = self.engine.player

		if key == tcod.event.KeySym.PERIOD and modifier & (
			tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT
		):
			return actions.TakeStairsAction(player)

		if key in MOVE_KEYS:
			dx, dy = MOVE_KEYS[key]
			action = BumpAction(player, dx, dy)
		elif key in WAIT_KEYS:
			action = WaitAction(player)

		elif key == tcod.event.KeySym.ESCAPE:
			raise SystemExit()
		elif key == tcod.event.KeySym.V:
			return HistoryViewer(self.engine)

		elif key == tcod.event.KeySym.G:
			action = PickupAction(player)

		elif key == tcod.event.KeySym.I:
			return InventoryActivateHandler(self.engine)
		elif key == tcod.event.KeySym.D:
			return InventoryDropHandler(self.engine)
		elif key == tcod.event.KeySym.SLASH:
			return LookHandler(self.engine)

		return action

class GameOverEventHandler(EventHandler):
	def on_quit(self) -> None:
		"""Handle exiting out of a finished game"""
		if os.path.exists("savegame.sav"):
			os.remove("savegame.sav")
		raise exceptions.QuitWithoutSaving()

	def ev_quit(self, event: tcod.event.Quit) -> None:
		self.on_quit()

	def ev_keydown(self, event: tcod.event.KeyDown) -> None:
		if event.sym == tcod.event.KeySym.ESCAPE:
			self.on_quit()

class HistoryViewer(EventHandler):
	"""Print the history on a larger window."""

	def __init__(self, engine: Engine):
		super().__init__(engine)
		self.log_length = len(engine.message_log.messages)
		self.cursor = self.log_length - 1

	def on_render(self, console: tcod.Console) -> None:
		super().on_render(console)

		log_console = tcod.console.Console(console.width - 6, console.height - 6)

		# Draw a frame with a custom title banner
		log_console.draw_frame(0, 0, log_console.width, log_console.height)
		log_console.print(
			x=0, y=0, width=log_console.width, height=1, string="┤Message history├", alignment=libtcodpy.CENTER
		)

		# Render the message log using the cursor
		self.engine.message_log.render_messages(
			log_console,
			1,
			1,
			log_console.width - 2,
			log_console.height -2,
			self.engine.message_log.messages[: self.cursor + 1],
		)
		log_console.blit(console, 3, 3)

	def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[MainGameEventHandler]:
		if event.sym in CURSOR_Y_KEYS:
			adjust = CURSOR_Y_KEYS[event.sym]
			if adjust < 0 and self.cursor == 0:
				self.cursor = self.log_length - 1
			elif adjust > 0 and self.cursor == self.log_length - 1:
				self.cursor = 0
			else:
				self.cursor = max(0, min(self.cursor + adjust, self.log_length - 1))
		elif event.sym == tcod.event.KeySym.HOME:
			self.cursor = 0
		elif event.sym == tcod.event.KeySym.END:
			self.cursor = self.log_length - 1
		else:
			return MainGameEventHandler(self.engine)
		return None
