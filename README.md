# EXIFrenameX

This script allows you to easily rename image and video files in a specified folder using their metadata information. It is a quick and convenient way to organize your media files by their recording date.

### How to use
1. Download the script (EXIFrenameX.py) or the release from the repository
2. Run the script or the executable (EXIFrenameX.exe)
3. Enter the folder path where the files to be renamed are located
4. The program will iterate over all files in the folder and rename them according to their recording date

### Requirements
- Python 3.x
- exifread
- pymediainfo
- tqdm (optional, but recommended for a better user experience)

You can install these libraries by running the following command in your command prompt:

    pip install exifread pymediainfo tqdm

### Supported file types
JPEG images (.JPG / .JPEG)
PNG images (.PNG)
Sony RAW images (.ARW)
Nikon RAW images (.NEF)
TIFF images (.TIFF / .TIF)
WebP images (.WEBP)
BMP images (.BMP)
Canon RAW images (.CR2)
Olympus RAW images (.ORF)
Panasonic RAW images (.RW2)
Leica RAW images (.RWL)
Samsung RAW images (.SRW)
QuickTime video (.MOV)
MPEG-4 video (.MP4)

### Note
- The program will check if the new name already exists and add an incremental number to avoid overwriting files with the same name.
- The program will not rename files that do not have exif or media metadata. These files will be listed in the output.
- The program is original in the repository EXIFrenameX.py. Additionally, I have packed the script into a .exe with pyinstaller and released it as a release.
- The command `pyinstaller EXIFrenameX.py --hidden-import tqdm --hidden-import pymediainfo --hidden-import exifread` is used to repack the script EXIFrenameX.py into a standalone executable using the PyInstaller library
