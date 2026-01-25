from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSettings,
    Qt,
    QSortFilterProxyModel,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPainter,
    QPalette,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QProxyStyle,
    QStyleOption,
    QTableView,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Optional deps (graceful)
try:
    import exifread  # type: ignore
except Exception:
    exifread = None

try:
    from PIL import Image  # type: ignore
except Exception:
    Image = None

try:
    from pillow_heif import register_heif_opener  # type: ignore
    register_heif_opener()
except Exception:
    register_heif_opener = None

try:
    import pymediainfo  # type: ignore
except Exception:
    pymediainfo = None

try:
    from exiftool_wrapper import ExifToolWrapper  # type: ignore
except Exception:
    ExifToolWrapper = None


APP_NAME = "EXIFrenameX"
APP_ORG = "TimTools"
APP_SETTINGS = "EXIFrenameX_Final"


# =========================
# Assets
# =========================
def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return str(Path(base) / relative)
    return str(Path(relative))


def app_icon_path() -> str:
    # Assets contain ico + icns
    if sys.platform.startswith("win"):
        return resource_path("assets/EXIFrenameX.ico")
    if sys.platform == "darwin":
        return resource_path("assets/EXIFrenameX.icns")
    return resource_path("assets/EXIFrenameX.ico")


# =========================
# Console + In-Memory Log
# =========================
class LogBuffer:
    def __init__(self, max_lines: int = 5000) -> None:
        self._max = max_lines
        self._lines: List[str] = []
        self._lock = threading.Lock()

    def write(self, msg: str) -> None:
        msg = msg.rstrip("\n")
        if not msg:
            return
        with self._lock:
            self._lines.append(msg)
            if len(self._lines) > self._max:
                self._lines = self._lines[-self._max :]

    def dump(self) -> str:
        with self._lock:
            return "\n".join(self._lines)


LOG = LogBuffer()


def log(msg: str) -> None:
    print(msg)
    LOG.write(msg)


# =========================
# Date parsing helpers
# =========================
EXIFTOOL_DATE_TAGS = [
    "EXIF:DateTimeOriginal",
    "EXIF:CreateDate",
    "XMP:CreateDate",
    "XMP:DateCreated",
    "QuickTime:CreateDate",
    "QuickTime:MediaCreateDate",
    "QuickTime:TrackCreateDate",
    "QuickTime:ModifyDate",
    "QuickTime:ContentCreateDate",
    "File:FileModifyDate",
    "File:FileCreateDate",
    "Composite:SubSecDateTimeOriginal",
    "Composite:DateTimeCreated",
    "PNG:CreationTime",
]

DATE_FORMATS = (
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y:%m:%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
)


def _to_local_naive(dt: _dt.datetime) -> _dt.datetime:
    if dt.tzinfo is not None:
        try:
            dt = dt.astimezone()
        except Exception:
            pass
        dt = dt.replace(tzinfo=None)
    return dt


def parse_datetime_any(s: str) -> Optional[_dt.datetime]:
    s = (s or "").strip()
    if not s:
        return None

    s_clean = re.sub(r"\s+", " ", s)
    for fmt in DATE_FORMATS:
        try:
            return _to_local_naive(_dt.datetime.strptime(s_clean, fmt))
        except Exception:
            continue

    s_no_tz = re.sub(r"([+-]\d{2}:?\d{2}|Z)$", "", s_clean).strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return _dt.datetime.strptime(s_no_tz, fmt)
        except Exception:
            continue
    return None


FILENAME_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("IMG_VID_YYYYMMDD_HHMMSS", re.compile(r"\b(?:IMG|VID)[-_]?(\d{8})[_-](\d{6})\b", re.IGNORECASE)),
    ("YYYY-MM-DD_HH-MM-SS", re.compile(r"\b(\d{4})[-_](\d{2})[-_](\d{2})[ _-](\d{2})[-_](\d{2})[-_](\d{2})\b")),
    ("WHATSAPP_IMG_YYYYMMDD", re.compile(r"\bIMG-(\d{8})-WA\d+\b", re.IGNORECASE)),
    ("DJI_YYYYMMDD_HHMMSS", re.compile(r"\bDJI[_-](\d{8})[_-](\d{6})\b", re.IGNORECASE)),
]


def parse_date_from_filename(name: str) -> Optional[_dt.datetime]:
    base = Path(name).stem
    for key, rx in FILENAME_PATTERNS:
        m = rx.search(base)
        if not m:
            continue
        try:
            if key in {"IMG_VID_YYYYMMDD_HHMMSS", "DJI_YYYYMMDD_HHMMSS"}:
                ymd, hms = m.group(1), m.group(2)
                return _dt.datetime.strptime(ymd + hms, "%Y%m%d%H%M%S")
            if key == "YYYY-MM-DD_HH-MM-SS":
                y, mo, d, hh, mm, ss = m.groups()
                return _dt.datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss))
            if key == "WHATSAPP_IMG_YYYYMMDD":
                ymd = m.group(1)
                return _dt.datetime.strptime(ymd, "%Y%m%d")
        except Exception:
            continue
    return None


def sidecar_xmp_path(p: Path) -> Path:
    cand = p.with_suffix(p.suffix + ".xmp")
    if cand.exists():
        return cand
    return p.with_suffix(".xmp")


def takeout_json_sidecar(p: Path) -> Optional[Path]:
    cand = p.with_suffix(p.suffix + ".json")
    return cand if cand.exists() else None


