"""All user-facing Spanish text, centralized.

Per AGENTS.md §3 / DESIGN.md §5.4, this is the ONLY place UI strings live.
Never inline a user-facing literal inside a view file — reference a key here
so the English/Spanish boundary stays unambiguous.
"""

from __future__ import annotations

APP_TITLE = "Caja Chica"

APP_SUBTITLE = "Registro de ventas, stock, gastos y caja"

USER_PICKER_TITLE = "Quién está trabajando ahora?"
USER_PICKER_PROMPT = "Selecciona tu nombre para continuar"
USER_PICKER_NO_USERS = "Aún no hay usuarios registrados."
USER_PICKER_CREATE_LABEL = "Crear un nuevo usuario"
USER_PICKER_CREATE_HINT = "Nombre del usuario nuevo"
USER_PICKER_CREATE_BUTTON = "Crear"
USER_PICKER_SELECT_BUTTON = "Seleccionar"
USER_REQUIRED_ERROR = "Escribe un nombre antes de crear el usuario."

MAIN_WELCOME = "Bienvenido"
BALANCE_LABEL = "Disponible total"
BALANCE_CASH_LABEL = "Efectivo"
BALANCE_QR_LABEL = "QR"
CURRENT_USER_LABEL = "Usuario actual"
