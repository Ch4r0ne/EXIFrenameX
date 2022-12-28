# Exifrenamer
Image and Video File Renamer

This script renames image and video files in a specified folder using the date taken or recorded as the new file name. 
The date is extracted from the EXIF metadata for images and from the media info for videos.

Dependencies
   - exifread
   - pymediainfo

Usage
   - Replace the value of folder_path with the path to the folder containing the image and video files that you want to rename.
   - Run the script.

Notes
    The script processes image files with the extensions .jpg, .jpeg, and .png, and video files with the extensions .mp4 and .mov.
