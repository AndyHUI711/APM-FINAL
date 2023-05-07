import cv2

# Initialize the camera
cap = cv2.VideoCapture(0)
print(cap)
# Check if camera is opened successfully
if (cap.isOpened()== False):
  print("Error opening video stream or file")
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter('runs/test_cam.avi', fourcc, 10.0, (480, 640))
# Read until video is completed
while(cap.isOpened()):
  # Capture frame-by-frameqq
  ret, frame = cap.read()
  print(ret, frame)
  if ret == True:

    # Display the resulting frame
    cv2.imshow('Frame',frame)
    frame_resize = cv2.resize(frame,(480,640))
    out.write(frame_resize)


    # Press Q on keyboard to exit
    if cv2.waitKey(25) & 0xFF == ord('q'):
      break

  # Break the loop
  else:
    break

# Release the video capture object and close all windows
cap.release()
out.release()
cv2.destroyAllWindows()

