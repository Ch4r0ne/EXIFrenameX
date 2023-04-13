import os
import exifread
import pymediainfo
import datetime
import threading 
from tkinter import filedialog
from tkinter import ttk
from tkinter import *

class ProgressUpdater:
    def __init__(self, total, prefix="", suffix="", decimals=1, length=100, fill='█', print_end="\r"):
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.decimals = decimals
        self.length = length
        self.fill = fill
        self.print_end = print_end
        self.progress = 0

    def update(self, progress):
        self.progress = progress
        percent = ("{0:." + str(self.decimals) + "f}").format(100 * (self.progress / float(self.total)))
        filled_length = int(self.length * self.progress // self.total)
        bar = self.fill * filled_length + '-' * (self.length - filled_length)
        output.config(state=NORMAL)
        output.delete(1.0, END)
        output.insert(INSERT, f'{self.prefix} |{bar}| {percent}% {self.suffix} - Processed files: {self.progress}/{self.total}\n')
        output.see(END)
        output.config(state=DISABLED)
        root.update_idletasks()

# function to extract date from exif tags of .jpeg, .jpg, .png, ... files
def get_exif_date(file_path):
    with open(file_path, 'rb') as f:
        tags = exifread.process_file(f)
        if 'EXIF DateTimeOriginal' in tags:
            date_str = str(tags['EXIF DateTimeOriginal'])
            return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
        elif 'EXIF DateTime' in tags:
            date_str = str(tags['EXIF DateTime'])
            return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
        else:
            return None

# function to extract date from metadata of .mov and .mp4 files
def get_media_date(file_path):
    media_info = pymediainfo.MediaInfo.parse(file_path)
    for track in media_info.tracks:
            if 'comapplequicktimecreationdate' in track.to_data():
                date_str = track.to_data()['comapplequicktimecreationdate']
                date_str = date_str.replace('T', ' ').split('+')[0]
                return datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            elif 'recorded_date' in track.to_data():
                date_str = track.to_data()['recorded_date']
                date_str = date_str.replace('T', ' ').split('+')[0]
                return datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            elif 'encoded_date' in track.to_data():
                date_str = track.to_data()['encoded_date']
                return datetime.datetime.strptime(date_str, 'UTC %Y-%m-%d %H:%M:%S')
            else:
                return None

def start_script():
    output.config(state=NORMAL)
    output.delete(1.0, END)

    folder = folder_path.get()
    output.insert(INSERT, f"Process files in the folder: {folder}\n")

    renamed_files = []
    files_without_metadata = []
    
    files = os.listdir(folder)
    progress_updater = ProgressUpdater(total=len(files), prefix='Rename files:', suffix='', length=50)
    for i, filename in enumerate(files):
        progress_updater.update(i+1)


        file_path = os.path.join(folder, filename)
        if os.path.isfile(file_path):
            extension = os.path.splitext(file_path)[1].lower()
            if extension in ['.jpg', '.jpeg', '.png', '.arw', '.nef', '.tiff', '.webp', '.bmp', '.cr2', '.orf', '.rw2', '.rwl', '.srw']:
                datetime_obj = get_exif_date(file_path)
            elif extension in ['.mov', '.mp4']:
                datetime_obj = get_media_date(file_path)
            else:
                datetime_obj = None

            if datetime_obj is not None:
                new_name = datetime_obj.strftime(selected_format.get()) + extension
                # check if new name already exists, if yes, add an incremental number
                if new_name in renamed_files:
                    i = 1
                    while new_name in renamed_files:
                        new_name = datetime_obj.strftime("%Y-%m-%d_%H-%M-%S") + '_' + str(i) + extension
                        i += 1
                try:
                    os.rename(file_path, os.path.join(folder_path.get(), new_name))
                    renamed_files.append(new_name)
                except FileExistsError:
                    i += 1
                    new_name = datetime_obj.strftime("%Y-%m-%d_%H-%M-%S") + '_' + str(i) + extension
                    os.rename(file_path, os.path.join(folder_path.get(), new_name))
                    renamed_files.append(new_name)
            else:
                files_without_metadata.append(filename)
                output.config(state=NORMAL)
                output.insert(INSERT, f"File '{filename}' could not be renamed (no metadata found).\n")
                output.see(END)
                output.config(state=DISABLED)
                root.update_idletasks()

def browse_folder():
    global folder_path
    folder_path.set(filedialog.askdirectory())

def update_file_preview():
    def generate_preview():
        preview.config(state=NORMAL)
        preview.delete(1.0, END)
        folder = folder_path.get()
        counter = 0
        if os.path.isdir(folder):
            for filename in os.listdir(folder):
                if counter >= 100:
                    break
                file_path = os.path.join(folder, filename)
                if os.path.isfile(file_path):
                    extension = os.path.splitext(file_path)[1].lower()
                    if extension in ['.jpg', '.jpeg', '.png', '.arw', '.nef', '.tiff', '.webp', '.bmp', '.cr2', '.orf', '.rw2', '.rwl', '.srw']:
                        datetime_obj = get_exif_date(file_path)
                    elif extension in ['.mov', '.mp4']:
                        datetime_obj = get_media_date(file_path)
                    else:
                        datetime_obj = None

                    if datetime_obj is not None:
                        new_name = datetime_obj.strftime(selected_format.get()) + extension
                    else:
                        new_name = filename
                    preview.insert(INSERT, new_name + "\n")
                    counter += 1
        preview.config(state=DISABLED)

    preview_thread = threading.Thread(target=generate_preview)
    preview_thread.start()

def show_format_hints():
    hints_window = Toplevel(root)
    hints_window.geometry("300x350")
    hints_window.configure(bg=BG_COLOR)
    hints_window.title("Format Hints")
    
    hints_text = """Format Placeholder Meanings:

    - Format 1: %Y-%m-%d_%H-%M-%S
    - Example: 2023-04-13_14-30-15
    
    - Format 2: %Y%m%d_%H%M%S
    - Example: 20230413_143015
    
    - Format 3: %d-%m-%Y_%Hh%Mm%Ss
    - Example: 13-04-2023_14h30m15s
    
    Placeholders:
    %Y - 4-digit year (e.g., 2023)
    %m - 2-digit month with leading zero (e.g., 04)
    %d - 2-digit day with leading zero (e.g., 13)
    %H - 2-digit hour with leading zero (e.g., 14)
    %M - 2-digit minute with leading zero (e.g., 30)
    %S - 2-digit second with leading zero (e.g., 15)
    """
    
    hints_label = Label(hints_window, text=hints_text, bg=BG_COLOR, fg=FG_COLOR, justify=LEFT)
    hints_label.pack(padx=10, pady=10)

BG_COLOR = "#303030"
FG_COLOR = "#F0F0F0"
BUTTON_COLOR = "#4a86e8"

root = Tk()
root.title("EXIFrenameX")
root.geometry("1050x550")
root.configure(bg=BG_COLOR)

folder_path = StringVar()
selected_format = StringVar()

left_frame = Frame(root, bg=BG_COLOR)
left_frame.pack(side=LEFT, fill=Y, padx=10)

Label(left_frame, text="Select folder:", bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, padx=10, pady=10, sticky=W)

Entry(left_frame, textvariable=folder_path).grid(row=1, column=0, padx=10, pady=5, sticky=W+E)
Button(left_frame, text="Browse", command=lambda: [browse_folder(), update_file_preview()], bg=BUTTON_COLOR, fg=FG_COLOR, width=10).grid(row=2, column=0, padx=10, pady=5, sticky=W)

selected_format = StringVar(value="%Y-%m-%d_%H-%M-%S")

Label(left_frame, text="Select format:", bg=BG_COLOR, fg=FG_COLOR).grid(row=3, column=0, padx=8, pady=8, sticky=W)
format_options = ["%Y-%m-%d_%H-%M-%S", "%Y%m%d_%H%M%S", "%d-%m-%Y_%Hh%Mm%Ss"]
dropdown = ttk.Combobox(left_frame, values=format_options, textvariable=selected_format, state="normal", width=18)
dropdown.grid(row=4, column=0, padx=10, pady=5, sticky=W+E)

selected_format.trace_add("write", lambda *args: update_file_preview())

Button(left_frame, text="Format Hints", command=show_format_hints, bg=BUTTON_COLOR, fg=FG_COLOR, width=10).grid(row=5, column=0, padx=8, pady=5, sticky=W)

Button(left_frame, text="Rename All", command=start_script, bg=BUTTON_COLOR, fg=FG_COLOR, width=18).grid(row=6, column=0, padx=10, pady=5, sticky='EW')

Label(left_frame, text="Processing output", bg=BG_COLOR, fg=FG_COLOR).grid(row=7, column=0, padx=10, pady=10, sticky=W)
output = Text(left_frame, wrap=WORD, state=DISABLED, bg=BG_COLOR, fg=FG_COLOR)
output.grid(row=8, column=0, padx=10, pady=5, sticky=W+E+N+S)

left_frame.grid_rowconfigure(8, weight=1)
left_frame.grid_columnconfigure(0, weight=1)

preview_frame = Frame(root, bg=BG_COLOR)
preview_frame.pack(side=LEFT, fill=BOTH, expand=1)

Label(preview_frame, text="File preview:", bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, sticky=W, padx=10, pady=10)

preview = Text(preview_frame, wrap=WORD, state=DISABLED, bg=BG_COLOR, fg=FG_COLOR)
preview.grid(row=1, column=0, sticky=N+S+E+W, padx=10, pady=5)
preview_scrollbar = Scrollbar(preview_frame, command=preview.yview)
preview_scrollbar.grid(row=1, column=1, sticky=N+S, padx=5, pady=5)
preview.config(yscrollcommand=preview_scrollbar.set)

preview_frame.grid_rowconfigure(1, weight=2)
preview_frame.grid_columnconfigure(0, weight=2)

root.mainloop()
