import os
import re
import threading
import datetime
import logging
import tkinter
import tkinter.filedialog
import customtkinter
from PIL import Image
from pillow_heif import register_heif_opener
import exifread
import pymediainfo
import traceback
from typing import Optional, List, Tuple, Dict

# ExifToolWrapper check (optional dependency)
try:
    from exiftool_wrapper import ExifToolWrapper
    EXIFTOOL_AVAILABLE = True
except ImportError:
    EXIFTOOL_AVAILABLE = False

register_heif_opener()

logging.basicConfig(
    filename='exifrenamex.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

EXIFTOOL_DATE_TAGS = [
    "EXIF:DateTimeOriginal", "EXIF:CreateDate", "QuickTime:CreateDate", "QuickTime:MediaCreateDate",
    "XMP:CreateDate", "File:FileModifyDate", "File:FileCreateDate", "Composite:SubSecDateTimeOriginal",
    "Composite:DateTimeCreated", "QuickTime:TrackCreateDate", "QuickTime:TrackModifyDate",
    "QuickTime:ModifyDate", "QuickTime:ContentCreateDate", "PNG:CreationTime"
]

# --- Metadata utilities ---

def parse_exiftool_datetime(dt_string: str) -> Optional[datetime.datetime]:
    """Try to parse multiple datetime formats commonly found in metadata."""
    date_formats = (
        "%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S%z"
    )
    for fmt in date_formats:
        try:
            return datetime.datetime.strptime(dt_string, fmt)
        except Exception:
            continue
    dt_string_no_tz = re.sub(r'([+-]\d{2}:?\d{2}|Z)$', '', dt_string).strip()
    try:
        return datetime.datetime.strptime(dt_string_no_tz, "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None

class MediaMetadataService:
    """Handles all metadata extraction from files using multiple fallback strategies."""
    EXIF_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.arw', '.nef', '.tiff', '.webp', '.bmp',
                       '.cr2', '.orf', '.rw2', '.rwl', '.srw']
    HEIC_EXTENSIONS = ['.heic']
    VIDEO_EXTENSIONS = ['.mp4', '.mov', '.3gp', '.avi', '.mkv', '.mts', '.m2ts', '.wmv']

    @staticmethod
    def get_exiftool_date(file_path: str) -> Optional[datetime.datetime]:
        if not EXIFTOOL_AVAILABLE:
            return None
        try:
            with ExifToolWrapper() as et:
                metadata = et.get_metadata(file_path)
            for tag in EXIFTOOL_DATE_TAGS:
                if tag in metadata:
                    dt = parse_exiftool_datetime(str(metadata[tag]))
                    if dt:
                        return dt
        except Exception as e:
            logging.warning(f"ExifTool read failed for {file_path}: {e}")
        return None

    @staticmethod
    def get_exif_date(file_path: str) -> Optional[datetime.datetime]:
        try:
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, stop_tag="EXIF DateTimeOriginal", details=False)
                date_str = str(tags.get('EXIF DateTimeOriginal') or tags.get('EXIF DateTime', ''))
                if date_str:
                    return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
        except Exception as e:
            logging.warning(f"EXIF read failed for {file_path}: {e}")
        return None

    @staticmethod
    def get_heic_exif_date(file_path: str) -> Optional[datetime.datetime]:
        try:
            with Image.open(file_path) as img:
                xmp = img.info.get('xmp')
                if xmp:
                    xmp = xmp.decode('utf-8') if isinstance(xmp, bytes) else xmp
                    match = re.search(r'xmp:CreateDate="([^"]+)"', xmp)
                    if match:
                        dt = match.group(1)
                        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z'):
                            try:
                                return datetime.datetime.strptime(dt, fmt)
                            except ValueError:
                                continue
        except Exception as e:
            logging.warning(f"HEIC/XMP read failed for {file_path}: {e}")
        return None

    @staticmethod
    def get_media_date(file_path: str) -> Optional[datetime.datetime]:
        try:
            mi = pymediainfo.MediaInfo.parse(file_path)
            for track in mi.tracks:
                for key in ['comapplequicktimecreationdate', 'recorded_date', 'encoded_date', 'tagged_date']:
                    date_str = track.to_data().get(key)
                    if date_str:
                        date_str = date_str.replace('T', ' ').split('+')[0]
                        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S %Z'):
                            try:
                                return datetime.datetime.strptime(date_str, fmt)
                            except ValueError:
                                continue
        except Exception as e:
            logging.warning(f"MediaInfo read failed for {file_path}: {e}")
        return None

    @staticmethod
    def get_file_system_date(file_path: str) -> datetime.datetime:
        stat = os.stat(file_path)
        try:
            if hasattr(stat, 'st_birthtime'):
                return datetime.datetime.fromtimestamp(stat.st_birthtime)
            return datetime.datetime.fromtimestamp(stat.st_ctime)
        except Exception:
            return datetime.datetime.fromtimestamp(stat.st_mtime)

    @classmethod
    def get_best_date(cls, file_path: str, use_fallback: bool = True) -> Optional[datetime.datetime]:
        ext = os.path.splitext(file_path)[1].lower()
        date = cls.get_exiftool_date(file_path)
        if date:
            return date
        if ext in cls.EXIF_EXTENSIONS:
            date = cls.get_exif_date(file_path)
            if date:
                return date
        if ext in cls.HEIC_EXTENSIONS:
            date = cls.get_heic_exif_date(file_path)
            if date:
                return date
        if ext in cls.VIDEO_EXTENSIONS:
            date = cls.get_media_date(file_path)
            if date:
                return date
        if use_fallback:
            return cls.get_file_system_date(file_path)
        return None

