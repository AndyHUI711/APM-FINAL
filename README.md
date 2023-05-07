# APM-FINAL
YOLOv8+Tracker+Jetson
# **APM CAPSTONE PROJECT - HKU IDT**

Using YOLOv8, Bytetrack and Jetson Nano

## YOLOv8
_reference to [https://github.com/ultralytics/ultralytics]()_ \
Using `git clone` to download YOLOv8 

## Bytetrack
_reference to [https://github.com/ifzhang/ByteTrack]()_ \
Trackers' files in [APM_CAPSTONE_FINAL\trackers]() \
We provide five different trackers, you can change it in the _track.py_ and _tracknew.py_ \
We recommend to use ByteTrack

## ReID
You can use your own ReID models \
You can change it in the _track.py_ and _tracknew.py_ 

## Models
We provide YOLOv5n and YOLOv8 models (n/s/m) \
The testing results of these models you can reference to our report \

1. Pre-Trained models (COCO)\
Path: "weights"
2. Trained on our own datasets \
Path: "weights\weights"

Reminder: You cannot use the _.engine_ models directly, \
you need to generate it using _.pt_ models on your own devices \
You can use _pt2engine.py_ or reference to _YOLOv8 - Ultralytics_

## Doors control
To control the lines and door status (reference to our report) \
You can use _door_control.py_ which is a TK GUI \
Data is saving at JSON: _region_setting.json_ \
If using our Jetson Nano with GPIO control, you can use hardware to control them
