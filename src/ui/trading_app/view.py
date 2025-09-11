"""Minimal passive view for the trading UI (headless-safe)."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any


class MainWindow:
    def __init__(self) -> None:
        # Callbacks provided by presenter
        self.on_add: Callable[[str], None] | None = None
        self.on_remove_selected: Callable[[list[str]], None] | None = None
        self.on_refresh: Callable[[], None] | None = None

        # Try to build a real Qt window
        self._qt: Any | None = None
        self._win: Any | None = None
        self._widgets: dict[str, Any] = {}
        try:
            qtw = importlib.import_module("PyQt6.QtWidgets")  # type: ignore
            self._qt = qtw
            self._win = qtw.QMainWindow()  # type: ignore[assignment]
            if self._win is not None:
                self._win.setWindowTitle("Trading GUI - Level 2")

            # Widgets
            symbol_input = qtw.QLineEdit()
            add_btn = qtw.QPushButton("Add")
            remove_btn = qtw.QPushButton("Remove Selected")
            refresh_btn = qtw.QPushButton("Refresh")
            active_list = qtw.QListWidget()
            status = qtw.QStatusBar()

            # Layout
            top = qtw.QWidget()
            vbox = qtw.QVBoxLayout(top)
            hbox = qtw.QHBoxLayout()
            hbox.addWidget(qtw.QLabel("Symbol:"))
            hbox.addWidget(symbol_input)
            hbox.addWidget(add_btn)
            hbox.addWidget(remove_btn)
            hbox.addWidget(refresh_btn)
            vbox.addLayout(hbox)
            vbox.addWidget(qtw.QLabel("Active Level 2 Streams:"))
            vbox.addWidget(active_list)
            self._win.setCentralWidget(top)  # type: ignore[union-attr]
            self._win.setStatusBar(status)  # type: ignore[union-attr]

            # Store refs
            self._widgets = {
                "symbol_input": symbol_input,
                "add_btn": add_btn,
                "remove_btn": remove_btn,
                "refresh_btn": refresh_btn,
                "active_list": active_list,
                "status": status,
            }

            # Wire up
            add_btn.clicked.connect(self._handle_add)  # type: ignore[attr-defined]
            remove_btn.clicked.connect(self._handle_remove)  # type: ignore[attr-defined]
            refresh_btn.clicked.connect(self._handle_refresh)  # type: ignore[attr-defined]
        except Exception:
            # Headless mode: no real window
            self._qt = None
            self._win = None
            self._widgets = {
                "symbol_input": None,
                "add_btn": None,
                "remove_btn": None,
                "refresh_btn": None,
                "active_list": None,
                "status": None,
            }

    # --- Internal utility to keep type checkers happy
    def _invoke_add_cb(self, cb: Callable[[str], None], sym: str) -> None:
        cb(sym)

    def _invoke_remove_cb(
        self, cb: Callable[[list[str]], None], syms: list[str]
    ) -> None:
        cb(syms)

    def _invoke_refresh_cb(self, cb: Callable[[], None]) -> None:
        cb()

    # Public methods used by presenter/app
    def show(self) -> None:
        try:
            if self._win:
                self._win.show()  # type: ignore[attr-defined]
        except Exception:
            pass

    def set_active(self, symbols: list[str]) -> None:
        lst = self._widgets.get("active_list")
        try:
            if lst is not None:
                lst.clear()  # type: ignore[attr-defined]
                for s in symbols:
                    lst.addItem(s)  # type: ignore[attr-defined]
        except Exception:
            pass

    def set_status(self, text: str) -> None:
        status = self._widgets.get("status")
        try:
            if status is not None:
                status.showMessage(text, 3000)  # type: ignore[attr-defined]
        except Exception:
            pass

    # Internal handlers (trigger callbacks)
    def _handle_add(self) -> None:
        sym: str = ""
        try:
            inp: Any = self._widgets.get("symbol_input")
            if inp is not None:
                sym = str(inp.text()).strip().upper()  # type: ignore[attr-defined]
        except Exception:
            sym = ""
        if not sym:
            self.set_status("Enter a symbol")
            return
        cb = self.on_add
        if cb is None:
            return
        try:
            self._invoke_add_cb(cb, sym)
        except Exception:
            pass

    def _handle_remove(self) -> None:
        syms: list[str] = []
        try:
            lst: Any = self._widgets.get("active_list")
            if lst is not None:
                items = lst.selectedItems()  # type: ignore[attr-defined]
                syms = [str(i.text()) for i in items]  # type: ignore[attr-defined]
        except Exception:
            syms = []
        if not syms:
            self.set_status("Select a stream to remove")
            return
        cb = self.on_remove_selected
        if cb is None:
            return
        try:
            self._invoke_remove_cb(cb, syms)
        except Exception:
            pass

    def _handle_refresh(self) -> None:
        cb = self.on_refresh
        if cb is None:
            return
        try:
            self._invoke_refresh_cb(cb)
        except Exception:
            pass
