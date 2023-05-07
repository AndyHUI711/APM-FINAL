"""
APM_HUI CHEUNG YUEN 3036033077
Allowed two threads
    -> 1. Camera/Input
    -> 2. Detection
"""
import argparse
import json
import os
import platform
import time

import cv2
import threading
import infer_yolov8
from pathlib import Path
import tkinter as tk
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from util_opt import parse_opt, print_arguments

FILE = Path(__file__).resolve()
ROOT = FILE.parents[0]  # yolov5 strongsort root directory
WEIGHTS = ROOT / 'weights'

if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH
if str(ROOT / 'ultralytics') not in sys.path:
    sys.path.append(str(ROOT / 'ultralytics'))  # add yolov8 ROOT to PATH
if str(ROOT / 'trackers' / 'strongsort') not in sys.path:
    sys.path.append(str(ROOT / 'trackers' / 'strongsort'))  # add strong_sort ROOT to PATH

ROOT = Path(os.path.relpath(ROOT, Path.cwd()))  # relative

# yolov8
from ultralytics.yolo.utils.torch_utils import select_device
from ultralytics.yolo.utils.checks import check_imgsz
from ultralytics.nn.autobackend import AutoBackend


class CameraThread(threading.Thread):

    def __init__(self, args):
        threading.Thread.__init__(self)
        print(f"camera {args.source}")
        self.source = args.source  # file/dir/URL/glob, 0 for webcam
        #self.source = 'test_videos/4.mp4'
        self.cap = cv2.VideoCapture(self.source)


        self.stop_thread = False

    def run(self):
        while not self.stop_thread:
            ret, frame = self.cap.read()
            if ret:
                DetectionThread.frame = frame.copy()
            else:
                DetectionThread.frame = None

    def stop(self):
        self.cap.release
        self.stop_thread = True


