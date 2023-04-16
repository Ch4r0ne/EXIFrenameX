import os
import exifread
import pymediainfo
import datetime
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import customtkinter
import threading

customtkinter.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
customtkinter.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        # configure window
        self.title("EXIFrenameX")
        self.geometry(f"{1100}x{580}")

        # configure grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure((2, 3), weight=0)
        self.grid_rowconfigure((0, 1, 2), weight=1)

        # create GUI
        self.sidebar_frame = customtkinter.CTkFrame(self, width=140, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        self.logo_label = customtkinter.CTkLabel(self.sidebar_frame, text="EXIFrenameX", font=customtkinter.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.sidebar_button_1 = customtkinter.CTkButton(self.sidebar_frame, command=self.sidebar_button_event)
        self.sidebar_button_1.grid(row=1, column=0, padx=20, pady=10)
        self.sidebar_button_1.configure(text="Rename Files", command=self.on_sidebar_button_1_click)
        #self.sidebar_button_1.bind("<ButtonRelease-1>", lambda _: self.update_preview())
        self.appearance_mode_optionemenu = customtkinter.CTkOptionMenu(self.sidebar_frame, values=["Light", "Dark", "System"], command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=7, column=0, padx=20, pady=(10, 10))
        self.scaling_optionemenu = customtkinter.CTkOptionMenu(self.sidebar_frame, values=["80%", "90%", "100%", "110%", "120%"], command=self.change_scaling_event)
        self.scaling_optionemenu.grid(row=8, column=0, padx=20, pady=(10, 20))
        self.entry = customtkinter.CTkEntry(self, placeholder_text="Brows File Pfad")
        self.entry.grid(row=3, column=1, columnspan=2, padx=(20, 0), pady=(20, 20), sticky="nsew")
        self.main_button_1 = customtkinter.CTkButton(master=self, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), text="Browse", command=self.browse_directory)
        self.main_button_1.grid(row=3, column=3, padx=(20, 20), pady=(20, 20), sticky="nsew")
        self.textbox_1 = customtkinter.CTkTextbox(self, width=250)
        self.textbox_1.grid(row=0, column=1, padx=(20, 0), pady=(20, 0), sticky="nsew")
        self.format_frame = customtkinter.CTkFrame(self, width=250)
        self.format_frame.grid(row=0, column=2, padx=(20, 0), pady=(20, 0), sticky="nsew")
        self.select_format_label = customtkinter.CTkLabel(self.format_frame, text="Select Format")
        self.select_format_label.grid(row=0, column=0, padx=20, pady=(10, 10), sticky="w")
        self.combobox_1 = customtkinter.CTkComboBox(self.format_frame, values=["%Y-%m-%d_%H-%M-%S", "%Y%m%d_%H%M%S", "%d-%m-%Y_%Hh%Mm%Ss"], width=240)
        self.combobox_1.grid(row=1, column=0, padx=20, pady=(10, 10))
        #self.combobox_1.bind("<<ComboboxSelected>>", lambda _: self.update_preview())
        self.entry_2 = customtkinter.CTkEntry(self.format_frame, width=240, placeholder_text="Enter Prefix here")
        self.entry_2.grid(row=2, column=0, padx=20, pady=(10, 10))
        self.entry_2.bind("<KeyRelease>", lambda _: self.update_preview())
        self.entry_3 = customtkinter.CTkEntry(self.format_frame, width=240, placeholder_text="Enter Suffix here")
        self.entry_3.grid(row=3, column=0, padx=20, pady=(10, 10))
        self.entry_3.bind("<KeyRelease>", lambda _: self.update_preview())
        self.update_button = customtkinter.CTkButton(self.format_frame, text="Update Preview", command=self.update_preview)
        self.update_button.grid(row=4, column=0, padx=20, pady=(10, 10), sticky="nsew")
        self.radiobutton_frame = customtkinter.CTkFrame(self)
        self.radiobutton_frame.grid(row=0, column=3, padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.radio_var = tkinter.IntVar(value=0)
        self.radio_var.trace_add('write', lambda *args, **kwargs: self.update_preview())
        self.label_radio_group = customtkinter.CTkLabel(master=self.radiobutton_frame, text="Select merge:")
        self.label_radio_group.grid(row=0, column=2, columnspan=1, padx=10, pady=10, sticky="w")
        self.radio_button_1 = customtkinter.CTkRadioButton(master=self.radiobutton_frame, variable=self.radio_var, value=0)
        self.radio_button_1.grid(row=1, column=2, pady=10, padx=20, sticky="w")
        self.radio_button_2 = customtkinter.CTkRadioButton(master=self.radiobutton_frame, variable=self.radio_var, value=1)
        self.radio_button_2.grid(row=2, column=2, pady=10, padx=20, sticky="w")
        self.radio_button_3 = customtkinter.CTkRadioButton(master=self.radiobutton_frame, variable=self.radio_var, value=2)
        self.radio_button_3.grid(row=3, column=2, pady=10, padx=20, sticky="w")
        self.radio_button_4 = customtkinter.CTkRadioButton(master=self.radiobutton_frame, variable=self.radio_var, value=3)
        self.radio_button_4.grid(row=4, column=2, pady=10, padx=20, sticky="w")
        self.textbox_2 = customtkinter.CTkTextbox(self, width=250)
        self.textbox_2.grid(row=1, column=1, padx=(20, 0), pady=(20, 0), sticky="nsew")
        self.textbox_3 = customtkinter.CTkTextbox(self, width=250)
        self.textbox_3.grid(row=1, column=2, columnspan=2, padx=(20, 20), pady=(20, 0), sticky="nsew")

        # set default values
        self.sidebar_button_1.configure(text="Rename Files")
        self.radio_button_1.configure(text="New")
        self.radio_button_1.select()
        self.radio_button_2.configure(text="New + Orginal")
        self.radio_button_3.configure(text="Orginal")
        self.radio_button_4.configure(text="Orginal + New")
        self.appearance_mode_optionemenu.set("Dark")
        self.scaling_optionemenu.set("100%")
        self.textbox_1.insert("0.0", "Format explanation\n\n"
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

        self.textbox_2.insert("0.0", "File processing: \n")
        self.textbox_3.insert("0.0", "Preview of Files (0-49):\n\n")

    # function to extract date from exif tags of .jpeg, .jpg, .png, ... files
    def get_exif_date(self, file_path):
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
    def get_media_date(self, file_path):
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
                           
    def on_sidebar_button_1_click(self):
        folder_path = self.entry.get()
        if not os.path.exists(folder_path):
            self.textbox_2.delete("0.0", tkinter.END)
            self.textbox_2.insert("0.0", "Please select a folder path\n\n")
            return

        def process_files():
            renamed_files = []
            files_without_metadata = []
            progress_updater = ProgressUpdater(self, 0)
            progress_updater.total = len(os.listdir(folder_path))
            for index, filename in enumerate(os.listdir(folder_path)):
                file_path = os.path.join(folder_path, filename)
                if os.path.isfile(file_path):
                    extension = os.path.splitext(file_path)[1].lower()
                    if extension in ['.jpg', '.jpeg', '.png', '.arw', '.nef', '.tiff', '.webp', '.bmp', '.cr2', '.orf', '.rw2', '.rwl', '.srw']:
                        datetime_obj = self.get_exif_date(file_path)
                    elif extension in ['.mov', '.mp4']:
                        datetime_obj = self.get_media_date(file_path)
                    else:
                        datetime_obj = None
                    if datetime_obj is not None:
                        new_name = self.get_formatted_date(datetime_obj, filename, index=index) + extension
                        if new_name in renamed_files:
                            i = 1
                            while new_name in renamed_files:
                                new_name = self.get_formatted_date(datetime_obj, filename, index=index) + '_' + str(i) + extension
                                i += 1
                        try:
                            os.rename(file_path, os.path.join(folder_path, new_name))
                            renamed_files.append(new_name)
                        except FileExistsError:
                            i += 1
                            new_name = self.get_formatted_date(datetime_obj, filename, index=index) + '_' + str(i) + extension
                            os.rename(file_path, os.path.join(folder_path, new_name))
                            renamed_files.append(new_name)
                    else:
                        files_without_metadata.append(filename)

                progress_updater.update(index+1)
            self.textbox_2.delete("3.0", tkinter.END)
            if len(files_without_metadata) > 0:
                self.textbox_2.insert("3.0", f"\n\nFiles without Metadata have not been renamed:\n")
                for name in files_without_metadata:
                    self.textbox_2.insert(tkinter.END, f"-> File: {name}\n")

            if len(renamed_files) > 0:
                if len(files_without_metadata) > 0:
                    self.textbox_2.insert(tkinter.END, f"\n\nRename Successfully:\n")
                else:
                    self.textbox_2.insert("3.0", f"\n\nRename Successfully:\n")
                for name in renamed_files:
                    self.textbox_2.insert(tkinter.END, f"-> File: {name}\n")
            else:
                if len(files_without_metadata) == 0:
                    self.textbox_2.insert("3.0", f"\n\nRename Successfully:\n")

        processing_thread = threading.Thread(target=process_files)
        processing_thread.start()

    def update_preview(self):
        try:
            folder_path = app.entry.get()
            if not os.path.exists(folder_path):
                app.textbox_3.delete("0.0", tkinter.END)
                app.textbox_3.insert("0.0", "Please select a folder path\n\n")
                return
            app.textbox_3.delete("0.0", tkinter.END)
            app.textbox_3.insert("0.0", "Preview of Files (0-49):\n\n")
            file_count = 0
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                if os.path.isfile(file_path):
                    extension = os.path.splitext(file_path)[1].lower()
                    if extension in ['.jpg', '.jpeg', '.png', '.arw', '.nef', '.tiff', '.webp', '.bmp', '.cr2', '.orf', '.rw2', '.rwl', '.srw']:
                        datetime_obj = self.get_exif_date(file_path)
                    elif extension in ['.mov', '.mp4']:
                        datetime_obj = self.get_media_date(file_path)
                    else:
                        datetime_obj = None
                    if datetime_obj is not None:
                        new_name = self.get_formatted_date(datetime_obj, filename) + extension
                        app.textbox_3.insert(tkinter.END, f"{filename} -> {new_name}\n")
                        file_count += 1
                        if file_count >= 50:
                            break
        except Exception as e:
            if hasattr(app, 'textbox_2'):  # check if textbox_2 exists
                app.textbox_2.insert("0.0", f"Error: {str(e)}\n\n")
                
    def get_formatted_date(self, datetime_obj, filename, index=None):
        format_str = self.combobox_1.get()
        prefix = self.entry_2.get()
        suffix = self.entry_3.get()
        base_name = os.path.splitext(filename)[0]

        radio_option = self.radio_var.get()

        if radio_option == 0:  # New
            return f"{prefix}{datetime_obj.strftime(format_str)}{suffix}"
        elif radio_option == 1:  # New + Original
            return f"{prefix}{datetime_obj.strftime(format_str)}_{base_name}{suffix}"
        elif radio_option == 2:  # Original
            return f"{prefix}{base_name}{suffix}"
        elif radio_option == 3:  # Original + New
            return f"{prefix}{base_name}_{datetime_obj.strftime(format_str)}{suffix}"
        else:
            return None

    def update_textbox_2(self, progress_text):
        self.textbox_2.delete("0.0", tkinter.END)
        self.textbox_2.insert("0.0", progress_text)

    def browse_directory(self):
        folder_path = tkinter.filedialog.askdirectory()
        self.entry.delete(0, tkinter.END)
        self.entry.insert(0, folder_path)
        self.update_preview()

    def open_input_dialog_event(self):
        dialog = customtkinter.CTkInputDialog(text="Type in a number:", title="CTkInputDialog")
        print("CTkInputDialog:", dialog.get_input())

    def change_appearance_mode_event(self, new_appearance_mode: str):
        customtkinter.set_appearance_mode(new_appearance_mode)

    def change_scaling_event(self, new_scaling: str):
        new_scaling_float = int(new_scaling.replace("%", "")) / 100
        customtkinter.set_widget_scaling(new_scaling_float)

    def sidebar_button_event(self):
        pass

class ProgressUpdater:
    def __init__(self, app, total, prefix="", suffix="", decimals=1, length=25, fill='█', print_end="\r"):
        self.app = app
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
        percent = ("{0:." + str(self.decimals) + "f}").format(100 * (progress / float(self.total)))
        filled_length = int(self.length * progress // self.total)
        bar = self.fill * filled_length + '-' * (self.length - filled_length)
        progress_text = f"{self.prefix} |{bar}| {percent}% {self.suffix}"
        app.update_textbox_2(progress_text)
        
if __name__ == "__main__":
    app = App()
    app.mainloop()