from __future__ import annotations

import json
from typing import Any

from PyQt5 import QtGui, QtWidgets

from src.core.configuration.services import (
    diff_dict,
    load_config,
    save_config,
    validate_config,
)

FILES = ["config.json", "ib_gateway_config.json", "symbol_mapping.json"]


class ConfigEditor(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Trading Config Editor")
        self.resize(1000, 700)

        # Widgets
        self.file_combo = QtWidgets.QComboBox()
        self.file_combo.addItems(FILES)
        self.load_btn = QtWidgets.QPushButton("Load")
        self.validate_btn = QtWidgets.QPushButton("Validate")
        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.setEnabled(False)

        self.json_edit = QtWidgets.QPlainTextEdit()
        font = QtGui.QFont("Monospace")
        self.json_edit.setFont(font)
        self.json_edit.textChanged.connect(self._on_text_changed)

        self.errors_view = QtWidgets.QTextEdit()
        self.errors_view.setReadOnly(True)
        self.diff_view = QtWidgets.QTextEdit()
        self.diff_view.setReadOnly(True)

        # Layout
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("File:"))
        top.addWidget(self.file_combo)
        top.addWidget(self.load_btn)
        top.addStretch(1)
        top.addWidget(self.validate_btn)
        top.addWidget(self.save_btn)

        split = QtWidgets.QSplitter()
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.addWidget(QtWidgets.QLabel("JSON:"))
        left_layout.addWidget(self.json_edit)
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.addWidget(QtWidgets.QLabel("Validation Errors:"))
        right_layout.addWidget(self.errors_view)
        right_layout.addWidget(QtWidgets.QLabel("Diff (current -> edited):"))
        right_layout.addWidget(self.diff_view)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([600, 400])

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(split)

        # Signals
        self.load_btn.clicked.connect(self.load_current)
        self.validate_btn.clicked.connect(self.validate_current)
        self.save_btn.clicked.connect(self.save_current)

        # State
        self._current_data: dict[str, Any] | None = None

        # Initial load
        self.load_current()

    def current_filename(self) -> str:
        return str(self.file_combo.currentText())

    def load_current(self) -> None:
        filename = self.current_filename()
        try:
            data = load_config(filename)
            self._current_data = data
            self.json_edit.blockSignals(True)
            self.json_edit.setPlainText(json.dumps(data, indent=2, sort_keys=True))
            self.json_edit.blockSignals(False)
            self.errors_view.clear()
            self.diff_view.clear()
            self.save_btn.setEnabled(False)
        except Exception as ex:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Load Error", str(ex))

    def _edited_data(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.json_edit.toPlainText())
        except Exception:  # noqa: BLE001
            return None

    def _on_text_changed(self) -> None:
        # Enable save only if JSON parses and differs from loaded data
        edited = self._edited_data()
        if edited is None or self._current_data is None:
            self.save_btn.setEnabled(False)
            return
        self.save_btn.setEnabled(edited != self._current_data)
        # Show diff quickly
        d = diff_dict(self._current_data, edited)
        self.diff_view.setPlainText(json.dumps(d, indent=2, sort_keys=True))

    def validate_current(self) -> None:
        filename = self.current_filename()
        edited = self._edited_data()
        if edited is None:
            self.errors_view.setPlainText("Invalid JSON")
            return
        result = validate_config(filename, edited)
        if result.valid:
            self.errors_view.setPlainText("No errors. ✔")
        else:
            self.errors_view.setPlainText("\n".join(result.errors))

    def save_current(self) -> None:
        filename = self.current_filename()
        edited = self._edited_data()
        if edited is None:
            QtWidgets.QMessageBox.warning(self, "Save", "Invalid JSON; cannot save.")
            return
        result = save_config(filename, edited)
        if not result.valid:
            QtWidgets.QMessageBox.warning(
                self, "Validation Failed", "Cannot save due to errors. See right panel."
            )
            self.errors_view.setPlainText("\n".join(result.errors))
            return
        # Refresh state
        self._current_data = edited
        self.save_btn.setEnabled(False)
        QtWidgets.QMessageBox.information(
            self, "Saved", f"Saved {filename} successfully."
        )


def main() -> None:
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = ConfigEditor()
    w.show()
    sys.exit(app.exec_())
