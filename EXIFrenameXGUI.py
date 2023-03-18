import os
import exifread
import pymediainfo
import datetime
from tqdm import tqdm
import tkinter as tk
from tkinter import filedialog

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

def process_files():
    folder_path = folder_entry.get()
    renamed_files = []
    files_without_metadata = []

    # iterate over all files in the folder
    renamed_files = []
    files_without_metadata = []
    for filename in tqdm(os.listdir(folder_path)):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            extension = os.path.splitext(file_path)[1].lower()
            if extension in ['.jpg', '.jpeg', '.png', '.arw', '.nef', '.tiff', '.webp', '.bmp', '.cr2', '.orf', '.rw2', '.rwl', '.srw']:
                datetime_obj = get_exif_date(file_path)
            elif extension in ['.mov', '.mp4']:
                datetime_obj = get_media_date(file_path)
            else:
                datetime_obj = None

            if datetime_obj is not None:
                new_name = datetime_obj.strftime("%Y-%m-%d_%H-%M-%S") + extension
                # check if new name already exists, if yes, add an incremental number
                if new_name in renamed_files:
                    i = 1
                    while new_name in renamed_files:
                        new_name = datetime_obj.strftime("%Y-%m-%d_%H-%M-%S") + '_' + str(i) + extension
                        i += 1
                try:
                    os.rename(file_path, os.path.join(folder_path, new_name))
                    renamed_files.append(new_name)
                except FileExistsError:
                    i += 1
                    new_name = datetime_obj.strftime("%Y-%m-%d_%H-%M-%S") + '_' + str(i) + extension
                    os.rename(file_path, os.path.join(folder_path, new_name))
                    renamed_files.append(new_name)
            else:
                files_without_metadata.append(filename)

    # Update the status label
    status_label.config(text="All files with metadata were successfully renamed.")
    if files_without_metadata:
        status_label.config(text="Some files could not be renamed due to missing metadata.")

def open_folder():
    folder_path = filedialog.askdirectory()
    folder_entry.delete(0, tk.END)
    folder_entry.insert(0, folder_path)

# Create the main window
root = tk.Tk()
root.title("File Renamer")

# Create the layout
folder_label = tk.Label(root, text="Folder Path:")
folder_label.grid(row=0, column=0, padx=10, pady=10, sticky="e")

folder_entry = tk.Entry(root, width=50)
folder_entry.grid(row=0, column=1, padx=10, pady=10, sticky="w")

browse_button = tk.Button(root, text="Browse", command=open_folder)
browse_button.grid(row=0, column=2, padx=10, pady=10)

rename_button = tk.Button(root, text="Rename Files", command=process_files)
rename_button.grid(row=1, column=0, columnspan=3, pady=10)

status_label = tk.Label(root, text="")
status_label.grid(row=2, column=0, columnspan=3, pady=10)

# Start the main GUI loop
root.mainloop()