def parse_xmp_for_date(xmp_text: str) -> Optional[_dt.datetime]:
    for rx in (
        re.compile(r'xmp:CreateDate="([^"]+)"', re.IGNORECASE),
        re.compile(r"<xmp:CreateDate>\s*([^<]+)\s*</xmp:CreateDate>", re.IGNORECASE),
        re.compile(r"<photoshop:DateCreated>\s*([^<]+)\s*</photoshop:DateCreated>", re.IGNORECASE),
    ):
        m = rx.search(xmp_text)
        if m:
            dt = parse_datetime_any(m.group(1))
            if dt:
                return dt
    return None


def parse_takeout_json_for_date(obj: Any) -> Optional[_dt.datetime]:
    try:
        for key in ("photoTakenTime", "creationTime", "modificationTime"):
            node = obj.get(key)
            if isinstance(node, dict):
                ts = node.get("timestamp")
                if ts:
                    return _dt.datetime.fromtimestamp(int(ts))
        if "timestamp" in obj:
            return _dt.datetime.fromtimestamp(int(obj["timestamp"]))
    except Exception:
        pass
    return None


# =========================
# Metadata Reader
# =========================
class FallbackMode(str):
    OFF = "OFF (skip if missing)"
    FS_CREATED = "File created time"
    FS_MODIFIED = "File modified time"


@dataclass(frozen=True)
class DeepOptions:
    parse_filename: bool = True
    read_xmp_sidecar: bool = True
    read_takeout_json: bool = True


@dataclass(frozen=True)
class ReadOptions:
    deep: DeepOptions
    fallback: str


