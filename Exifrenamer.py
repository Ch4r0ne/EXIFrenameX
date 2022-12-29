import exifread
import datetime
import os
import pymediainfo
from typing import List, Dict

# Inform the user about the supported file types and how the new filenames will be generated
print("The files will be renamed based on their creation or recording date.")
print("The new filename will be in the following format: YYYY-MM-DD_HH-MM-SS.Filetype")
print("")

# Ask the user for the path of the folder containing the files
print(r"Example path: C:\Users\Username\Documents\ImageFolder")
folder_path = input("Enter the path of the folder containing the image files:")
directory = folder_path

def get_image_exif_datetime_original(image_path: str) -> str:
    # Open the image file in binary mode
    with open(image_path, 'rb') as f:
        # Read the EXIF metadata from the image file
        tags = exifread.process_file(f)

        # Filter the metadata by the DateTimeOriginal tag and return the value in the desired format
        date_time_original = tags.get('EXIF DateTimeOriginal', None)
        if date_time_original:
            # Parse the metadata value as a datetime object
            date_time_obj = datetime.datetime.strptime(str(date_time_original), '%Y:%m:%d %H:%M:%S')
            # Format the datetime object as a string in the desired format
            return date_time_obj.strftime('%Y-%m-%d_%H-%M-%S')
        else:
            return ""

def process_image_files(directory: str, image_formats: List[str]) -> Dict[str, str]:
    results = {}
    # Iterate through the files in the directory
    for filename in os.listdir(directory):
        # Check if the file is an image file
        file_extension = os.path.splitext(filename)[1].lower()
        if file_extension in image_formats:
            image_path = os.path.join(directory, filename)
            # Extract the EXIF DateTimeOriginal metadata from the image file
            date_time_original = get_image_exif_datetime_original(image_path)
            # Check if the image filename is already in the results dictionary
            if filename in results:
                # If the image filename is already in the results dictionary, add a "_" and an incremental number to the filename
                i = 1
                while f"{filename}_{i}" in results:
                    i += 1
                filename = f"{filename}_{i}"
            # Add the image filename and EXIF DateTimeOriginal metadata to the results dictionary
            results[filename] = date_time_original
    return results

# Set the acceptable image file formats
image_formats = ['.jpg', '.jpeg', '.png', '.arw', '.nef', '.tiff', '.webp', '.bmp', '.cr2', '.orf', '.rw2', '.rwl', '.srw']

# Process the image files in the directory
results = process_image_files(directory, image_formats)

# Initialize the counters for the number of files renamed and the number of files not renamed
renamed_count = 0
not_renamed_count = 0

# Print the results and try to rename the files using the EXIF DateTimeOriginal metadata
for filename, date_time_original in results.items():
    if date_time_original:
        # Try to rename the file using the EXIF DateTimeOriginal metadata
        try:
            # Split the filename into the base name and the extension
            base_name, extension = os.path.splitext(filename)
            # Construct the new filename using the EXIF DateTimeOriginal metadata and the extension
            new_filename = f"{date_time_original}{extension}"
            os.rename(os.path.join(directory, filename), os.path.join(directory, new_filename))
            renamed_count += 1
            print(f"File '{filename}' successfully renamed to '{new_filename}'")
        except OSError:
            # If an error occurred while renaming the file, try to rename it again with a different filename
            i = 1
            while True:
                # Construct a new filename using the EXIF DateTimeOriginal metadata, an incremental number, and the extension
                new_filename = f"{date_time_original}_{i}{extension}"
                try:
                    os.rename(os.path.join(directory, filename), os.path.join(directory, new_filename))
                    renamed_count += 1
                    print(f"File '{filename}' successfully renamed to '{new_filename}'")
                    break
                except OSError:
                    i += 1
            #not_renamed_count += 1
            #print(f"Failed to rename file '{filename}'")
    else:
        not_renamed_count += 1
        print(f"File '{filename}' does not have EXIF DateTimeOriginal metadata")

# Get a list of all files in the folder
files = os.listdir(folder_path)

# Iterate through the list of files
for file in files:
    # Check if the file is a video file (based on its file extension)
    if file.endswith(".mov") or file.endswith(".mp4"): # Replace ".MOV" and ".MP4" with the desired file extension(s)
        # Open the video file
        file_path = os.path.join(folder_path, file)
        media_info = pymediainfo.MediaInfo.parse(file_path)

        # Initialize a flag to track if the first "comapplequicktimecreationdate" or "recorded_date" has been found
        metadata_found = False
        metadata_name = ""
        metadata_value = ""

        # Iterate through all tracks in the file
        for track in media_info.tracks:
            # Look for the "comapplequicktimecreationdate" metadata
            creation_date = track.to_data().get("comapplequicktimecreationdate", None)
            if creation_date is not None and not metadata_found:
                # Remove the "+" character and all characters after it from the metadata value
                creation_date = creation_date.split("+")[0]
                # Remove the milliseconds from the metadata value
                creation_date = creation_date.split(".")[0]
                # Split the metadata value into date and time
                date_str, time_str = creation_date.split("T")
                # Extract the date and time from the parts
                creation_date = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                # Format the datetime object in the desired format
                metadata_value = creation_date.strftime("%Y-%m-%d_%H-%M-%S")
                metadata_name = "comapplequicktimecreationdate"
                metadata_found = True
                break

        # If the "comapplequicktimecreationdate" metadata was not found...
        if not metadata_found:
            # ...look for the "recorded_date" metadata
            for track in media_info.tracks:
                recorded_date = track.to_data().get("recorded_date", None)
                if recorded_date is not None:
                    # Remove the timezone information from the recorded_date value
                    recorded_date = recorded_date.split("+")[0]
                    # Parse the recorded_date value
                    recorded_date = datetime.datetime.strptime(recorded_date, "%Y-%m-%dT%H:%M:%S")
                    # Format the recorded_date value in the desired format
                    metadata_value = recorded_date.strftime("%Y-%m-%d_%H-%M-%S")
                    metadata_name = "recorded_date"
                    metadata_found = True
                    break

        # If the metadata was not found...
        if not metadata_found:
            # ...print a message
            print(f"File {file} does not have recorded_date or comapplequicktimecreationdate metadata")
        else:
            # Rename the file based on the metadata value
            # Split the file name and the extension
            base_name, extension = os.path.splitext(file)
            # Construct the new file name
            new_file_path = os.path.join(folder_path, f"{metadata_value}{extension}")
            file_path_exists = True
            counter = 1
            # Check if the file already exists with the new name
            while file_path_exists:
                # If the file already exists with the new name...
                if os.path.exists(new_file_path):
                    # ...rename the file with a counter suffix
                    new_file_path = os.path.join(folder_path, f"{metadata_value}_{counter}{extension}")
                    counter += 1
                else:
                    # If the file does not exist with the new name, break out of the loop
                    file_path_exists = False
            # Try to rename the file
            try:
                os.rename(file_path, new_file_path)
                print(f"File {file} successfully renamed to {metadata_value}{extension}")
                renamed_count += 1
            except OSError:
                # If an error occurred while renaming the file, increment the error counter
                not_renamed_count += 1
                print(f"Error renaming {file} to {metadata_value}{extension}")

# Print the results
print(f"Renamed {renamed_count} files.")
print(f"Encountered {not_renamed_count} errors while renaming files.")
