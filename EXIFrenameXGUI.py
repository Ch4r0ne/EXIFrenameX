import os
import exifread
import pymediainfo
import datetime
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
    output.insert(INSERT, f"Verarbeite Dateien im Ordner: {folder}\n")

    renamed_files = []
    files_without_metadata = []
    
    for filename in tqdm(os.listdir(folder), desc="Dateien umbenennen", unit="file", file=TqdmOutput()):
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

root = Tk()
root.title("EXIFrenameX")
root.geometry("800x400")
root.configure(bg='#D3D3D3')

folder_path = StringVar()
selected_format = StringVar()

left_frame = Frame(root, bg='#D3D3D3')
left_frame.pack(side=LEFT, fill=BOTH, expand=1)

# Change text colours and background colours accordingly
Label(left_frame, text="Ordner auswählen:", bg='#D3D3D3', fg='#000000').pack(anchor=NW, padx=5, pady=5)
Entry(left_frame, textvariable=folder_path).pack(fill=X, padx=5, pady=5)
Button(left_frame, text="Durchsuchen", command=browse_folder, bg='#A9A9A9', fg='#000000').pack(fill=X, padx=5, pady=5)

Label(left_frame, text="Format auswählen:", bg='#D3D3D3', fg='#000000').pack(anchor=NW, padx=5, pady=5)
format_options = ["%Y-%m-%d_%H-%M-%S", "%Y%m%d_%H%M%S", "%d-%m-%Y_%Hh%Mm%Ss"]
dropdown = ttk.Combobox(left_frame, values=format_options, textvariable=selected_format, state="normal")
dropdown.pack(fill=X, padx=5, pady=5)

Button(left_frame, text="Skript starten", command=start_script, bg='#A9A9A9', fg='#000000').pack(fill=X, padx=5, pady=5)

right_frame = Frame(root, bg='#D3D3D3')
right_frame.pack(side=RIGHT, fill=BOTH, expand=1)

Label(right_frame, text="CMD-Ausgabe:", bg='#D3D3D3', fg='#000000').pack(anchor=NW, padx=5, pady=5)

output = Text(right_frame, wrap=WORD, state=DISABLED, bg='#A9A9A9', fg='#000000')
output.pack(fill=BOTH, expand=1, padx=5, pady=5)
scrollbar = Scrollbar(right_frame, command=output.yview)
scrollbar.pack(side=RIGHT, fill=Y)
output.config(yscrollcommand=scrollbar.set)

root.mainloop()
