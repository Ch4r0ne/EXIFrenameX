from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    QUrl,
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


APP_NAME = "Date Renamer Toolkit"
APP_ORG = "TimTools"
APP_SETTINGS = "DateRenamerToolkit"
APP_SETTINGS_OLD = "EXIFrenameX_Final"
USE_NATIVE_SCROLLBARS = True


# =========================
# Assets
# =========================
def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return str(Path(base) / relative)
    return str(Path(relative))


def app_icon_path() -> str:
    # New branding first
    if sys.platform.startswith("win"):
        cand = resource_path("assets/DateRenamerToolkit.ico")
        fallback = resource_path("assets/EXIFrenameX.ico")
    elif sys.platform == "darwin":
        cand = resource_path("assets/DateRenamerToolkit.icns")
        fallback = resource_path("assets/EXIFrenameX.icns")
    else:
        cand = resource_path("assets/DateRenamerToolkit.ico")
        fallback = resource_path("assets/EXIFrenameX.ico")

    return cand if Path(cand).exists() else fallback


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
    # DJI Fly exports: dji_fly_20251108_164116_...
    ("DJI_FLY_YYYYMMDD_HHMMSS", re.compile(r"\bDJI[_-]?FLY[_-]((?:19|20)\d{6})[_-](\d{6})\b", re.IGNORECASE)),

    # DJI common: DJI_20251108_164116_...
    ("DJI_YYYYMMDD_HHMMSS", re.compile(r"\bDJI[_-]((?:19|20)\d{6})[_-](\d{6})\b", re.IGNORECASE)),

    # Generic camera export: 20251111_184839.mp4 (seen in your list)
    ("YYYYMMDD_HHMMSS", re.compile(r"\b((?:19|20)\d{6})[_-](\d{6})\b")),

    # Android/Apple style: IMG_20250101_120000 / VID_...
    ("IMG_VID_YYYYMMDD_HHMMSS", re.compile(r"\b(?:IMG|VID)[-_]?((?:19|20)\d{6})[_-](\d{6})\b", re.IGNORECASE)),

    ("YYYY-MM-DD_HH-MM-SS", re.compile(r"\b(\d{4})[-_](\d{2})[-_](\d{2})[ _-](\d{2})[-_](\d{2})[-_](\d{2})\b")),
    ("WHATSAPP_IMG_YYYYMMDD", re.compile(r"\bIMG-(\d{8})-WA\d+\b", re.IGNORECASE)),
]


def parse_date_from_filename(name: str) -> Optional[_dt.datetime]:
    base = Path(name).stem
    for key, rx in FILENAME_PATTERNS:
        m = rx.search(base)
        if not m:
            continue
        try:
            if key in {"IMG_VID_YYYYMMDD_HHMMSS", "DJI_YYYYMMDD_HHMMSS", "DJI_FLY_YYYYMMDD_HHMMSS", "YYYYMMDD_HHMMSS"}:
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


class ExifToolMode(str):
    AUTO = "Auto (bundled → system)"
    BUNDLED = "Bundled (packaged)"
    SYSTEM = "System (PATH)"
    OFF = "Off"


