# Image and Video File Renamer

This script allows you to easily rename image and video files in a specified folder using their metadata information. It is a quick and convenient way to organize your media files by their creation or recording date.


## Features

  - Renames image files using the 'EXIF DateTimeOriginal' field
  - Renames video files using the 'recorded_date' field for MP4 files or the 'comapplequicktimecreationdate' field for MOV files
  - Falls back to the 'recorded_date' field if the 'comapplequicktimecreationdate' field is not present for MOV files
  - Handles any errors that may occur while processing the files
  - Supports various image file formats including .jpg, .jpeg, .png, .arw, .nef, .tiff, .webp, .bmp, .cr2, .orf, .rw2, .rwl, and .srw
  - Supports MP4 and MOV video file formats
  
## Using the Exifrenamer

Follow these steps to use the Exifrenamer script:

    1. Download the Exifrenamer.zip file from the "Releases" section of the GitHub repository.
    2. Unpack the .zip file to access the Exifrenamer folder.
    3. Navigate to the Exifrenamer folder and double-click on the Exifrenamer.exe file to launch the script.
    4. When prompted, enter the path to the folder containing the image and video files you want to rename.
    5. The script will process the files and attempt to rename them using the metadata information.
    6. Upon completion, the script will display the number of files successfully renamed and the number of files not renamed.


# Development requirements
## Requirements

    Python 3
    exifread library
    pymediainfo library

## Usage

    Install Python 3
    Install the required libraries: pip install exifread pymediainfo
    Run the script: Exifrenamer.py
    When prompted, enter the path to the folder containing the image and video files
    
## How to repack the .py script

1. Install PyInstaller: ```pip install pyinstaller```
2. Navigate to the script's directory: ```cd path/to/script/directory```
3. Repack the script: ```pyinstaller Exifrenamer.py```
4. If necessary, include any external dependencies using the --add-data flag:
   ```pyinstaller Exifrenamer.py --add-data "exifread;exifread" --add-data "pymediainfo;pymediainfo"```

## Note

The script only processes image files with the following extensions: '.jpg','.jpeg','.png','.arw','.nef','.tiff','.webp','.bmp','.cr2','.orf','.rw2','.rwl','.srw'        
The script only processes video files with the following extensions: '.mp4','.mov'