# --- Rename/Undo Service ---

class RenameService:
    """Handles file renaming logic, keeps undo history, abstracts all file operations for the GUI."""
    def __init__(self):
        self.rename_history: List[List[Tuple[str, str]]] = []

    def rename_files(
        self,
        folder_path: str,
        files: List[str],
        naming_settings: Dict,
        use_fallback: bool
    ) -> Tuple[List[str], List[str], List[str], List[Tuple[str, str]]]:
        renamed_files = []
        files_without_metadata = []
        errors = []
        rename_pairs = []
        name_set = set()
        for filename in files:
            file_path = os.path.join(folder_path, filename)
            try:
                date_obj = MediaMetadataService.get_best_date(file_path, use_fallback=use_fallback)
                if date_obj:
                    new_name = get_formatted_name(
                        date_obj, filename,
                        format_str=naming_settings["format_str"],
                        prefix=naming_settings["prefix"],
                        suffix=naming_settings["suffix"],
                        radio_option=naming_settings["radio_option"]
                    )
                    original_new_name = new_name
                    i = 1
                    while new_name in name_set or os.path.exists(os.path.join(folder_path, new_name)):
                        name_root, name_ext = os.path.splitext(original_new_name)
                        new_name = f"{name_root}_{i}{name_ext}"
                        i += 1
                    os.rename(file_path, os.path.join(folder_path, new_name))
                    renamed_files.append(new_name)
                    name_set.add(new_name)
                    rename_pairs.append((os.path.join(folder_path, new_name), file_path))
                    logging.info(f"Renamed: {filename} -> {new_name}")
                else:
                    files_without_metadata.append(filename)
                    logging.info(f"No metadata found for: {filename}")
            except Exception as exc:
                errors.append(f"{filename} (Error: {str(exc)})")
                logging.error(f"Error renaming {filename}: {exc}", exc_info=True)
        if rename_pairs:
            self.rename_history.append(rename_pairs)
        return renamed_files, files_without_metadata, errors, rename_pairs

    def undo_last_rename(self) -> Tuple[List[Tuple[str, str]], List[str]]:
        if not self.rename_history:
            return [], ["Nothing to undo."]
        last_pairs = self.rename_history.pop()
        undone = []
        errors = []
        for new_path, old_path in reversed(last_pairs):
            try:
                if os.path.exists(new_path):
                    if not os.path.exists(old_path):
                        os.rename(new_path, old_path)
                        undone.append((os.path.basename(new_path), os.path.basename(old_path)))
                        logging.info(f"Undo: {os.path.basename(new_path)} -> {os.path.basename(old_path)}")
                    else:
                        errors.append(f"Target exists: {os.path.basename(old_path)}")
                else:
                    errors.append(f"File not found: {os.path.basename(new_path)}")
            except Exception as e:
                errors.append(f"Error: {os.path.basename(new_path)}: {str(e)}")
                logging.error(f"Error undoing {os.path.basename(new_path)}: {e}", exc_info=True)
        return undone, errors

