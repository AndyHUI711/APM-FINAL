from ultralytics import YOLO
model = YOLO("yolov8s.pt")
model = YOLO("weights/yolov8s.pt")
# accepts all formats - image/dir/Path/URL/video/PIL/ndarray. 0 for webcam
success = model.export(format="engine",device=0)