class DetectionThread(threading.Thread):
    frame = None
    frame_num = 0

    def __init__(self, args):
        threading.Thread.__init__(self)

        self.stop_thread = False
        # Load a model
        self.model = args.yolo_weights
        self.tracker = args.reid_weights
        self.tracking_method = args.tracking_method
        self.tracking_config = args.tracking_config

        #ROOT / 'trackers' / self.tracking_method / 'configs' / (self.tracking_method + '.yaml')

        self.device = args.device
        self.imgsz = args.imgsz
        # Load model
        device = select_device(self.device)
        self.is_seg = '-seg' in str(self.model)
        self.model = AutoBackend(self.model, device=device, dnn=False, fp16=True)
        self.stride, self.names, self.pt = self.model.stride, self.model.names, self.model.pt
        self.imgsz = check_imgsz(self.imgsz, stride=self.stride)  # check image size
        self.tracker_list = []

        # entrance count
        self.entrance, self.records, self.center_traj = None, None, None



        # do_entrance_counting
        self.id_set = set()
        self.interval_id_set = set()
        self.in_id_list = list()
        self.out_id_list = list()
        self.prev_center = dict()
        self.records = list()


        # time and FPS
        self.start_time = time.time()
        self.frames = 0

        # save video
        self.save_vid = True
        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        self.out = cv2.VideoWriter(args.out_dir, fourcc, 30.0, (1920, 1080))

    def run(self):
        while not self.stop_thread:
            start_runtime = time.time()
            with open('region_setting.json') as file:
                data = json.load(file)
            region_type = data['type']
            region_line1 = int(data['number1'])
            region_line2 = int(data['number2'])

            if DetectionThread.frame is not None:
                h, w_img, c = DetectionThread.frame.shape
            else:
                w_img = 4000

            if region_type == 'both':
                self.entrance = [0, region_line1, w_img, region_line1, 0, region_line2, w_img,
                                 region_line2]
            elif region_type == 'upper':
                self.entrance = [0, region_line1, w_img, region_line1]
            elif region_type == 'under':
                self.entrance = [0, 0, 0, 0, 0, region_line2, w_img, region_line2]
            elif region_type == 'close':
                self.entrance = [0, 0, 0, 0, 0, 0, 0, 0]
            else:
                raise ValueError("region_type:{} unsupported.".format(
                    region_type))

            if DetectionThread.frame is not None:
                frame = infer_yolov8.run(source=DetectionThread.frame, yolo_weights=self.model,
                                         reid_weights=self.tracker,
                                         tracking_method=self.tracking_method,
                                         tracking_config=self.tracking_config,
                                         exp_name='yolov8_infer',
                                         imgsz=self.imgsz,
                                         is_seg=self.is_seg,
                                         model=self.model,
                                         stride=self.stride,
                                         names=self.names,
                                         pt=self.pt,
                                         tracker_list=self.tracker_list,
                                         entrance=self.entrance,
                                         id_set=self.id_set,
                                         interval_id_set=self.interval_id_set,
                                         in_id_list=self.in_id_list,
                                         out_id_list=self.out_id_list,
                                         prev_center=self.prev_center,
                                         records=self.records,
                                         seen=self.frames,
                                         region_type=region_type,
                                         )

                if platform.system() == 'Linux':  # allow window resize (Linux)
                    cv2.namedWindow('Detection', cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                    cv2.resizeWindow('Detection', frame.shape[1], frame.shape[0])

                # add FPS
                self.frames += 1
                elapsed_time = time.time() - start_runtime
                fps = 1 / elapsed_time

                cv2.putText(frame, f'FPS: {fps:.2f}', (frame.shape[1] - 180, 30), cv2.FONT_HERSHEY_SIMPLEX, 1,
                            (0, 0, 255), 2)

                if self.save_vid:
                    # write the flipped frame
                    frame_resize = cv2.resize(frame, (1920, 1080))
                    self.out.write(frame_resize)
                    #pass


                # display frame
                cv2.imshow('Detection', frame)
                if cv2.waitKey(1) == ord('q'):  # 1 millisecond
                    self.out.release()
                    stop_program()
                    break
                # DetectionThread.frame = None
            else:
                self.out.release()
                self.stop_thread = True
                cv2.destroyAllWindows()
                stop_program()
                break

        return

    def stop(self):
        self.stop_thread = True
        self.out.release()
        cv2.destroyAllWindows()
        # save predicted video
        print(f'Running time: {time.time() - self.start_time}; Detected frames: {self.frames};')

        # exit the main process
        # print('Exiting...')
        # os._exit(os.EX_OK)


def start_program():
    global camera_thread
    global detection_thread
    # parse params from command
    opt = parse_opt()

    opt.yolo_weights = 'weights/yolov8n.engine'
    opt.out_dir = 'runs/yolov8n_engine_true.avi'

    # Code to start the program goes here
    camera_thread = CameraThread(opt)
    camera_thread.start()

    detection_thread = DetectionThread(opt)
    detection_thread.start()

    camera_thread.join()
    detection_thread.join()
    pass

def start_video():
    global camera_thread
    global detection_thread
    # parse params from command
    opt = parse_opt()
    opt.source = 'test_videos/2.mp4'
    # opt.yolo_weights = 'weights/yolov5mu.pt'
    # opt.out_dir = 'runs/yolov5mu_pt.avi'

    # Code to start the program goes here
    camera_thread = CameraThread(opt)
    camera_thread.start()

    detection_thread = DetectionThread(opt)
    detection_thread.start()

    camera_thread.join()
    detection_thread.join()
    pass

def stop_program():
    # Code to stop the program goes here
    camera_thread.stop()
    detection_thread.stop()
    print("STOP programs")
    pass

def exit_program():
    # Code to stop the program goes here
    # Code to stop the program goes here
    camera_thread.stop()
    detection_thread.stop()
    print("STOP programs")
    # exit the main process
    print('Exiting...')
    os._exit(os.EX_OK)
    pass


if __name__ == '__main__':
    # Create a new window
    window = tk.Tk()
    window.title("Main APM window")

    # Add a label
    label = tk.Label(window, text="Welcome to APM!", font=("Arial Bold", 20))
    label.pack(pady=10)

    # Add the start button
    start_button = tk.Button(window, text="Start default (Camera)", command=start_program)
    start_button.pack(pady=5)

    # Add the start video button
    video_button = tk.Button(window, text="Start Video", command=start_video)
    video_button.pack(pady=5)


    # Add the stop button
    stop_button = tk.Button(window, text="Stop Program", command=stop_program)
    stop_button.pack(pady=5)

    # Add the stop button
    exit_button = tk.Button(window, text="Exit Program", command=exit_program)
    exit_button.pack(pady=5)

    # Start the GUI main loop
    window.mainloop()
