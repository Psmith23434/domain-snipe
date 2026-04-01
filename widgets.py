# widgets.py
from PyQt5.QtWidgets import QTableWidget, QHeaderView, QAbstractItemView, QFrame, QLabel
from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtGui import QFont


class DraggableTable(QTableWidget):
    row_moved = pyqtSignal()

    def __init__(self, rows, cols, parent=None):
        super().__init__(rows, cols, parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.row_moved.emit()


class Signals(QObject):
    status_update        = pyqtSignal(str, str)
    success              = pyqtSignal(str, dict)
    failure              = pyqtSignal(str, str)
    whois_result         = pyqtSignal(str, str)
    premium_detect       = pyqtSignal(str, float, str)
    next_check           = pyqtSignal(str, float, str)
    price_update         = pyqtSignal(str, str)
    premium_check_result = pyqtSignal(str, dict)


def _divider():
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color:#334155;")
    return f


def _section_label(text):
    label = QLabel(text)
    label.setFont(QFont("Arial", 10, QFont.Bold))
    label.setContentsMargins(0, 8, 0, 4)
    return label