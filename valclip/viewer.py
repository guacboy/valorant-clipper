"""Popup window that plays each new montage on a chosen monitor without stealing focus."""

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget


class MontageSignals(QObject):
    ready = Signal(str)


class Viewer(QVideoWidget):
    def __init__(self, monitor: int) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        screens = QGuiApplication.screens()
        screen = screens[monitor] if monitor < len(screens) else screens[-1]
        self.setGeometry(screen.geometry())

        self._audio = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self)
        self._player.mediaStatusChanged.connect(self._on_status)

    def play(self, path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        self.show()
        self._player.play()

    def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.hide()

    def mousePressEvent(self, event) -> None:
        self._player.stop()
        self.hide()
