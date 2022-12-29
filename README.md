# Description

This script renames image and video files in a specified folder using their metadata information. It processes image files by extracting the 'EXIF DateTimeOriginal' field and renaming the file using the formatted date as the new filename. It processes video files by extracting the 'recorded_date' field for MP4 files or the 'comapplequicktimecreationdate' field for MOV files, and renaming the file using the formatted date as the new filename. If the 'comapplequicktimecreationdate' field is not present for MOV files, it falls back to the 'recorded_date' field. The script handles any errors that may occur while processing the files.

# Requirements

    Python 3
    exifread library
    pymediainfo library

# Usage

    Install Python 3
    Install the required libraries: pip install exifread pymediainfo
    Run the script: Exifrenamer.py
    When prompted, enter the path to the folder containing the image and video files

# Note

The script only processes image files with the following extensions: '.jpg', '.jpeg', '.png', '.arw', '.nef', '.tiff', '.webp', '.bmp', '.cr2', '.orf', '.rw2', '.rwl', '.srw'        
The script only processes video files with the following extensions: '.mp4', '.mov'

# Goal

The goal of this program is to make it easy for anyone to use and rename image and video files in a specified folder using their metadata information. The program should have a user-friendly interface and support additional file formats.
