import cv2
import os

# Folder path containing videos
folder_path_mother = '/home/cyhuiae/PycharmProjects/fyp_yolov8/runs/track'
for folder_path in os.listdir(folder_path_mother):
    # Iterate through all videos in the folder
    for filename in os.listdir(folder_path):
        if filename.endswith('.mp4') or filename.endswith('.avi'):

            # Open the video file
            video = cv2.VideoCapture(os.path.join(folder_path, filename))

            # Extract frames from the video
            success, image = video.read()
            count = 0
            while success:
                # Save the frame as a picture
                cv2.imwrite(os.path.join(folder_path, f"{filename}-frame-{count}.jpg"), image)
                success, image = video.read()
                count += 1

            # Release the video object
            video.release()
