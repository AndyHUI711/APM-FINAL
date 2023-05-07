from ultralytics import YOLO

# Load a model
model = YOLO('weights/weights/c640.pt')  # load a custom trained

# Export the model
model.export(format='engine',device=0, int8= True, imgsz=(480,640))
