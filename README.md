# Description

This script renames image and video files in a specified folder using their metadata information. It processes image files by extracting the 'EXIF DateTimeOriginal' field and renaming the file using the formatted date as the new filename. It processes video files by extracting the 'recorded_date' field for MP4 files or the 'comapplequicktimecreationdate' field for MOV files, and renaming the file using the formatted date as the new filename. If the 'comapplequicktimecreationdate' field is not present for MOV files, it falls back to the 'recorded_date' field. The script handles any errors that may occur while processing the files.

# Requirements

    Python 3
    exifread library
    pymediainfo library

# Usage

    Install the required libraries: pip install exifread pymediainfo
    Run the script: python rename_files.py
    When prompted, enter the path to the folder containing the image and video files

# Note

The script only processes image files with the following extensions: '.jpg', '.jpeg', '.png'
The script only processes video files with the following extensions: '.mp4', '.mov'