def get_formatted_name(
    datetime_obj: datetime.datetime,
    filename: str,
    format_str: str,
    prefix: str = "",
    suffix: str = "",
    radio_option: int = 0
) -> str:
    base_name, ext = os.path.splitext(filename)
    new_time = datetime_obj.strftime(format_str)
    if radio_option == 0:
        return f"{prefix}{new_time}{suffix}{ext}"
    elif radio_option == 1:
        return f"{prefix}{new_time}_{base_name}{suffix}{ext}"
    elif radio_option == 2:
        return f"{prefix}{base_name}{suffix}{ext}"
    elif radio_option == 3:
        return f"{prefix}{base_name}_{new_time}{suffix}{ext}"
    return f"{prefix}{new_time}{suffix}{ext}"

# --- Progressbar Helper for GUI ---

class ProgressUpdater:
    def __init__(self, app_ref, total, prefix="", suffix="", decimals=1, length=25, fill='█'):
        self.app_ref = app_ref
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.decimals = decimals
        self.length = length
        self.fill = fill

    def update(self, progress):
        percent = ("{0:." + str(self.decimals) + "f}").format(100 * (progress / float(self.total)))
        filled_length = int(self.length * progress // self.total)
        bar = self.fill * filled_length + '-' * (self.length - filled_length)
        progress_text = f"{self.prefix} |{bar}| {percent}% {self.suffix}"
        self.app_ref.after(0, lambda: self.app_ref.set_status_output(progress_text))

# --- Main GUI Application ---

class ExifRenameXApp(customtkinter.CTk):
    """
    Main application window for EXIFrenameX.
    Handles all GUI components and delegates logic to business logic service classes.
    """
    def __init__(self):
        super().__init__()
        self.title("EXIFrenameX")
        self.geometry("1240x720")
        self.rename_service = RenameService()
        self._build_gui()

    def _build_gui(self):
        # --- LAYOUT ROOT GRID ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure((2, 3), weight=0)
        self.grid_rowconfigure((0, 1, 2), weight=1)

        # --- SIDEBAR (LEFT) ---
        self.sidebar = customtkinter.CTkFrame(self, width=170, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=7, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)

        self.logo_label = customtkinter.CTkLabel(
            self.sidebar, text="EXIFrenameX",
            font=customtkinter.CTkFont(size=22, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(25, 10))

        # Theme and scaling selectors (small)
        font_options = customtkinter.CTkFont(size=12)
        self.appearance_mode_optionmenu = customtkinter.CTkOptionMenu(
            self.sidebar, values=["Light", "Dark", "System"], command=self.change_appearance_mode_event,
            width=90, height=28, font=font_options
        )
        self.appearance_mode_optionmenu.grid(row=7, column=0, padx=20, pady=(7, 5), sticky="ew")

        self.scaling_optionmenu = customtkinter.CTkOptionMenu(
            self.sidebar, values=["80%", "90%", "100%", "110%", "120%"], command=self.change_scaling_event,
            width=90, height=28, font=font_options
        )
        self.scaling_optionmenu.grid(row=8, column=0, padx=20, pady=(2, 18), sticky="ew")

        # --- FORMAT LEGEND (LEFT CENTER) ---
        self.legend_textbox = customtkinter.CTkTextbox(self, width=260)
        self.legend_textbox.grid(row=0, column=1, padx=(20, 0), pady=(20, 0), sticky="nsew")
        self.legend_textbox.insert("0.0", (
            "Format explanation\n\n"
            "- Format 1: %Y-%m-%d_%H-%M-%S\n"
            "- Example: 2023-04-13_14-30-15\n\n"
            "- Format 2: %Y%m%d_%H%M%S\n"
            "- Example: 20230413_143015\n\n"
            "- Format 3: %d-%m-%Y_%Hh%Mm%Ss\n"
            "- Example: 13-04-2023_14h30m15s\n\n"
            "Placeholders:\n"
            "- %Y: year (e.g., 2023)\n"
            "- %m: month (e.g., 01)\n"
            "- %d: day (e.g., 31)\n"
            "- %H: hour (00-23)\n"
            "- %M: minute (00-59)\n"
            "- %S: second (00-59)\n\n"
            "Other options:\n"
            "- %y: 2-digit year\n"
            "- %b, %B: abbreviated/full month name\n"
            "- %a, %A: abbreviated/full weekday name\n"
            "- %I: hour (01-12)\n"
            "- %p: AM/PM\n"
            "- %j: day of the year\n"
            "- %U, %W: week number (Sun/Mon first)\n"
            "- %Z, %z: time zone name/offset\n\n"
            "Combine symbols to create custom formats.")
        )

        # --- STATUS OUTPUT (CENTER LEFT, UNDER LEGEND) ---
        self.status_output_textbox = customtkinter.CTkTextbox(self, width=270)
        self.status_output_textbox.grid(row=1, column=1, padx=(20, 0), pady=(20, 0), sticky="nsew")
        self.set_status_output("File processing status will appear here.")

        # --- FILENAME FORMAT / PREFIX / SUFFIX + UNDO PANEL (TOP RIGHT) ---
        self.format_frame = customtkinter.CTkFrame(self, width=270)
        self.format_frame.grid(row=0, column=2, padx=(20, 0), pady=(20, 0), sticky="nsew")

        self.select_format_label = customtkinter.CTkLabel(
            self.format_frame, text="Select File Name Format", font=customtkinter.CTkFont(weight="bold", size=15)
        )
        self.select_format_label.grid(row=0, column=0, padx=20, pady=(10, 2), sticky="w")

        self.format_combobox = customtkinter.CTkComboBox(
            self.format_frame,
            values=["%Y-%m-%d_%H-%M-%S", "%Y%m%d_%H%M%S", "%d-%m-%Y_%Hh%Mm%Ss"],
            width=240, command=self.on_format_change
        )
        self.format_combobox.grid(row=1, column=0, padx=20, pady=(6, 8))
        self.format_combobox.set("%Y-%m-%d_%H-%M-%S")

        self.prefix_entry = customtkinter.CTkEntry(
            self.format_frame, width=240, placeholder_text="Enter prefix for new names"
        )
        self.prefix_entry.grid(row=2, column=0, padx=20, pady=(2, 8))
        self.prefix_entry.bind("<KeyRelease>", lambda _: self.update_preview())

        self.suffix_entry = customtkinter.CTkEntry(
            self.format_frame, width=240, placeholder_text="Enter suffix for new names"
        )
        self.suffix_entry.grid(row=3, column=0, padx=20, pady=(2, 8))
        self.suffix_entry.bind("<KeyRelease>", lambda _: self.update_preview())

        # --- UNDO BUTTON under File Name Format panel ---
        self.undo_button = customtkinter.CTkButton(
            self.format_frame, text="Undo last Rename", command=self.on_undo_last_rename, state="disabled"
        )
        self.undo_button.grid(row=4, column=0, padx=20, pady=(16, 10), sticky="ew")

        # --- PATTERN/FALLBACK PANEL (TOP RIGHT OUTER) ---
        self.pattern_fallback_frame = customtkinter.CTkFrame(self, width=270)
        self.pattern_fallback_frame.grid(row=0, column=3, padx=(20, 20), pady=(20, 0), sticky="nsew")

        self.naming_pattern_label = customtkinter.CTkLabel(
            master=self.pattern_fallback_frame,
            text="File Name Pattern",
            font=customtkinter.CTkFont(weight="bold", size=15)
        )
        self.naming_pattern_label.grid(row=0, column=0, padx=20, pady=(18, 6), sticky="w")

        self.naming_style_var = tkinter.IntVar(value=0)
        self.naming_style_var.trace_add('write', lambda *args, **kwargs: self.update_preview())
        self.radio_new_only = customtkinter.CTkRadioButton(
            master=self.pattern_fallback_frame, variable=self.naming_style_var, value=0, text="Date only"
        )
        self.radio_new_only.grid(row=1, column=0, pady=(6, 2), padx=30, sticky="w")
        self.radio_new_original = customtkinter.CTkRadioButton(
            master=self.pattern_fallback_frame, variable=self.naming_style_var, value=1, text="Date + Original"
        )
        self.radio_new_original.grid(row=2, column=0, pady=2, padx=30, sticky="w")
        self.radio_original_only = customtkinter.CTkRadioButton(
            master=self.pattern_fallback_frame, variable=self.naming_style_var, value=2, text="Original only"
        )
        self.radio_original_only.grid(row=3, column=0, pady=2, padx=30, sticky="w")
        self.radio_original_new = customtkinter.CTkRadioButton(
            master=self.pattern_fallback_frame, variable=self.naming_style_var, value=3, text="Original + Date"
        )
        self.radio_original_new.grid(row=4, column=0, pady=(2, 12), padx=30, sticky="w")

        self.fallback_label = customtkinter.CTkLabel(
            master=self.pattern_fallback_frame, text="Fallback Options", font=customtkinter.CTkFont(weight="bold", size=13)
        )
        self.fallback_label.grid(row=5, column=0, padx=20, pady=(14, 2), sticky="w")
        self.use_system_time_var = tkinter.BooleanVar(value=True)
        self.system_time_checkbox = customtkinter.CTkCheckBox(
            self.pattern_fallback_frame, text="Use file system timestamp if no metadata",
            variable=self.use_system_time_var, onvalue=True, offvalue=False,
            command=self.on_system_time_option_changed
        )
        self.system_time_checkbox.grid(row=6, column=0, padx=28, pady=(2, 8), sticky="w")

        # --- LIVE PREVIEW OUTPUT (BOTTOM RIGHT) ---
        self.preview_textbox = customtkinter.CTkTextbox(self, width=350)
        self.preview_textbox.grid(row=1, column=2, columnspan=2, padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.set_preview_output("Live preview of renamed files (first 50):\n\n")

        # --- INPUT LINE (FOLDER ENTRY + BUTTONS) ---
        self.input_frame = customtkinter.CTkFrame(self)
        self.input_frame.grid(row=4, column=1, columnspan=3, padx=(20, 20), pady=(10, 10), sticky="nsew")
        self.input_frame.grid_columnconfigure(0, weight=5)
        self.input_frame.grid_columnconfigure(1, weight=1)
        self.input_frame.grid_columnconfigure(2, weight=1)

        self.folder_path_entry = customtkinter.CTkEntry(
            self.input_frame, placeholder_text="Select or enter target directory for renaming"
        )
        self.folder_path_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        self.folder_path_entry.bind("<KeyRelease>", lambda _: self.update_preview())
        self.folder_path_entry.bind("<<Paste>>", lambda _: self.update_preview())

        self.browse_button = customtkinter.CTkButton(
            self.input_frame, fg_color="transparent", border_width=2,
            text_color=("gray10", "#DCE4EE"), text="Browse", command=self.browse_directory, width=100, height=36
        )
        self.browse_button.grid(row=0, column=1, padx=(0, 5), pady=10, sticky="ew")

        self.rename_files_button_input = customtkinter.CTkButton(
            self.input_frame, text="Rename Files", command=self.on_rename_files_click, width=110, height=36
        )
        self.rename_files_button_input.grid(row=0, column=2, padx=(0, 10), pady=10, sticky="ew")

        # Initial settings
        self.appearance_mode_optionmenu.set("Dark")
        self.scaling_optionmenu.set("100%")
        self.format_combobox.set("%Y-%m-%d_%H-%M-%S")

    # --- GUI EVENTS & UTILITIES ---
    def set_status_output(self, text: str):
        self.status_output_textbox.delete("0.0", tkinter.END)
        self.status_output_textbox.insert("0.0", text)

    def set_preview_output(self, text: str):
        self.preview_textbox.delete("0.0", tkinter.END)
        self.preview_textbox.insert("0.0", text)

    def update_undo_button_text(self):
        steps = len(self.rename_service.rename_history)
        steps_str = " ".join(str(i+1) for i in range(steps))
        if steps:
            self.undo_button.configure(
                text=f"Undo last Rename ({steps_str})",
                state="normal"
            )
        else:
            self.undo_button.configure(
                text="Undo last Rename",
                state="disabled"
            )

    def on_format_change(self, *_):
        self.update_preview()

    def on_rename_files_click(self):
        folder_path = self.folder_path_entry.get()
        if not os.path.exists(folder_path):
            self.set_status_output("Please select a valid folder path.\n")
            return
        use_fallback = self.use_system_time_var.get()
        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
        naming_settings = {
            "format_str": self.format_combobox.get(),
            "prefix": self.prefix_entry.get(),
            "suffix": self.suffix_entry.get(),
            "radio_option": self.naming_style_var.get()
        }
        progress_updater = ProgressUpdater(self, len(files))

        def process_files():
            renamed_files, files_without_metadata, errors, rename_pairs = self.rename_service.rename_files(
                folder_path, files, naming_settings, use_fallback
            )
            for idx in range(len(files)):
                progress_updater.update(idx + 1)
            def final_report():
                summary = ""
                if renamed_files:
                    summary += "Renamed files:\n" + "\n".join(f"-> {f}" for f in renamed_files) + "\n"
                if files_without_metadata:
                    summary += "\nFiles without valid metadata (kept original name):\n"
                    summary += "\n".join(f"-> {f}" for f in files_without_metadata) + "\n"
                if errors:
                    summary += "\nErrors encountered:\n" + "\n".join(errors)
                if not summary:
                    summary = "No files processed or renamed."
                self.update_undo_button_text()
                self.set_status_output(summary)
            self.after(0, final_report)
        threading.Thread(target=process_files, daemon=True).start()

    def on_undo_last_rename(self):
        def undo_renames():
            undone, errors = self.rename_service.undo_last_rename()
            def undo_report():
                summary = "Undo Report:\n"
                if undone:
                    summary += "\n".join(f"{src} -> {dst}" for src, dst in undone) + "\n"
                if errors:
                    summary += "\nErrors:\n" + "\n".join(errors)
                self.update_undo_button_text()
                self.set_status_output(summary)
                self.update_preview()
            self.after(0, undo_report)
        threading.Thread(target=undo_renames, daemon=True).start()

    def update_preview(self):
        try:
            folder_path = self.folder_path_entry.get()
            if not os.path.exists(folder_path):
                self.set_preview_output("Please select a folder path.\n")
                return
            use_fallback = self.use_system_time_var.get()
            preview_lines = []
            file_count = 0
            naming_settings = {
                "format_str": self.format_combobox.get(),
                "prefix": self.prefix_entry.get(),
                "suffix": self.suffix_entry.get(),
                "radio_option": self.naming_style_var.get()
            }
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                if os.path.isfile(file_path):
                    date_obj = MediaMetadataService.get_best_date(file_path, use_fallback=use_fallback)
                    if date_obj:
                        new_name = get_formatted_name(
                            date_obj, filename,
                            format_str=naming_settings["format_str"],
                            prefix=naming_settings["prefix"],
                            suffix=naming_settings["suffix"],
                            radio_option=naming_settings["radio_option"]
                        )
                        preview_lines.append(f"{filename} -> {new_name}")
                    else:
                        preview_lines.append(f"{filename} -> no rename (no date found)")
                    file_count += 1
                    if file_count >= 50:
                        break
            if preview_lines:
                self.set_preview_output("Live preview of renamed files (first 50):\n\n" + "\n".join(preview_lines))
            else:
                self.set_preview_output("No files to preview in this directory.\n")
        except Exception as e:
            self.set_status_output(f"Error updating preview: {str(e)}\n")
            logging.error(f"Error updating preview: {e}", exc_info=True)

    def browse_directory(self):
        folder_path = tkinter.filedialog.askdirectory()
        self.folder_path_entry.delete(0, tkinter.END)
        self.folder_path_entry.insert(0, folder_path)
        self.update_preview()

    def on_system_time_option_changed(self):
        self.update_preview()

    def change_appearance_mode_event(self, new_appearance_mode: str):
        customtkinter.set_appearance_mode(new_appearance_mode)

    def change_scaling_event(self, new_scaling: str):
        customtkinter.set_widget_scaling(int(new_scaling.replace("%", "")) / 100)

# --- App Entry Point ---

if __name__ == "__main__":
    try:
        app = ExifRenameXApp()
        app.mainloop()
    except KeyboardInterrupt:
        print("App terminated by user.")
