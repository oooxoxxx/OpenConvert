"""引擎模組下載對話框：需要什麼下載什麼。"""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from ...core import modules
from ...core.errors import ConversionCancelled, OpenConvertError


class ModuleInstallThread(QThread):
    progress = Signal(float, str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, module_id: str, parent=None) -> None:
        super().__init__(parent)
        self._module_id = module_id
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            path = modules.install(
                self._module_id,
                progress=lambda fraction, message: self.progress.emit(fraction, message),
                cancelled=self._cancel.is_set,
            )
            modules.write_notices(modules.target_base())
            self.succeeded.emit(str(path))
        except ConversionCancelled:
            self.failed.emit("已取消。")
        except OpenConvertError as exc:
            self.failed.emit(exc.user_message)


class ModuleInstallDialog(QDialog):
    """詢問並執行單一模組的下載；成功時以 ``accepted()`` 關閉。"""

    def __init__(self, module_id: str, parent=None) -> None:
        super().__init__(parent)
        self._module_id = module_id
        self._thread: ModuleInstallThread | None = None
        self._spec = modules.get_module(module_id)

        self.setWindowTitle("下載引擎模組")
        self.setMinimumWidth(460)
        self._build_ui()

    # ------------------------------------------------------------------ 版面

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(10)

        spec = self._spec
        if spec is None:
            title = QLabel(f"「{self._module_id}」在這個平台上沒有提供。")
            title.setWordWrap(True)
            layout.addWidget(title)
            close = QPushButton("關閉")
            close.setObjectName("Ghost")
            close.clicked.connect(self.reject)
            layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
            return

        size = f"{spec.size / 1e6:.0f} MB" if spec.size else "未知大小"
        header = QLabel(f"{spec.label}")
        header.setObjectName("H2")
        layout.addWidget(header)

        info = QLabel(f"大小：約 {size}\n授權：{spec.license}\n用途：{spec.purpose}\n來源：{spec.url}")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._status = QLabel("尚未下載。所有檔案都以 SHA-256 驗證，不會執行未經驗證的內容。")
        self._status.setObjectName("Muted")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        self._progress.hide()
        layout.addWidget(self._progress)

        buttons = QHBoxLayout()
        self._install_button = QPushButton(f"下載並安裝（約 {size}）")
        self._install_button.setObjectName("Primary")
        self._install_button.clicked.connect(self._start)
        self._cancel_button = QPushButton("取消")
        self._cancel_button.setObjectName("Ghost")
        self._cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self._install_button)
        buttons.addWidget(self._cancel_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------ 動作

    def _start(self) -> None:
        self._install_button.setEnabled(False)
        self._cancel_button.setText("取消下載")
        self._progress.show()
        self._status.setText("連線中…")

        self._thread = ModuleInstallThread(self._module_id, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.succeeded.connect(self._on_success)
        self._thread.failed.connect(self._on_failure)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_progress(self, fraction: float, message: str) -> None:
        self._progress.setValue(int(fraction * 1000))
        self._status.setText(message)

    def _on_success(self, path: str) -> None:
        self._status.setText(f"已安裝到 {path}")
        self.accept()

    def _on_failure(self, message: str) -> None:
        self._progress.hide()
        self._status.setText(message)
        self._install_button.setEnabled(True)
        self._cancel_button.setText("關閉")
        self._thread = None