class ExifToolSession:
    def __init__(self) -> None:
        self._wrapper = None
        self._cli_ok = False

        if ExifToolWrapper is not None:
            try:
                self._wrapper = ExifToolWrapper()
            except Exception:
                self._wrapper = None

        if self._wrapper is None:
            self._cli_ok = self._detect_exiftool_cli()

    def _detect_exiftool_cli(self) -> bool:
        try:
            p = subprocess.run(["exiftool", "-ver"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return p.returncode == 0
        except Exception:
            return False

    def __enter__(self) -> "ExifToolSession":
        if self._wrapper is not None:
            try:
                self._wrapper.__enter__()
            except Exception:
                self._wrapper = None
                self._cli_ok = self._detect_exiftool_cli()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._wrapper is not None:
            try:
                self._wrapper.__exit__(exc_type, exc, tb)
            except Exception:
                pass

    def available(self) -> bool:
        return self._wrapper is not None or self._cli_ok

    def metadata(self, file_path: str) -> Dict[str, Any]:
        if self._wrapper is not None:
            try:
                return dict(self._wrapper.get_metadata(file_path) or {})
            except Exception:
                return {}
        if self._cli_ok:
            return self._cli_metadata(file_path)
        return {}

    def _cli_metadata(self, file_path: str) -> Dict[str, Any]:
        try:
            p = subprocess.run(
                ["exiftool", "-j", "-G", "-s", "-n", file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if p.returncode != 0:
                return {}
            arr = json.loads(p.stdout)
            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                return arr[0]
        except Exception:
            return {}
        return {}


class MetadataReader:
    IMAGE_EXTS = {
        ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif",
        ".heic", ".heif",
        ".arw", ".nef", ".cr2", ".dng", ".rw2", ".orf", ".srw",
    }
    VIDEO_EXTS = {
        ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".wmv", ".webm", ".3gp", ".mts", ".m2ts", ".mpg", ".mpeg",
    }

    def __init__(self, options: ReadOptions) -> None:
        self.options = options

    def _fs_created(self, p: Path) -> _dt.datetime:
        st = p.stat()
        if hasattr(st, "st_birthtime"):
            try:
                return _dt.datetime.fromtimestamp(st.st_birthtime)
            except Exception:
                pass
        return _dt.datetime.fromtimestamp(st.st_ctime)

    def _fs_modified(self, p: Path) -> _dt.datetime:
        return _dt.datetime.fromtimestamp(p.stat().st_mtime)

    def _fallback(self, p: Path) -> Optional[_dt.datetime]:
        if self.options.fallback == FallbackMode.FS_CREATED:
            return self._fs_created(p)
        if self.options.fallback == FallbackMode.FS_MODIFIED:
            return self._fs_modified(p)
        return None

    def _exifread_dt(self, p: Path) -> Optional[_dt.datetime]:
        if exifread is None:
            return None
        try:
            with p.open("rb") as f:
                tags = exifread.process_file(f, details=False)
            for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
                v = tags.get(key)
                if v:
                    dt = parse_datetime_any(str(v))
                    if dt:
                        return dt
        except Exception:
            return None
        return None

    def _heic_pillow_xmp(self, p: Path) -> Optional[_dt.datetime]:
        if Image is None:
            return None
        try:
            with Image.open(str(p)) as img:
                xmp = img.info.get("xmp")
                if xmp:
                    if isinstance(xmp, bytes):
                        xmp = xmp.decode("utf-8", errors="ignore")
                    dt = parse_xmp_for_date(str(xmp))
                    if dt:
                        return dt
        except Exception:
            return None
        return None

    def _mediainfo_dt(self, p: Path) -> Optional[_dt.datetime]:
        if pymediainfo is None:
            return None
        try:
            mi = pymediainfo.MediaInfo.parse(str(p))
            for track in mi.tracks:
                data = track.to_data() or {}
                for k in (
                    "comapplequicktimecreationdate",
                    "recorded_date",
                    "encoded_date",
                    "tagged_date",
                    "file_created_date",
                    "file_modified_date",
                ):
                    v = data.get(k)
                    if v:
                        s = str(v).replace("T", " ")
                        s = s.split("+")[0].strip()
                        dt = parse_datetime_any(s)
                        if dt:
                            return dt
        except Exception:
            return None
        return None

    def _deep_filename_dt(self, p: Path) -> Optional[_dt.datetime]:
        if not self.options.deep.parse_filename:
            return None
        return parse_date_from_filename(p.name)

    def _deep_xmp_sidecar_dt(self, p: Path) -> Optional[_dt.datetime]:
        if not self.options.deep.read_xmp_sidecar:
            return None
        xp = sidecar_xmp_path(p)
        if xp.exists():
            try:
                txt = xp.read_text(encoding="utf-8", errors="ignore")
                return parse_xmp_for_date(txt)
            except Exception:
                return None
        return None

    def _deep_takeout_json_dt(self, p: Path) -> Optional[_dt.datetime]:
        if not self.options.deep.read_takeout_json:
            return None
        jp = takeout_json_sidecar(p)
        if jp and jp.exists():
            try:
                obj = json.loads(jp.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(obj, dict):
                    return parse_takeout_json_for_date(obj)
            except Exception:
                return None
        return None

    def best_datetime(self, p: Path, exiftool: Optional[ExifToolSession]) -> Tuple[Optional[_dt.datetime], str]:
        # 1) ExifTool FIRST if available (Windows/macOS)
        if exiftool is not None and exiftool.available():
            md = exiftool.metadata(str(p))
            for tag in EXIFTOOL_DATE_TAGS:
                if tag in md:
                    dt = parse_datetime_any(str(md[tag]))
                    if dt:
                        return dt, f"exiftool:{tag}"
            for tag in ("DateTimeOriginal", "CreateDate", "MediaCreateDate"):
                if tag in md:
                    dt = parse_datetime_any(str(md[tag]))
                    if dt:
                        return dt, f"exiftool:{tag}"

        # 2) Takeout JSON
        dt = self._deep_takeout_json_dt(p)
        if dt:
            return dt, "takeout_json"

        # 3) XMP sidecar
        dt = self._deep_xmp_sidecar_dt(p)
        if dt:
            return dt, "xmp_sidecar"

        # 4) EXIF (classic images)
        ext = p.suffix.lower()
        if ext in self.IMAGE_EXTS:
            dt = self._exifread_dt(p)
            if dt:
                return dt, "exifread"

        # 5) HEIC embedded XMP
        if ext in {".heic", ".heif"}:
            dt = self._heic_pillow_xmp(p)
            if dt:
                return dt, "heic_xmp"

        # 6) MediaInfo (videos)
        if ext in self.VIDEO_EXTS:
            dt = self._mediainfo_dt(p)
            if dt:
                return dt, "mediainfo"

        # 7) Filename parse
        dt = self._deep_filename_dt(p)
        if dt:
            return dt, "filename"

        # 8) Fallback
        dt = self._fallback(p)
        if dt:
            if self.options.fallback == FallbackMode.FS_CREATED:
                return dt, "fs_created"
            if self.options.fallback == FallbackMode.FS_MODIFIED:
                return dt, "fs_modified"

        return None, "missing"


# =========================
# Rename core
# =========================
class PatternMode(str):
    DATE_ONLY = "Date only"
    DATE_ORIG = "Date + Original"
    ORIG_ONLY = "Original only"
    ORIG_DATE = "Original + Date"


def format_new_name(
    dt: Optional[_dt.datetime],
    original_name: str,
    fmt: str,
    prefix: str,
    suffix: str,
    pattern: str,
) -> Optional[str]:
    base, ext = os.path.splitext(original_name)
    if pattern == PatternMode.ORIG_ONLY:
        return f"{prefix}{base}{suffix}{ext}"

    if dt is None:
        return None

    stamp = dt.strftime(fmt)
    if pattern == PatternMode.DATE_ONLY:
        return f"{prefix}{stamp}{suffix}{ext}"
    if pattern == PatternMode.DATE_ORIG:
        return f"{prefix}{stamp}_{base}{suffix}{ext}"
    if pattern == PatternMode.ORIG_DATE:
        return f"{prefix}{base}_{stamp}{suffix}{ext}"

    return f"{prefix}{stamp}{suffix}{ext}"


def unique_name_in_folder(folder: Path, filename: str, used: set[str]) -> str:
    if filename not in used and not (folder / filename).exists():
        used.add(filename)
        return filename

    stem, ext = os.path.splitext(filename)
    i = 1
    while True:
        cand = f"{stem}_{i}{ext}"
        if cand not in used and not (folder / cand).exists():
            used.add(cand)
            return cand
        i += 1


@dataclass
class PreviewRow:
    old_name: str
    new_name: str
    dt: Optional[_dt.datetime]
    source: str
    path: Path
    status: str


@dataclass
class RenameResult:
    renamed: int
    skipped: int
    errors: int
    pairs: List[Tuple[Path, Path]]


# =========================
# Table model + filter
# =========================
class PreviewModel(QAbstractTableModel):
    COLS = ["Old name", "New name"]

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[PreviewRow] = []

    def set_rows(self, rows: List[PreviewRow]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else 2

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.COLS[section]
        return str(section + 1)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return r.old_name if index.column() == 0 else r.new_name
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = str(r.path)
            if r.source and r.source != "missing":
                tip += f"\nSource: {r.source}"
            if r.dt:
                tip += f"\nTimestamp: {r.dt.isoformat(sep=' ')}"
            if r.status:
                tip += f"\nStatus: {r.status}"
            return tip
        if role == Qt.ItemDataRole.ForegroundRole:
            if r.status.startswith("ERROR"):
                return QColor(220, 130, 130)
            if r.status.startswith("SKIP"):
                return QColor(170, 170, 170)
            return QColor(235, 235, 235)
        return None


class PreviewFilter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self._needle = ""

    def set_needle(self, text: str) -> None:
        self._needle = (text or "").strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._needle:
            return True
        m = self.sourceModel()
        if m is None:
            return True
        a = str(m.data(m.index(source_row, 0, source_parent), Qt.ItemDataRole.DisplayRole) or "").lower()
        b = str(m.data(m.index(source_row, 1, source_parent), Qt.ItemDataRole.DisplayRole) or "").lower()
        return self._needle in a or self._needle in b


# =========================
# Workers
# =========================
class ScanWorker(QObject):
    finished = pyqtSignal(list, int, int)  # rows, total_files, meta_ok
    failed = pyqtSignal(str)

    def __init__(
        self,
        folder: Path,
        recursive: bool,
        reader: MetadataReader,
        fmt: str,
        prefix: str,
        suffix: str,
        pattern: str,
        cancel_event: threading.Event,
    ):
        super().__init__()
        self.folder = folder
        self.recursive = recursive
        self.reader = reader
        self.fmt = fmt
        self.prefix = prefix
        self.suffix = suffix
        self.pattern = pattern
        self.cancel = cancel_event

    def _iter_files(self) -> Iterable[Path]:
        if not self.recursive:
            for p in self.folder.iterdir():
                if p.is_file():
                    yield p
            return
        for p in self.folder.rglob("*"):
            if p.is_file():
                yield p

    def run(self) -> None:
        try:
            if not self.folder.exists() or not self.folder.is_dir():
                self.failed.emit("Folder does not exist.")
                return

            rows: List[PreviewRow] = []
            total = 0
            meta_ok = 0
            used_names: set[str] = set()

            with ExifToolSession() as exiftool:
                if exiftool.available():
                    log("[scan] ExifTool available -> preferred path")
                else:
                    log("[scan] ExifTool not available -> fallback readers")

                for p in self._iter_files():
                    if self.cancel.is_set():
                        break
                    total += 1

                    dt, src = self.reader.best_datetime(p, exiftool)
                    if dt is not None:
                        meta_ok += 1

                    new = format_new_name(dt, p.name, self.fmt, self.prefix, self.suffix, self.pattern)
                    if new is None:
                        rows.append(PreviewRow(p.name, "(no timestamp)", dt, src, p, "SKIP (missing timestamp)"))
                        continue

                    new_unique = unique_name_in_folder(p.parent, new, used_names)
                    rows.append(PreviewRow(p.name, new_unique, dt, src, p, "OK"))

            self.finished.emit(rows, total, meta_ok)

        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class RenameWorker(QObject):
    finished = pyqtSignal(object)  # RenameResult
    failed = pyqtSignal(str)

    def __init__(self, rows: List[PreviewRow], fmt: str, prefix: str, suffix: str, pattern: str, cancel_event: threading.Event):
        super().__init__()
        self.rows = rows
        self.fmt = fmt
        self.prefix = prefix
        self.suffix = suffix
        self.pattern = pattern
        self.cancel = cancel_event

    def run(self) -> None:
        try:
            pairs: List[Tuple[Path, Path]] = []
            renamed = 0
            skipped = 0
            errors = 0
            used: Dict[Path, set[str]] = {}

            for r in self.rows:
                if self.cancel.is_set():
                    break

                if not r.path.exists():
                    skipped += 1
                    continue

                new = format_new_name(r.dt, r.path.name, self.fmt, self.prefix, self.suffix, self.pattern)
                if new is None:
                    skipped += 1
                    continue

                folder = r.path.parent
                if folder not in used:
                    used[folder] = set()
                new_unique = unique_name_in_folder(folder, new, used[folder])

                src = r.path
                dst = folder / new_unique

                if src.name == dst.name:
                    skipped += 1
                    continue

                try:
                    src.rename(dst)
                    pairs.append((src, dst))
                    renamed += 1
                except Exception:
                    errors += 1

            self.finished.emit(RenameResult(renamed, skipped, errors, pairs))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class UndoWorker(QObject):
    finished = pyqtSignal(int, int)  # undone, errors
    failed = pyqtSignal(str)

    def __init__(self, pairs: List[Tuple[Path, Path]]):
        super().__init__()
        self.pairs = pairs

    def run(self) -> None:
        undone = 0
        errors = 0
        try:
            for src, dst in reversed(self.pairs):
                if dst.exists() and not src.exists():
                    try:
                        dst.rename(src)
                        undone += 1
                    except Exception:
                        errors += 1
                else:
                    errors += 1
            self.finished.emit(undone, errors)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


# =========================
# UI Style
# =========================
class CheckStyle(QProxyStyle):
    """
    Plattform-neutraler Checkbox-Style mit sichtbarem Haken ✓.
    Verhindert "nur farbige Fläche" ohne Tick.
    """

    def drawPrimitive(self, element: QStyle.PrimitiveElement, option: QStyleOption, painter: QPainter, widget=None) -> None:
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            rect = option.rect.adjusted(1, 1, -1, -1)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
            checked = bool(option.state & QStyle.StateFlag.State_On)

            border = QColor("#3a3a3a") if enabled else QColor("#2a2a2a")
            bg = QColor("#1b1b1b")
            if checked:
                bg = QColor("#cfa9ff")
                border = QColor("#cfa9ff")

            painter.setPen(QPen(border, 1))
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, 6, 6)

            if checked:
                pen = QPen(QColor("#111111"), 2.2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)

                x1 = rect.left() + rect.width() * 0.26
                y1 = rect.top() + rect.height() * 0.56
                x2 = rect.left() + rect.width() * 0.44
                y2 = rect.top() + rect.height() * 0.74
                x3 = rect.left() + rect.width() * 0.78
                y3 = rect.top() + rect.height() * 0.32

                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
                painter.drawLine(int(x2), int(y2), int(x3), int(y3))

            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)


def apply_chatgpt_dark(app: QApplication) -> None:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#1f1f1f"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#eaeaea"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#171717"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1d1d1d"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#eaeaea"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#2a2a2a"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#eaeaea"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#3a3a3a"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

    # IMPORTANT: we do NOT style checkbox indicator here (custom style draws it)
    app.setStyleSheet(
        """
        * { font-size: 10pt; }
        QWidget { color: #eaeaea; background: transparent; }
        QMainWindow { background: #1f1f1f; }

        QFrame#Card {
            background: #232323;
            border: 1px solid #2f2f2f;
            border-radius: 18px;
        }
        QLabel#H1 { font-size: 16pt; font-weight: 800; }
        QLabel#SectionTitle { font-size: 10.5pt; font-weight: 800; color: #f0f0f0; }
        QLabel#Hint { color: #bdbdbd; font-weight: 700; }

        QLineEdit, QComboBox, QTextEdit {
            background: #1b1b1b;
            border: 1px solid #2f2f2f;
            border-radius: 12px;
            padding: 10px 12px;
        }
        QComboBox::drop-down { border: 0px; width: 30px; }
        QComboBox QAbstractItemView {
            background: #1b1b1b;
            border: 1px solid #2f2f2f;
            selection-background-color: #2b2b2b;
        }

        QCheckBox { spacing: 10px; }

        QPushButton {
            border-radius: 12px;
            padding: 9px 14px;
            border: 1px solid #2f2f2f;
            background: #262626;
        }
        QPushButton:hover { background: #2b2b2b; border: 1px solid #3a3a3a; }
        QPushButton:pressed { background: #222222; }
        QPushButton:disabled { color: #8c8c8c; background: #222222; border: 1px solid #262626; }

        QPushButton#Primary {
            background: #f3f3f3;
            color: #111111;
            border: 1px solid #f3f3f3;
            font-weight: 800;
        }
        QPushButton#Primary:hover { background: #ffffff; }

        QPushButton#Danger {
            background: #3a2020;
            border: 1px solid #5a2a2a;
            color: #ffd6d6;
            font-weight: 800;
        }

        QToolButton {
            border-radius: 12px;
            padding: 9px 12px;
            border: 1px solid #2f2f2f;
            background: #262626;
        }

        QTableView {
            background: #1b1b1b;
            border: 1px solid #2f2f2f;
            border-radius: 14px;
            gridline-color: #222222;
            selection-background-color: #2a2a2a;
            selection-color: #ffffff;
        }
        QHeaderView::section {
            background: #1b1b1b;
            border: 0px;
            border-bottom: 1px solid #2f2f2f;
            padding: 10px 10px;
            font-weight: 900;
            color: #eaeaea;
            text-align: left;
        }
        QTableView::item { padding: 8px 10px; }
        QScrollBar:vertical {
            background: transparent;
            width: 12px;
            margin: 8px 6px 8px 0px;
        }
        QScrollBar::handle:vertical {
            background: #3a3a3a;
            border-radius: 6px;
            min-height: 40px;
        }
        QScrollBar::handle:vertical:hover { background: #4a4a4a; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """
    )


class LogsDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("Logs")
        self.resize(900, 520)

        lay = QVBoxLayout(self)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setText(LOG.dump())
        lay.addWidget(self.text)

        btn = QPushButton("Close")
        btn.clicked.connect(self.accept)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)


# =========================
# Main Window
# =========================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(app_icon_path()))
        self.resize(1320, 760)

        self.settings = QSettings(APP_ORG, APP_SETTINGS)

        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._scan_cancel = threading.Event()

        self._rename_thread: Optional[QThread] = None
        self._rename_worker: Optional[RenameWorker] = None
        self._rename_cancel = threading.Event()

        self._undo_pairs: List[Tuple[Path, Path]] = []

        self.model = PreviewModel()
        self.proxy = PreviewFilter()
        self.proxy.setSourceModel(self.model)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(220)
        self._debounce.timeout.connect(self._start_scan_if_possible)

        self._build_ui()
        self._load_settings()
        self._update_ui_state(initial=True)

        QTimer.singleShot(0, self._fit_columns_initial)
        self._debounce.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_columns_initial)

    # ---------- UI ----------
    def _card(self, title: str) -> QFrame:
        f = QFrame()
        f.setObjectName("Card")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        t = QLabel(title)
        t.setObjectName("SectionTitle")
        lay.addWidget(t)
        return f

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

        # Top bar
        top = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("H1")

        btn_help = QPushButton("Help")
        btn_logs = QPushButton("Logs")
        btn_help.clicked.connect(self._show_help)
        btn_logs.clicked.connect(self._show_logs)

        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(btn_help)
        top.addWidget(btn_logs)
        outer.addLayout(top)

        # Main split
        split = QHBoxLayout()
        split.setSpacing(14)
        outer.addLayout(split, 1)

        # Left panel
        left = QVBoxLayout()
        left.setSpacing(14)
        split.addLayout(left, 1)

        # Folder card
        self.card_folder = self._card("Folder")
        left.addWidget(self.card_folder)

        cf = self.card_folder.layout()
        assert isinstance(cf, QVBoxLayout)

        row_path = QHBoxLayout()
        self.ed_folder = QLineEdit()
        self.ed_folder.setPlaceholderText("Select a folder…")
        self.ed_folder.textChanged.connect(lambda: self._debounce.start())

        self.btn_browse = QPushButton("Browse")
        self.btn_open = QPushButton("Open")
        self.btn_browse.setObjectName("Primary")
        self.btn_browse.clicked.connect(self._browse_folder)
        self.btn_open.clicked.connect(self._open_folder)

        row_path.addWidget(self.ed_folder, 1)
        row_path.addSpacing(10)
        row_path.addWidget(self.btn_browse)
        row_path.addWidget(self.btn_open)
        cf.addLayout(row_path)

        # CLEAN counts: no boxes/pills
        self.lbl_counts = QLabel("Files: 0   |   Metadata: 0/0")
        self.lbl_counts.setObjectName("Hint")
        cf.addWidget(self.lbl_counts)

        # Naming card
        self.card_naming = self._card("Naming")
        left.addWidget(self.card_naming)

        cn = self.card_naming.layout()
        assert isinstance(cn, QVBoxLayout)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        # ORDER requested:
        # Format -> Prefix -> Suffix -> Pattern -> Fallback -> Include subfolders
        self.cmb_format = QComboBox()
        self.cmb_format.setEditable(True)
        self.cmb_format.addItems([
            "%Y-%m-%d_%H-%M-%S",
            "%Y%m%d_%H%M%S",
            "%d-%m-%Y_%Hh%Mm%Ss",
        ])
        self.cmb_format.setCurrentText("%Y-%m-%d_%H-%M-%S")
        self.cmb_format.currentTextChanged.connect(lambda: self._debounce.start())

        self.ed_prefix = QLineEdit()
        self.ed_prefix.setPlaceholderText("Prefix (optional)")
        self.ed_prefix.textChanged.connect(lambda: self._debounce.start())

        self.ed_suffix = QLineEdit()
        self.ed_suffix.setPlaceholderText("Suffix (optional)")
        self.ed_suffix.textChanged.connect(lambda: self._debounce.start())

        self.cmb_pattern = QComboBox()
        self.cmb_pattern.addItems([PatternMode.DATE_ONLY, PatternMode.DATE_ORIG, PatternMode.ORIG_ONLY, PatternMode.ORIG_DATE])
        self.cmb_pattern.setCurrentText(PatternMode.DATE_ONLY)
        self.cmb_pattern.currentIndexChanged.connect(lambda: self._debounce.start())

        self.cmb_fallback = QComboBox()
        self.cmb_fallback.addItems([FallbackMode.OFF, FallbackMode.FS_CREATED, FallbackMode.FS_MODIFIED])
        self.cmb_fallback.setCurrentText(FallbackMode.OFF)
        self.cmb_fallback.currentIndexChanged.connect(lambda: self._debounce.start())

        self.cb_recursive = QCheckBox("Include subfolders (recursive)")
        self.cb_recursive.setChecked(True)
        self.cb_recursive.stateChanged.connect(lambda: self._debounce.start())

        r = 0
        grid.addWidget(QLabel("Format"), r, 0)
        grid.addWidget(self.cmb_format, r, 1, 1, 2)
        r += 1

        grid.addWidget(QLabel("Prefix"), r, 0)
        grid.addWidget(self.ed_prefix, r, 1, 1, 2)
        r += 1
        
        grid.addWidget(QLabel("Suffix"), r, 0)
        grid.addWidget(self.ed_suffix, r, 1, 1, 2)
        r += 1

        grid.addWidget(QLabel("Pattern"), r, 0)
        grid.addWidget(self.cmb_pattern, r, 1, 1, 2)
        r += 1

        grid.addWidget(QLabel("Fallback if missing"), r, 0)
        grid.addWidget(self.cmb_fallback, r, 1, 1, 2)
        r += 1

        grid.addWidget(self.cb_recursive, r, 0, 1, 3)
        r += 1

        cn.addLayout(grid)

        # Advanced collapsible
        self.btn_adv = QToolButton()
        self.btn_adv.setText("Advanced analysis")
        self.btn_adv.setCheckable(True)
        self.btn_adv.setChecked(False)
        self.btn_adv.toggled.connect(self._toggle_advanced)

        self.adv_box = QFrame()
        self.adv_box.setObjectName("Card")
        self.adv_box.setVisible(False)
        adv_l = QVBoxLayout(self.adv_box)
        adv_l.setContentsMargins(14, 12, 14, 12)
        adv_l.setSpacing(10)

        self.cb_deep_filename = QCheckBox("Deep: parse date from filename")
        self.cb_deep_filename.setChecked(True)
        self.cb_deep_filename.stateChanged.connect(lambda: self._debounce.start())

        self.cb_deep_xmp = QCheckBox("Deep: read .xmp sidecar if present")
        self.cb_deep_xmp.setChecked(True)
        self.cb_deep_xmp.stateChanged.connect(lambda: self._debounce.start())

        self.cb_deep_takeout = QCheckBox("Deep: read Google Takeout .json sidecar")
        self.cb_deep_takeout.setChecked(True)
        self.cb_deep_takeout.stateChanged.connect(lambda: self._debounce.start())

        adv_l.addWidget(self.cb_deep_filename)
        adv_l.addWidget(self.cb_deep_xmp)
        adv_l.addWidget(self.cb_deep_takeout)

        cn.addSpacing(6)
        cn.addWidget(self.btn_adv, alignment=Qt.AlignmentFlag.AlignLeft)
        cn.addWidget(self.adv_box)

        # Run card (fix: no huge empty, title stays top)
        self.card_run = self._card("Run")
        self.card_run.setMaximumHeight(190)
        left.addWidget(self.card_run)

        cr = self.card_run.layout()
        assert isinstance(cr, QVBoxLayout)

        run_row = QHBoxLayout()
        run_row.setSpacing(12)

        self.btn_rename = QPushButton("Rename")
        self.btn_stop = QPushButton("Stop")
        self.btn_undo = QPushButton("Undo")

        self.btn_rename.setObjectName("Primary")
        self.btn_stop.setObjectName("Danger")

        for b in (self.btn_rename, self.btn_stop, self.btn_undo):
            b.setMinimumHeight(42)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_rename.clicked.connect(self._start_rename)
        self.btn_stop.clicked.connect(self._stop_all)
        self.btn_undo.clicked.connect(self._undo_last)

        run_row.addWidget(self.btn_rename)
        run_row.addWidget(self.btn_stop)
        run_row.addWidget(self.btn_undo)
        cr.addLayout(run_row)
        cr.addStretch(1)  # keep header at top visually

        # Right panel
        right = QVBoxLayout()
        right.setSpacing(14)
        split.addLayout(right, 1)

        self.card_preview = self._card("Preview")
        right.addWidget(self.card_preview, 1)

        cp = self.card_preview.layout()
        assert isinstance(cp, QVBoxLayout)

        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText("Filter (old/new)…")
        self.ed_filter.textChanged.connect(self.proxy.set_needle)
        cp.addWidget(self.ed_filter)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)

        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)

        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(30)

        cp.addWidget(self.table, 1)

    def _fit_columns_initial(self) -> None:
        # Split clean 50/50 on start and after resizes
        w = self.table.viewport().width()
        if w <= 40:
            return
        half = max(220, int(w * 0.5))
        self.table.setColumnWidth(0, half)
        self.table.setColumnWidth(1, max(220, w - half))

    # ---------- Settings ----------
    def _load_settings(self) -> None:
        self.ed_folder.setText(self.settings.value("folder/path", "", type=str))
        self.cb_recursive.setChecked(self.settings.value("naming/recursive", True, type=bool))
        self.cmb_format.setCurrentText(self.settings.value("naming/format", "%Y-%m-%d_%H-%M-%S", type=str))
        self.ed_prefix.setText(self.settings.value("naming/prefix", "", type=str))
        self.ed_suffix.setText(self.settings.value("naming/suffix", "", type=str))

        pat = self.settings.value("naming/pattern", PatternMode.DATE_ONLY, type=str)
        i = self.cmb_pattern.findText(pat)
        if i >= 0:
            self.cmb_pattern.setCurrentIndex(i)

        fb = self.settings.value("naming/fallback", FallbackMode.OFF, type=str)
        i = self.cmb_fallback.findText(fb)
        if i >= 0:
            self.cmb_fallback.setCurrentIndex(i)

        self.cb_deep_filename.setChecked(self.settings.value("deep/filename", True, type=bool))
        self.cb_deep_xmp.setChecked(self.settings.value("deep/xmp", True, type=bool))
        self.cb_deep_takeout.setChecked(self.settings.value("deep/takeout", True, type=bool))

    def _save_settings(self) -> None:
        self.settings.setValue("folder/path", self.ed_folder.text().strip())
        self.settings.setValue("naming/recursive", self.cb_recursive.isChecked())
        self.settings.setValue("naming/format", self.cmb_format.currentText())
        self.settings.setValue("naming/prefix", self.ed_prefix.text())
        self.settings.setValue("naming/suffix", self.ed_suffix.text())
        self.settings.setValue("naming/pattern", self.cmb_pattern.currentText())
        self.settings.setValue("naming/fallback", self.cmb_fallback.currentText())
        self.settings.setValue("deep/filename", self.cb_deep_filename.isChecked())
        self.settings.setValue("deep/xmp", self.cb_deep_xmp.isChecked())
        self.settings.setValue("deep/takeout", self.cb_deep_takeout.isChecked())

    # ---------- Actions ----------
    def _toggle_advanced(self, checked: bool) -> None:
        self.adv_box.setVisible(checked)

    def _browse_folder(self) -> None:
        start = self.ed_folder.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Select folder", start)
        if d:
            self.ed_folder.setText(d)

    def _open_folder(self) -> None:
        p = Path(self.ed_folder.text().strip())
        if not p.exists() or not p.is_dir():
            QMessageBox.information(self, "Open", "Select a valid folder first.")
            return
        QDesktopServices.openUrl(p.as_uri())  # cross-platform

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            "Help",
            "1) Choose a folder\n"
            "2) Preview updates automatically\n"
            "3) Click Rename\n"
            "Undo is available for the last run (this session).",
        )

    def _show_logs(self) -> None:
        LogsDialog(self).exec()

    def _stop_all(self) -> None:
        if self._scan_thread is not None:
            self._scan_cancel.set()
        if self._rename_thread is not None:
            self._rename_cancel.set()

    # ---------- Scan ----------
    def _build_reader(self) -> MetadataReader:
        deep = DeepOptions(
            parse_filename=self.cb_deep_filename.isChecked(),
            read_xmp_sidecar=self.cb_deep_xmp.isChecked(),
            read_takeout_json=self.cb_deep_takeout.isChecked(),
        )
        opts = ReadOptions(deep=deep, fallback=self.cmb_fallback.currentText())
        return MetadataReader(opts)

    def _start_scan_if_possible(self) -> None:
        self._save_settings()

        folder_txt = self.ed_folder.text().strip()
        folder = Path(folder_txt) if folder_txt else None
        if folder is None or not folder.exists() or not folder.is_dir():
            self.model.set_rows([])
            self.lbl_counts.setText("Files: 0   |   Metadata: 0/0")
            self._update_ui_state()
            self._fit_columns_initial()
            return

        if self._scan_thread is not None:
            self._scan_cancel.set()

        self._scan_cancel = threading.Event()
        reader = self._build_reader()

        fmt = self.cmb_format.currentText().strip() or "%Y-%m-%d_%H-%M-%S"
        prefix = self.ed_prefix.text()
        suffix = self.ed_suffix.text()
        pattern = self.cmb_pattern.currentText()

        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(
            folder=folder,
            recursive=self.cb_recursive.isChecked(),
            reader=reader,
            fmt=fmt,
            prefix=prefix,
            suffix=suffix,
            pattern=pattern,
            cancel_event=self._scan_cancel,
        )
        self._scan_worker.moveToThread(self._scan_thread)

        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)

        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.failed.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._cleanup_scan)

        self._scan_thread.start()
        self._update_ui_state()

    def _on_scan_finished(self, rows: list, total: int, meta_ok: int) -> None:
        rows = list(rows)
        self.model.set_rows(rows)

        self.lbl_counts.setText(f"Files: {total}   |   Metadata: {meta_ok}/{total}")
        log(f"[scan] files={total} meta={meta_ok} rows={len(rows)}")

        self._fit_columns_initial()
        self._update_ui_state()

    def _on_scan_failed(self, msg: str) -> None:
        log(f"[scan] ERROR {msg}")
        QMessageBox.critical(self, "Scan error", msg)
        self._update_ui_state()

    def _cleanup_scan(self) -> None:
        self._scan_thread = None
        self._scan_worker = None
        self._update_ui_state()

    # ---------- Rename / Undo ----------
    def _start_rename(self) -> None:
        if self._rename_thread is not None:
            return

        rows = self.model.rows
        if not rows:
            QMessageBox.information(self, "Rename", "Nothing to rename. Select a folder first.")
            return

        res = QMessageBox.question(
            self,
            "Confirm rename",
            "Rename files in place?\n\nUndo is available for the last run (this session).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        self._rename_cancel = threading.Event()

        fmt = self.cmb_format.currentText().strip() or "%Y-%m-%d_%H-%M-%S"
        prefix = self.ed_prefix.text()
        suffix = self.ed_suffix.text()
        pattern = self.cmb_pattern.currentText()

        self._rename_thread = QThread()
        self._rename_worker = RenameWorker(rows, fmt, prefix, suffix, pattern, self._rename_cancel)
        self._rename_worker.moveToThread(self._rename_thread)

        self._rename_thread.started.connect(self._rename_worker.run)
        self._rename_worker.finished.connect(self._on_rename_finished)
        self._rename_worker.failed.connect(self._on_rename_failed)

        self._rename_worker.finished.connect(self._rename_thread.quit)
        self._rename_worker.failed.connect(self._rename_thread.quit)
        self._rename_thread.finished.connect(self._cleanup_rename)

        self._rename_thread.start()
        self._update_ui_state()

    def _on_rename_finished(self, result_obj: object) -> None:
        if not isinstance(result_obj, RenameResult):
            QMessageBox.critical(self, "Rename", "Unexpected result.")
            return

        self._undo_pairs = list(result_obj.pairs)
        log(f"[rename] renamed={result_obj.renamed} skipped={result_obj.skipped} errors={result_obj.errors}")

        # refresh preview
        self._debounce.start()
        self._update_ui_state()

    def _on_rename_failed(self, msg: str) -> None:
        log(f"[rename] ERROR {msg}")
        QMessageBox.critical(self, "Rename error", msg)
        self._update_ui_state()

    def _cleanup_rename(self) -> None:
        self._rename_thread = None
        self._rename_worker = None
        self._update_ui_state()

    def _undo_last(self) -> None:
        if not self._undo_pairs:
            return
        res = QMessageBox.question(
            self,
            "Undo",
            "Undo last rename run?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Undo")
        dlg.setText("Undo in progress…")
        dlg.setStandardButtons(QMessageBox.StandardButton.NoButton)
        dlg.show()

        t = QThread()
        w = UndoWorker(self._undo_pairs)
        w.moveToThread(t)

        def done(undone: int, errors: int) -> None:
            dlg.hide()
            log(f"[undo] undone={undone} errors={errors}")
            if errors:
                QMessageBox.warning(self, "Undo", f"Undone: {undone}\nErrors: {errors}")
            else:
                QMessageBox.information(self, "Undo", f"Undone: {undone}")
            self._undo_pairs = []
            self._debounce.start()
            self._update_ui_state()

        def fail(msg: str) -> None:
            dlg.hide()
            log(f"[undo] ERROR {msg}")
            QMessageBox.critical(self, "Undo error", msg)
            self._update_ui_state()

        t.started.connect(w.run)
        w.finished.connect(done)
        w.failed.connect(fail)
        w.finished.connect(t.quit)
        w.failed.connect(t.quit)
        t.finished.connect(t.deleteLater)
        t.start()

    # ---------- UI State ----------
    def _update_ui_state(self, initial: bool = False) -> None:
        folder_ok = Path(self.ed_folder.text().strip()).is_dir()
        scanning = self._scan_thread is not None
        renaming = self._rename_thread is not None

        self.btn_open.setEnabled(folder_ok and not scanning and not renaming)
        self.btn_browse.setEnabled(not scanning and not renaming)
        self.ed_folder.setEnabled(not renaming)

        for w in (
            self.cb_recursive, self.cmb_fallback, self.cmb_format, self.ed_prefix, self.ed_suffix,
            self.cmb_pattern, self.btn_adv, self.cb_deep_filename, self.cb_deep_xmp, self.cb_deep_takeout
        ):
            w.setEnabled(not renaming)

        self.btn_rename.setEnabled(folder_ok and not scanning and not renaming and len(self.model.rows) > 0)
        self.btn_stop.setEnabled(scanning or renaming)
        self.btn_undo.setEnabled(not renaming and not scanning and bool(self._undo_pairs))

        if initial:
            self.btn_undo.setEnabled(False)

    def closeEvent(self, event) -> None:
        try:
            self._stop_all()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(app_icon_path()))

    # Apply checkbox style with visible checkmark ✓
    app.setStyle(CheckStyle(app.style()))

    apply_chatgpt_dark(app)

    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