def bundled_exiftool_path() -> Optional[str]:
    # tools/exiftool/exiftool(.exe)
    if sys.platform.startswith("win"):
        p = Path(resource_path("tools/exiftool/exiftool.exe"))
    else:
        p = Path(resource_path("tools/exiftool/exiftool"))
    return str(p) if p.exists() else None


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
    def __init__(self, mode: str = ExifToolMode.AUTO) -> None:
        self.mode = mode
        self._cmd: Optional[List[str]] = None
        self._desc: str = "exiftool:disabled"
        self._version: str = ""
        self._resolve()

    def _run_exiftool(self, args: List[str]) -> subprocess.CompletedProcess[str]:
        """
        Run exiftool without flashing a console window on Windows.
        """
        if not self._cmd:
            raise RuntimeError("ExifTool not resolved")

        kwargs: Dict[str, Any] = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
            kwargs["creationflags"] = creationflags
            kwargs["startupinfo"] = startupinfo

        return subprocess.run(self._cmd + args, **kwargs)

    def _probe(self, cmd: List[str]) -> bool:
        try:
            self._cmd = cmd
            p = self._run_exiftool(["-ver"])
            if p.returncode == 0:
                self._version = (p.stdout or "").strip()
                return True
        except Exception:
            return False
        return False

    def _resolve(self) -> None:
        if self.mode == ExifToolMode.OFF:
            return

        bundled = bundled_exiftool_path()
        candidates: List[Tuple[List[str], str]] = []

        if self.mode in (ExifToolMode.AUTO, ExifToolMode.BUNDLED) and bundled:
            candidates.append(([bundled], f"bundled:{bundled}"))

        if self.mode in (ExifToolMode.AUTO, ExifToolMode.SYSTEM):
            candidates.append((["exiftool"], "system:exiftool"))

        for cmd, desc in candidates:
            if self._probe(cmd):
                self._cmd = cmd
                self._desc = desc
                return

        self._cmd = None
        self._desc = "exiftool:not_found"

    def __enter__(self) -> "ExifToolSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def available(self) -> bool:
        return self._cmd is not None

    def info(self) -> str:
        if not self.available():
            return self._desc
        return f"{self._desc} v{self._version}"

    def metadata(self, file_path: str) -> Dict[str, Any]:
        if not self._cmd:
            return {}
        return self._cli_metadata(file_path)

    def metadata_many(self, file_paths: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch metadata for many files in ONE exiftool call.
        Returns map: SourceFile -> metadata dict.
        """
        if not self._cmd or not file_paths:
            return {}

        tag_args = [f"-{t}" for t in EXIFTOOL_DATE_TAGS] + [
            "-DateTimeOriginal",
            "-CreateDate",
            "-MediaCreateDate",
        ]

        try:
            p = self._run_exiftool(["-j", "-G", "-s"] + tag_args + file_paths)
            if p.returncode != 0:
                return {}
            arr = json.loads(p.stdout or "[]")
            out: Dict[str, Dict[str, Any]] = {}
            if isinstance(arr, list):
                for d in arr:
                    if isinstance(d, dict):
                        sf = str(d.get("SourceFile") or "")
                        if sf:
                            out[sf] = d
            return out
        except Exception:
            return {}

    def _cli_metadata(self, file_path: str) -> Dict[str, Any]:
        try:
            tag_args = [f"-{t}" for t in EXIFTOOL_DATE_TAGS] + [
                "-DateTimeOriginal",
                "-CreateDate",
                "-MediaCreateDate",
            ]
            p = self._run_exiftool(["-j", "-G", "-s"] + tag_args + [file_path])
            if p.returncode != 0:
                return {}
            arr = json.loads(p.stdout or "[]")
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

    def best_datetime(
        self,
        p: Path,
        exiftool: Optional[ExifToolSession],
        exiftool_md: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[_dt.datetime], str]:
        # 1) ExifTool FIRST if available (Windows/macOS)
        if exiftool_md is None and exiftool is not None and exiftool.available():
            exiftool_md = exiftool.metadata(str(p))

        if exiftool_md:
            for tag in EXIFTOOL_DATE_TAGS:
                if tag in exiftool_md:
                    dt = parse_datetime_any(str(exiftool_md[tag]))
                    if dt:
                        return dt, f"exiftool:{tag}"
            for tag in ("DateTimeOriginal", "CreateDate", "MediaCreateDate"):
                if tag in exiftool_md:
                    dt = parse_datetime_any(str(exiftool_md[tag]))
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

    def clear(self) -> None:
        self.beginResetModel()
        self.rows = []
        self.endResetModel()

    def append_row(self, row: PreviewRow) -> None:
        r = len(self.rows)
        self.beginInsertRows(QModelIndex(), r, r)
        self.rows.append(row)
        self.endInsertRows()

    def append_rows(self, rows: List[PreviewRow]) -> None:
        if not rows:
            return
        start = len(self.rows)
        end = start + len(rows) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self.rows.extend(rows)
        self.endInsertRows()

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
    row_ready = pyqtSignal(object, int, int, int, int)  # row, processed, total, meta_ok, scan_id
    finished = pyqtSignal(list, int, int, str, int)  # rows, total_files, meta_ok, exiftool_info, scan_id
    failed = pyqtSignal(str, int)

    def __init__(
        self,
        scan_id: int,
        folder: Path,
        recursive: bool,
        reader: MetadataReader,
        fmt: str,
        prefix: str,
        suffix: str,
        pattern: str,
        exiftool_mode: str,
        cancel_event: threading.Event,
        parallel_scan: bool,
        parallel_workers: str,
    ):
        super().__init__()
        self.scan_id = scan_id
        self.folder = folder
        self.recursive = recursive
        self.reader = reader
        self.fmt = fmt
        self.prefix = prefix
        self.suffix = suffix
        self.pattern = pattern
        self.exiftool_mode = exiftool_mode
        self.cancel = cancel_event
        self.parallel_scan = parallel_scan
        self.parallel_workers = parallel_workers

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
                self.failed.emit("Folder does not exist.", self.scan_id)
                return

            files = list(self._iter_files())
            total = len(files)

            def _norm(s: str) -> str:
                return os.path.normcase(os.path.normpath(s))

            rows: List[PreviewRow] = []
            used: Dict[Path, set[str]] = {}

            with ExifToolSession(mode=self.exiftool_mode) as exiftool:
                info = exiftool.info()
                log(f"[scan] {info}")

                exif_map: Dict[str, Dict[str, Any]] = {}
                if exiftool.available() and total:
                    chunk_size = 200
                    for i in range(0, total, chunk_size):
                        if self.cancel.is_set():
                            break
                        chunk = files[i : i + chunk_size]
                        md = exiftool.metadata_many([str(p) for p in chunk])
                        for k, v in md.items():
                            exif_map[_norm(k)] = v

                def process_one(idx: int, p: Path) -> Tuple[int, PreviewRow, bool]:
                    if self.cancel.is_set():
                        row = PreviewRow(p.name, "(cancelled)", None, "cancelled", p, "SKIP (cancelled)")
                        return idx, row, False

                    md = exif_map.get(_norm(str(p)))
                    dt, src = self.reader.best_datetime(p, exiftool=None, exiftool_md=md)
                    ok = dt is not None

                    new = format_new_name(dt, p.name, self.fmt, self.prefix, self.suffix, self.pattern)
                    if new is None:
                        row = PreviewRow(p.name, "(no timestamp)", dt, src, p, "SKIP (missing timestamp)")
                        return idx, row, ok

                    row = PreviewRow(p.name, new, dt, src, p, "OK")
                    return idx, row, ok

                def resolve_workers() -> int:
                    if (self.parallel_workers or "").strip().lower() != "auto":
                        try:
                            n = int(self.parallel_workers)
                            return max(1, min(32, n))
                        except Exception:
                            pass
                    cpu = os.cpu_count() or 4
                    return max(4, min(12, cpu * 2))

                parallel = bool(self.parallel_scan) and total > 1

                results: Dict[int, Tuple[PreviewRow, bool]] = {}
                next_emit = 0
                processed = 0
                meta_ok = 0

                def emit_ready_up_to() -> None:
                    nonlocal next_emit, processed, meta_ok
                    while next_emit in results:
                        row, ok = results.pop(next_emit)
                        if row.status == "OK":
                            folder = row.path.parent
                            if folder not in used:
                                used[folder] = set()
                            row = PreviewRow(
                                row.old_name,
                                unique_name_in_folder(folder, row.new_name, used[folder]),
                                row.dt,
                                row.source,
                                row.path,
                                row.status,
                            )

                        rows.append(row)
                        processed += 1
                        if ok:
                            meta_ok += 1
                        self.row_ready.emit(row, processed, total, meta_ok, self.scan_id)
                        next_emit += 1

                if not parallel:
                    for idx, p in enumerate(files):
                        if self.cancel.is_set():
                            break
                        i, row, ok = process_one(idx, p)
                        results[i] = (row, ok)
                        emit_ready_up_to()

                    self.finished.emit(rows, total, meta_ok, info, self.scan_id)
                    return

                workers = resolve_workers()
                log(f"[scan] parallel workers={workers}")

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(process_one, idx, p) for idx, p in enumerate(files)]
                    for fut in as_completed(futures):
                        if self.cancel.is_set():
                            break
                        idx, row, ok = fut.result()
                        results[idx] = (row, ok)
                        emit_ready_up_to()

                emit_ready_up_to()
                self.finished.emit(rows, total, meta_ok, info, self.scan_id)

        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}", self.scan_id)


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


def apply_enterprise_dark_theme(app: QApplication) -> None:
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
    stylesheet = """
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
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
            border: 1px solid #cfa9ff;
        }
        QLineEdit:disabled, QComboBox:disabled, QTextEdit:disabled {
            color: #9a9a9a;
            background: #1a1a1a;
            border: 1px solid #262626;
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
        QPushButton:focus { border: 1px solid #cfa9ff; }

        QPushButton[primary="true"] {
            background: #f3f3f3;
            color: #111111;
            border: 1px solid #f3f3f3;
            font-weight: 800;
        }
        QPushButton[primary="true"]:hover { background: #ffffff; }

        QPushButton[danger="true"] {
            background: #3a2020;
            border: 1px solid #5a2a2a;
            color: #ffd6d6;
            font-weight: 800;
        }
        QPushButton[danger="true"]:hover { background: #442626; }

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
    """
    if not USE_NATIVE_SCROLLBARS:
        stylesheet += """
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
    app.setStyleSheet(stylesheet)


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
        self._migrate_settings_once()

        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._scan_cancel = threading.Event()
        self._scan_seq = 0
        self._active_scan_id = 0
        self._scan_restart_requested = False

        self._row_buffer: List[PreviewRow] = []
        self._scan_progress: Optional[Tuple[int, int, int]] = None

        self._rename_thread: Optional[QThread] = None
        self._rename_worker: Optional[RenameWorker] = None
        self._rename_cancel = threading.Event()

        self._undo_pairs: List[Tuple[Path, Path]] = []

        self.model = PreviewModel()
        self.proxy = PreviewFilter()
        self.proxy.setSourceModel(self.model)

        # --- Debounces: scan vs naming ---
        self._scan_debounce = QTimer(self)
        self._scan_debounce.setSingleShot(True)
        self._scan_debounce.setInterval(350)
        self._scan_debounce.timeout.connect(self._start_scan_if_possible)

        self._naming_debounce = QTimer(self)
        self._naming_debounce.setSingleShot(True)
        self._naming_debounce.setInterval(250)
        self._naming_debounce.timeout.connect(self._apply_naming_if_possible)

        self._naming_dirty = False
        self._pending_naming_apply = False

        self._row_flush = QTimer(self)
        self._row_flush.setInterval(50)
        self._row_flush.timeout.connect(self._flush_row_buffer)

        self._build_ui()
        self._load_settings()
        self._update_ui_state(initial=True)

        QTimer.singleShot(0, self._fit_columns_initial)
        self._scan_debounce.start()

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
        self.ed_folder.textChanged.connect(self._trigger_scan)

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
        self.cmb_format.currentTextChanged.connect(self._trigger_naming)

        self.ed_prefix = QLineEdit()
        self.ed_prefix.setPlaceholderText("Prefix (optional)")
        self.ed_prefix.textChanged.connect(self._trigger_naming)

        self.ed_suffix = QLineEdit()
        self.ed_suffix.setPlaceholderText("Suffix (optional)")
        self.ed_suffix.textChanged.connect(self._trigger_naming)

        self.cmb_pattern = QComboBox()
        self.cmb_pattern.addItems([PatternMode.DATE_ONLY, PatternMode.DATE_ORIG, PatternMode.ORIG_ONLY, PatternMode.ORIG_DATE])
        self.cmb_pattern.setCurrentText(PatternMode.DATE_ONLY)
        self.cmb_pattern.currentIndexChanged.connect(self._trigger_naming)

        self.cmb_fallback = QComboBox()
        self.cmb_fallback.addItems([FallbackMode.OFF, FallbackMode.FS_CREATED, FallbackMode.FS_MODIFIED])
        self.cmb_fallback.setCurrentText(FallbackMode.OFF)
        self.cmb_fallback.currentIndexChanged.connect(self._trigger_scan)

        self.cb_recursive = QCheckBox("Include subfolders (recursive)")
        self.cb_recursive.setChecked(True)
        self.cb_recursive.stateChanged.connect(self._trigger_scan)

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

        row = QHBoxLayout()
        row.addWidget(QLabel("ExifTool"))
        self.cmb_exiftool = QComboBox()
        self.cmb_exiftool.addItems([ExifToolMode.AUTO, ExifToolMode.BUNDLED, ExifToolMode.SYSTEM, ExifToolMode.OFF])
        self.cmb_exiftool.setCurrentText(ExifToolMode.AUTO)
        self.cmb_exiftool.currentIndexChanged.connect(self._trigger_scan)
        row.addWidget(self.cmb_exiftool, 1)
        adv_l.addLayout(row)

        self.lbl_exiftool_info = QLabel("ExifTool: (scan not run yet)")
        self.lbl_exiftool_info.setObjectName("Hint")
        adv_l.addWidget(self.lbl_exiftool_info)

        self.cb_deep_xmp = QCheckBox("Deep: read .xmp sidecar if present")
        self.cb_deep_xmp.setChecked(True)
        self.cb_deep_xmp.stateChanged.connect(self._trigger_scan)

        self.cb_deep_takeout = QCheckBox("Deep: read Google Takeout .json sidecar")
        self.cb_deep_takeout.setChecked(True)
        self.cb_deep_takeout.stateChanged.connect(self._trigger_scan)

        adv_l.addWidget(self.cb_deep_xmp)
        adv_l.addWidget(self.cb_deep_takeout)

        self.cb_filename_date = QCheckBox("Deep: use filename date when metadata is missing")
        self.cb_filename_date.setChecked(False)
        self.cb_filename_date.stateChanged.connect(self._trigger_scan)
        adv_l.addWidget(self.cb_filename_date)

        self.cb_parallel_scan = QCheckBox("Performance: parallel scan (recommended)")
        self.cb_parallel_scan.setChecked(True)
        self.cb_parallel_scan.stateChanged.connect(self._trigger_scan)
        adv_l.addWidget(self.cb_parallel_scan)

        rowp = QHBoxLayout()
        rowp.addWidget(QLabel("Parallel workers"))
        self.cmb_parallel_workers = QComboBox()
        self.cmb_parallel_workers.addItems(["Auto", "4", "6", "8", "12", "16"])
        self.cmb_parallel_workers.setCurrentText("Auto")
        self.cmb_parallel_workers.currentIndexChanged.connect(self._trigger_scan)
        rowp.addWidget(self.cmb_parallel_workers, 1)
        adv_l.addLayout(rowp)

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

        self.btn_undo = QPushButton("Undo")
        self.btn_action = QPushButton("Rename")

        self.btn_action.setProperty("primary", True)
        self.btn_action.setProperty("danger", False)

        for b in (self.btn_action, self.btn_undo):
            b.setMinimumHeight(46)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_action.clicked.connect(self._primary_action)
        self.btn_undo.clicked.connect(self._undo_last)

        run_row.addWidget(self.btn_action, 3)
        run_row.addWidget(self.btn_undo, 1)
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
    def _migrate_settings_once(self) -> None:
        if self.settings.value("_migrated_from_exifrenamex", False, type=bool):
            return

        old = QSettings(APP_ORG, APP_SETTINGS_OLD)
        try:
            keys = old.allKeys()
        except Exception:
            keys = []

        # Nur migrieren, wenn wirklich alte Settings existieren
        if keys:
            for k in keys:
                if self.settings.value(k, None) in (None, ""):
                    self.settings.setValue(k, old.value(k))

        self.settings.setValue("_migrated_from_exifrenamex", True)

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

        self.cb_filename_date.setChecked(self.settings.value("deep/filename", False, type=bool))
        self.cb_deep_xmp.setChecked(self.settings.value("deep/xmp", True, type=bool))
        self.cb_deep_takeout.setChecked(self.settings.value("deep/takeout", True, type=bool))
        self.cb_parallel_scan.setChecked(self.settings.value("perf/parallel_scan", True, type=bool))
        self.cmb_parallel_workers.setCurrentText(self.settings.value("perf/parallel_workers", "Auto", type=str))

    def _save_settings(self) -> None:
        self.settings.setValue("folder/path", self.ed_folder.text().strip())
        self.settings.setValue("naming/recursive", self.cb_recursive.isChecked())
        self.settings.setValue("naming/format", self.cmb_format.currentText())
        self.settings.setValue("naming/prefix", self.ed_prefix.text())
        self.settings.setValue("naming/suffix", self.ed_suffix.text())
        self.settings.setValue("naming/pattern", self.cmb_pattern.currentText())
        self.settings.setValue("naming/fallback", self.cmb_fallback.currentText())
        self.settings.setValue("deep/filename", self.cb_filename_date.isChecked())
        self.settings.setValue("deep/xmp", self.cb_deep_xmp.isChecked())
        self.settings.setValue("deep/takeout", self.cb_deep_takeout.isChecked())
        self.settings.setValue("perf/parallel_scan", self.cb_parallel_scan.isChecked())
        self.settings.setValue("perf/parallel_workers", self.cmb_parallel_workers.currentText())

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
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

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

    def _trigger_scan(self) -> None:
        # Scan ist teuer → nur wenn nötig
        self._scan_debounce.start()

    def _trigger_naming(self) -> None:
        # Naming ist billig → nur Preview neu rechnen
        self._naming_dirty = True
        self._naming_debounce.start()

    def _stop_all(self) -> None:
        self._scan_restart_requested = False
        if self._scan_thread is not None:
            self._scan_cancel.set()
        if self._rename_thread is not None:
            self._rename_cancel.set()

    def _request_scan_restart(self) -> None:
        if self._scan_thread is None:
            return
        self._scan_restart_requested = True
        self._scan_cancel.set()

    # ---------- Scan ----------
    def _primary_action(self) -> None:
        scanning = self._scan_thread is not None
        renaming = self._rename_thread is not None
        if scanning or renaming:
            self._stop_all()
            return
        self._start_rename()

    def _build_reader(self) -> MetadataReader:
        deep = DeepOptions(
            parse_filename=self.cb_filename_date.isChecked(),
            read_xmp_sidecar=self.cb_deep_xmp.isChecked(),
            read_takeout_json=self.cb_deep_takeout.isChecked(),
        )
        opts = ReadOptions(deep=deep, fallback=self.cmb_fallback.currentText())
        return MetadataReader(opts)

    def _apply_naming_if_possible(self, force: bool = False) -> None:
        if not force and not self._naming_dirty:
            return

        # Während Scan läuft: nicht ständig ResetModel + Inserts fighten.
        # Wir merken uns nur: "nach Scan fertig anwenden".
        if self._scan_thread is not None and not force:
            self._pending_naming_apply = True
            return

        self._naming_dirty = False
        self._pending_naming_apply = False

        if not self.model.rows:
            self._update_ui_state()
            return

        fmt = self.cmb_format.currentText().strip() or "%Y-%m-%d_%H-%M-%S"
        prefix = self.ed_prefix.text()
        suffix = self.ed_suffix.text()
        pattern = self.cmb_pattern.currentText()

        used: Dict[Path, set[str]] = {}
        new_rows: List[PreviewRow] = []

        for r in self.model.rows:
            # ERROR/CANCEL nicht überschreiben
            if r.status.startswith("ERROR") or r.status.startswith("SKIP (cancelled)"):
                new_rows.append(r)
                continue

            folder = r.path.parent
            if folder not in used:
                used[folder] = set()

            new_name = format_new_name(r.dt, r.old_name, fmt, prefix, suffix, pattern)
            if new_name is None:
                new_rows.append(PreviewRow(
                    r.old_name,
                    "(no timestamp)",
                    r.dt,
                    r.source,
                    r.path,
                    "SKIP (missing timestamp)",
                ))
                continue

            uniq = unique_name_in_folder(folder, new_name, used[folder])
            new_rows.append(PreviewRow(r.old_name, uniq, r.dt, r.source, r.path, "OK"))

        self.model.set_rows(new_rows)
        self._fit_columns_initial()
        self._update_ui_state()

    def _flush_row_buffer(self) -> None:
        if not self._row_buffer:
            self._row_flush.stop()
            return

        batch = self._row_buffer[:200]
        del self._row_buffer[:200]
        self.model.append_rows(batch)

        if self._scan_progress:
            processed, total, meta_ok = self._scan_progress
            self.lbl_counts.setText(f"Files: {processed}/{total}   |   Metadata: {meta_ok}/{processed}")

        if not self._row_buffer:
            self._row_flush.stop()

    def _start_scan_if_possible(self) -> None:
        self._save_settings()

        if self._rename_thread is not None:
            return

        folder_txt = self.ed_folder.text().strip()
        folder = Path(folder_txt) if folder_txt else None
        if folder is None or not folder.exists() or not folder.is_dir():
            self.model.clear()
            self._row_buffer.clear()
            self._row_flush.stop()
            self._scan_progress = None
            self.lbl_counts.setText("Files: 0   |   Metadata: 0/0")
            self._update_ui_state()
            self._fit_columns_initial()
            return

        if self._scan_thread is not None:
            self._request_scan_restart()
            self._update_ui_state()
            return

        self._scan_cancel = threading.Event()
        reader = self._build_reader()

        fmt = self.cmb_format.currentText().strip() or "%Y-%m-%d_%H-%M-%S"
        prefix = self.ed_prefix.text()
        suffix = self.ed_suffix.text()
        pattern = self.cmb_pattern.currentText()
        exiftool_mode = getattr(self, "cmb_exiftool", None).currentText() if hasattr(self, "cmb_exiftool") else ExifToolMode.AUTO
        parallel_scan = self.cb_parallel_scan.isChecked()
        parallel_workers = self.cmb_parallel_workers.currentText()

        self._scan_seq += 1
        scan_id = self._scan_seq
        self._active_scan_id = scan_id

        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(
            scan_id=scan_id,
            folder=folder,
            recursive=self.cb_recursive.isChecked(),
            reader=reader,
            fmt=fmt,
            prefix=prefix,
            suffix=suffix,
            pattern=pattern,
            exiftool_mode=exiftool_mode,
            cancel_event=self._scan_cancel,
            parallel_scan=parallel_scan,
            parallel_workers=parallel_workers,
        )
        self._scan_worker.moveToThread(self._scan_thread)

        self.model.clear()
        self._row_buffer.clear()
        self._row_flush.stop()
        self._scan_progress = None
        self.lbl_counts.setText("Files: 0   |   Metadata: 0/0")
        self.table.setSortingEnabled(False)

        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.row_ready.connect(self._on_scan_row_ready)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)

        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.failed.connect(self._scan_thread.quit)
        t = self._scan_thread
        w = self._scan_worker
        self._scan_thread.finished.connect(lambda sid=scan_id, tt=t, ww=w: self._cleanup_scan_instance(sid, tt, ww))

        self._scan_thread.start()
        self._update_ui_state()

    def _on_scan_row_ready(self, row_obj: object, processed: int, total: int, meta_ok: int, scan_id: int) -> None:
        if scan_id != self._active_scan_id:
            return
        if isinstance(row_obj, PreviewRow):
            self._row_buffer.append(row_obj)
            self._scan_progress = (processed, total, meta_ok)
            if not self._row_flush.isActive():
                self._row_flush.start()

    def _on_scan_finished(self, rows: list, total: int, meta_ok: int, exiftool_info: str, scan_id: int) -> None:
        if scan_id != self._active_scan_id:
            return
        self._row_buffer.clear()
        self._row_flush.stop()
        rows = list(rows)
        self.model.set_rows(rows)

        self.lbl_counts.setText(f"Files: {total}   |   Metadata: {meta_ok}/{total}")
        log(f"[scan] files={total} meta={meta_ok} rows={len(rows)}")
        self.lbl_exiftool_info.setText(f"ExifTool: {exiftool_info}")

        self._apply_naming_if_possible(force=True)

        self._fit_columns_initial()
        self.table.setSortingEnabled(True)
        self._update_ui_state()

    def _on_scan_failed(self, msg: str, scan_id: int) -> None:
        if scan_id != self._active_scan_id:
            return
        log(f"[scan] ERROR {msg}")
        self._row_buffer.clear()
        self._row_flush.stop()
        self.table.setSortingEnabled(True)
        QMessageBox.critical(self, "Scan error", msg)
        self._update_ui_state()

    def _cleanup_scan_instance(self, scan_id: int, t: QThread, w: QObject) -> None:
        try:
            w.deleteLater()
        except Exception:
            pass
        try:
            t.deleteLater()
        except Exception:
            pass

        if scan_id == self._active_scan_id:
            self._scan_thread = None
            self._scan_worker = None

            restart = self._scan_restart_requested
            self._scan_restart_requested = False
            self._update_ui_state()
            if restart:
                QTimer.singleShot(0, self._start_scan_if_possible)

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
        self._trigger_scan()
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
            self._trigger_scan()
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
        busy = scanning or renaming

        self.btn_open.setEnabled(folder_ok and not busy)
        self.btn_browse.setEnabled(not busy)
        self.ed_folder.setEnabled(not renaming)

        for w in (
            self.cb_recursive, self.cmb_fallback, self.cmb_format, self.ed_prefix, self.ed_suffix,
            self.cmb_pattern, self.btn_adv, self.cb_filename_date, self.cb_deep_xmp, self.cb_deep_takeout,
            self.cmb_exiftool, self.cb_parallel_scan, self.cmb_parallel_workers
        ):
            w.setEnabled(not renaming)

        self.btn_action.setEnabled(busy or (folder_ok and not scanning and not renaming and len(self.model.rows) > 0))
        self.btn_action.setText("Stop" if busy else "Rename")
        self.btn_action.setProperty("primary", not busy)
        self.btn_action.setProperty("danger", busy)
        self.btn_action.style().unpolish(self.btn_action)
        self.btn_action.style().polish(self.btn_action)
        self.btn_action.update()

        self.btn_undo.setEnabled(not busy and bool(self._undo_pairs))

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
    if sys.platform.startswith("win"):
        app.setFont(QFont("Segoe UI", 10))

    # Apply checkbox style with visible checkmark ✓
    app.setStyle(CheckStyle(app.style()))

    apply_enterprise_dark_theme(app)

    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
