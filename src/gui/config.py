from typing import Optional, cast

import webcolors
from aqt.qt import *
from aqt.utils import askUser, showInfo

from ..config import CustomFlag, config
from ..consts import consts
from ..forms.config import Ui_Dialog
from ..gui.dialog import Dialog


def qcolor_to_hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


def color_string_to_qcolor(color: str) -> QColor:
    c = webcolors.html5_parse_legacy_color(color)
    qcolor = QColor(c.red, c.green, c.blue)

    return qcolor


class FlagColorButton(QPushButton):
    color_changed = pyqtSignal()

    def __init__(self, parent: QWidget, color: str = ""):
        super().__init__(parent)
        self.color = color_string_to_qcolor(color)
        self.setFlat(True)
        qconnect(self.clicked, self.on_clicked)
        self.update_color()

    def update_color(self) -> None:
        self.setStyleSheet(
            "FlagColorButton { background-color: %s }" % qcolor_to_hex(self.color)
        )

    def on_clicked(self) -> None:
        new_color = QColorDialog.getColor(
            self.color, self, f"{consts.name} - Select Color"
        )
        if new_color.isValid():
            self.color = new_color
            self.color_changed.emit()
        self.update_color()


class FlagShortcutWidget(QWidget):
    keySequenceChanged = pyqtSignal()

    def __init__(self, parent: QWidget, shortcut: Optional[str] = None) -> None:
        super().__init__(parent)
        self.shortcut = shortcut
        self.setup_ui()

    def setup_ui(self) -> None:
        hbox = QHBoxLayout()
        self.sequence_edit = sequence_edit = QKeySequenceEdit(self)
        if self.shortcut:
            sequence_edit.setKeySequence(QKeySequence(self.shortcut))
        qconnect(
            sequence_edit.keySequenceChanged, lambda _: self.keySequenceChanged.emit()
        )
        hbox.addWidget(sequence_edit)
        clear_button = QPushButton(self)
        clear_button.setIcon(QIcon(str(consts.dir / "icons" / "x.svg")))
        clear_button.setMaximumSize(16, 16)
        qconnect(clear_button.clicked, sequence_edit.clear)
        hbox.addWidget(clear_button)
        hbox.setContentsMargins(2, 0, 2, 0)
        self.setLayout(hbox)

    def keySequence(self) -> QKeySequence:
        return self.sequence_edit.keySequence()


class FlagListWidget(QTableWidget):
    HEADER_LABELS = ["Label", "Light Color", "Dark Color", "Shortcut"]

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setColumnCount(len(self.HEADER_LABELS))
        self.setHorizontalHeaderLabels(self.HEADER_LABELS)
        self.setRowCount(len(config.flags))
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setStyleSheet(
            """
QTableView {
    border: none;
    border-collapse: collapse;
}

QTableView::item {
    border: none;
    padding: 2px;
}
"""
        )
        for i, flag in enumerate(config.flags):
            self.new_flag(i, flag)

    def new_flag(self, i: int, flag: CustomFlag) -> None:
        label_item = QTableWidgetItem(flag.label)
        self.setItem(i, 0, label_item)

        light_color_widget = FlagColorButton(self, flag.color_light)
        light_color_item = QTableWidgetItem()
        light_color_item.setFlags(
            light_color_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        self.setItem(i, 1, light_color_item)
        qconnect(
            light_color_widget.color_changed,
            lambda: self.itemChanged.emit(None),
        )
        self.setCellWidget(i, 1, light_color_widget)

        dark_color_widget = FlagColorButton(self, flag.color_dark)
        dark_color_item = QTableWidgetItem()
        dark_color_item.setFlags(dark_color_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(i, 2, dark_color_item)
        qconnect(
            dark_color_widget.color_changed,
            lambda: self.itemChanged.emit(None),
        )
        self.setCellWidget(i, 2, dark_color_widget)

        shortcut_widget = FlagShortcutWidget(self, flag.shortcut)
        shortcut_item = QTableWidgetItem()
        shortcut_item.setFlags(shortcut_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(i, 2, shortcut_item)
        qconnect(
            shortcut_widget.keySequenceChanged,
            lambda: self.itemChanged.emit(None),
        )
        self.setCellWidget(i, 3, shortcut_widget)
        self.setRowHeight(i, 40)


class ConfigDialog(Dialog):
    def __init__(self, parent: QWidget):
        self.dirty = False
        super().__init__(parent)

    def setup_ui(self) -> None:
        self.form = Ui_Dialog()
        self.form.setupUi(self)
        self.setWindowTitle(f"{consts.name} - Config")
        self.setMinimumSize(600, 500)
        self.setContentsMargins(0, 0, 0, 0)
        self.flag_list = FlagListWidget(self)
        self.form.flag_list_container.addWidget(self.flag_list)
        self.form.show_flag_labels.setChecked(config["show_flag_labels"])
        qconnect(self.form.save_button.clicked, self.on_save)
        qconnect(self.form.new_button.clicked, self.on_new)
        qconnect(self.form.delete_button.clicked, self.on_delete)
        qconnect(self.flag_list.itemChanged, self.on_item_changed)
        super().setup_ui()

    def on_item_changed(self, item: Optional[QTableWidgetItem] = None) -> None:
        self.dirty = True

    def save(self) -> None:
        new_flags = []
        for i in range(self.flag_list.rowCount()):
            label = self.flag_list.item(i, 0).text()
            color_light_widget = cast(FlagColorButton, self.flag_list.cellWidget(i, 1))
            color_light = qcolor_to_hex(color_light_widget.color)
            color_dark_widget = cast(FlagColorButton, self.flag_list.cellWidget(i, 2))
            color_dark = qcolor_to_hex(color_dark_widget.color)
            shortcut_widget = cast(FlagShortcutWidget, self.flag_list.cellWidget(i, 3))
            shortcut = shortcut_widget.keySequence().toString()

            new_flags.append(CustomFlag(label, color_light, color_dark, shortcut))

        config.flags = new_flags
        config["show_flag_labels"] = self.form.show_flag_labels.isChecked()
        showInfo(
            "Changes will take effect when you restart Anki.", self, title=consts.name
        )

    def on_save(self) -> None:
        self.save()
        self.accept()

    def on_new(self) -> None:
        self.flag_list.insertRow(self.flag_list.rowCount())
        self.flag_list.new_flag(
            self.flag_list.rowCount() - 1, CustomFlag("My Flag", "#ffd800", "#ffee75")
        )
        self.dirty = True

    def on_delete(self) -> None:
        if self.flag_list.selectedIndexes():
            last_index = self.flag_list.selectedIndexes()[-1]
            self.flag_list.removeRow(last_index.row())
            self.dirty = True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.dirty:
            if askUser("Save changes?", self, title=consts.name):
                self.save()
        return super().closeEvent(event)
