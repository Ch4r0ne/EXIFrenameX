import exifread
import datetime
import os
import pymediainfo

folder_path = r'E:\Temp'

image_formats = ['.jpg', '.jpeg', '.png']
video_formats = ['.mp4', '.mov']

# Iterate through all the files in the folder
for filename in os.listdir(folder_path):
    file_extension = os.path.splitext(filename)[1].lower()

    # Process image files
    if file_extension in image_formats:
        try:
            f = open(os.path.join(folder_path, filename), 'rb')
            tags = exifread.process_file(f)
            date_time_original = tags.get('EXIF DateTimeOriginal', None)
            if date_time_original:
                date_time_obj = datetime.datetime.strptime(str(date_time_original), '%Y:%m:%d %H:%M:%S')
                formatted_date_time = date_time_obj.strftime('%Y-%m-%d_%H-%M-%S')
                f.close()
                # Save the date as the file name
                new_filename = formatted_date_time + file_extension
                os.rename(os.path.join(folder_path, filename), os.path.join(folder_path, new_filename))
                print(f"Filename: {filename}, DateTimeOriginal: {formatted_date_time}")
            else:
                f.close()
        except Exception as e:
            print(f"Error processing file {filename}: {e}")

    # Process video files
    elif file_extension in video_formats:
        try:
            file_path = os.path.join(folder_path, filename)
            media_info = pymediainfo.MediaInfo.parse(file_path)
            creation_date_found = False
            recorded_date = None
            for track in media_info.tracks:
                # Get recorded date for MP4 files
                if file_extension == '.mp4':
                    recorded_date = track.to_data().get("recorded_date", None)
                    if recorded_date is not None:
                        recorded_date = recorded_date.split("+")[0]
                        recorded_date = datetime.datetime.strptime(recorded_date, "%Y-%m-%dT%H:%M:%S")
                        recorded_date = recorded_date.strftime("%Y-%m-%d_%H-%M-%S")
                        # Save the date as the file name
                        new_filename = recorded_date + file_extension
                        os.rename(os.path.join(folder_path, filename), os.path.join(folder_path, new_filename))
                        print(f"recorded_date for {filename}: {recorded_date}")
                        break
                    else:
                        print(f"recorded_date not found for {filename}.")
                # Get creation date for MOV files
                elif file_extension == '.mov':
                    creation_date = track.to_data().get("comapplequicktimecreationdate", None)
                    if creation_date is not None and not creation_date_found:
                        creation_date_found = True
                        creation_date = creation_date.split("+")[0]
                        creation_date = creation_date.split(".")[0]
                        date_str, time_str = creation_date.split("T")
                        creation_date = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                        creation_date = creation_date.strftime("%Y-%m-%d_%H-%M-%S")
                        # Save the date as the file name
                        new_filename = creation_date + file_extension
                        os.rename(os.path.join(folder_path, filename), os.path.join(folder_path, new_filename))
                        print(f"comapplequicktimecreationdate: {creation_date}")
            if not creation_date_found:
                print("comapplequicktimecreationdate was not found.")
        except Exception as e:
            print(f"Error processing file {filename}: {e}")

    # Process other file types
    else:
        print(f"Skipping file {filename} - unsupported file type.")
