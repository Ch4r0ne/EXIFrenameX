import os
import exifread
import pymediainfo
import datetime
import threading 
from tkinter import filedialog
from tkinter import ttk
from tkinter import *
from tqdm import tqdm

class TqdmOutput:
    def write(self, s):
        if s.rstrip() != "":
            output.config(state=NORMAL)
            output.insert(INSERT, s)
            output.see(END)
            output.config(state=DISABLED)
            root.update_idletasks()

    def flush(self):
        pass

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
    
    for filename in tqdm(os.listdir(folder), desc="Rename files", unit="file", file=TqdmOutput()):
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

BG_COLOR = "#303030"
FG_COLOR = "#F0F0F0"
BUTTON_COLOR = "#4a86e8"

root = Tk()
root.title("EXIFrenameX")
root.geometry("1100x600")
root.configure(bg=BG_COLOR)

folder_path = StringVar()
selected_format = StringVar()

left_frame = Frame(root, bg=BG_COLOR)
left_frame.pack(side=LEFT, fill=BOTH, expand=1)

Label(left_frame, text="Select folder:", bg=BG_COLOR, fg=FG_COLOR).pack(anchor=NW, padx=10, pady=10)
Entry(left_frame, textvariable=folder_path).pack(fill=X, padx=10, pady=5)
Button(left_frame, text="Browse", command=lambda: [browse_folder(), update_file_preview()], bg=BUTTON_COLOR, fg=FG_COLOR).pack(fill=X, padx=10, pady=5)

selected_format = StringVar(value="%Y-%m-%d_%H-%M-%S")

Label(left_frame, text="Select format:", bg=BG_COLOR, fg=FG_COLOR).pack(anchor=NW, padx=10, pady=10)
format_options = ["%Y-%m-%d_%H-%M-%S", "%Y%m%d_%H%M%S", "%d-%m-%Y_%Hh%Mm%Ss"]
dropdown = ttk.Combobox(left_frame, values=format_options, textvariable=selected_format, state="normal")
dropdown.pack(fill=X, padx=10, pady=5)

selected_format.trace_add("write", lambda *args: update_file_preview())

Button(left_frame, text="Start script", command=start_script, bg=BUTTON_COLOR, fg=FG_COLOR).pack(fill=X, padx=10, pady=5)

right_frame = Frame(root, bg=BG_COLOR)
right_frame.pack(side=LEFT, fill=BOTH, expand=1)

Label(right_frame, text="Processing output", bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, sticky=W, padx=10, pady=10)

output = Text(right_frame, wrap=WORD, state=DISABLED, bg=BG_COLOR, fg=FG_COLOR)
output.grid(row=1, column=0, sticky=N+S+E+W, padx=10, pady=5)

right_frame.grid_rowconfigure(1, weight=1)
right_frame.grid_columnconfigure(0, weight=1)

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
