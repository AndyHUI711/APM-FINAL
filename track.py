import argparse
import json

import cv2
import os

from visulization import plot_tracking

# limit the number of cpus used by high performance libraries
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import sys
import platform
import numpy as np
from pathlib import Path
import torch
import torch.backends.cudnn as cudnn
import threading
import time


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

import logging
from ultralytics import YOLO
from ultralytics.nn.autobackend import AutoBackend
from ultralytics.yolo.data.dataloaders.stream_loaders import LoadImages, LoadStreams
from ultralytics.yolo.data.utils import IMG_FORMATS, VID_FORMATS
from ultralytics.yolo.utils import DEFAULT_CFG, LOGGER, SETTINGS, callbacks, colorstr, ops
from ultralytics.yolo.utils.checks import check_file, check_imgsz, check_imshow, print_args, check_requirements
from ultralytics.yolo.utils.files import increment_path
from ultralytics.yolo.utils.torch_utils import select_device
from ultralytics.yolo.utils.ops import Profile, non_max_suppression, scale_boxes, process_mask, process_mask_native
from ultralytics.yolo.utils.plotting import Annotator, colors, save_one_box

from trackers.multi_tracker_zoo import create_tracker


@torch.no_grad()
def run(
        source='0',
        yolo_weights=WEIGHTS / 'yolov8m.pt',  # model.pt path(s),
        reid_weights=WEIGHTS / 'osnet_x0_25_msmt17.pt',  # model.pt path,
        tracking_method='strongsort',
        tracking_config=None,
        imgsz=(640, 640),  # inference size (height, width)
        conf_thres=0.25,  # confidence threshold
        iou_thres=0.45,  # NMS IOU threshold
        max_det=1000,  # maximum detections per image
        device='',  # cuda device, i.e. 0 or 0,1,2,3 or cpu
        show_vid=True,  # show results
        save_txt=False,  # save results to *.txt
        save_conf=False,  # save confidences in --save-txt labels
        save_crop=False,  # save cropped prediction boxes
        save_trajectories=False,  # save trajectories for each track
        save_vid=False,  # save confidences in --save-txt labels
        nosave=False,  # do not save images/videos
        classes=None,  # filter by class: --class 0, or --class 0 2 3
        agnostic_nms=False,  # class-agnostic NMS
        augment=False,  # augmented inference
        visualize=False,  # visualize features
        update=False,  # update all models
        project=ROOT / 'runs' / 'track',  # save results to project/name
        name=None,  # save results to project/name
        exist_ok=False,  # existing project/name ok, do not increment
        line_thickness=2,  # bounding box thickness (pixels)
        hide_labels=False,  # hide labels
        hide_conf=False,  # hide confidences
        hide_class=False,  # hide IDs
        half=True,  # use FP16 half-precision inference
        dnn=False,  # use OpenCV DNN for ONNX inference
        vid_stride=1,  # video frame-rate stride
        retina_masks=False,
        line1=125,
        line2=250,
        region_type='both',
        do_entrance_counting=True

):
    source = str(source)
    frames_num = 0
    save_img = not nosave and not source.endswith('.txt')  # save inference images
    is_file = Path(source).suffix[1:] in (VID_FORMATS)
    is_url = source.lower().startswith(('rtsp://', 'rtmp://', 'http://', 'https://'))
    webcam = source.isnumeric() or source.endswith('.txt') or (is_url and not is_file)
    if is_url and is_file:
        source = check_file(source)  # download

    # Directories
    if not isinstance(yolo_weights, list):  # single yolo model
        exp_name = yolo_weights.stem
        suffix = str(yolo_weights).split('.')[1]
    elif type(yolo_weights) is list and len(yolo_weights) == 1:  # single models after --yolo_weights
        exp_name = Path(yolo_weights[0]).stem
        suffix = str(Path(yolo_weights[0])).split('.')[1]
    else:  # multiple models after --yolo_weights
        exp_name = 'ensemble'
        suffix = 'ensemble'

    exp_name = name if name else exp_name + "_" + suffix + "_" + reid_weights.stem

    if save_crop or save_trajectories or save_img or save_vid or save_txt:
        print(exp_name)
        save_dir = increment_path(Path(project) / exp_name, exist_ok=exist_ok)  # increment run
        (save_dir / 'tracks' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Load model
    device = select_device(device)
    is_seg = '-seg' in str(yolo_weights)
    model = AutoBackend(yolo_weights, device=device, dnn=dnn, fp16=half)
    stride, names, pt = model.stride, model.names, model.pt
    imgsz = check_imgsz(imgsz, stride=stride)  # check image size

    # Dataloader
    bs = 1
    if webcam:
        show_vid = check_imshow(warn=True)
        dataset = LoadStreams(
            source,
            imgsz=imgsz,
            stride=stride,
            auto=pt,
            transforms=getattr(model.model, 'transforms', None),
            vid_stride=vid_stride
        )
        bs = len(dataset)
    else:
        dataset = LoadImages(
            source,
            imgsz=imgsz,
            stride=stride,
            auto=pt,
            transforms=getattr(model.model, 'transforms', None),
            vid_stride=vid_stride
        )
    vid_path, vid_writer, txt_path = [None] * bs, [None] * bs, [None] * bs
    model.warmup(imgsz=(1 if pt or model.triton else bs, 3, *imgsz))  # warmup

    # Create as many strong sort instances as there are video sources
    tracker_list = []
    for i in range(bs):
        tracker = create_tracker(tracking_method, tracking_config, reid_weights, device, half)
        tracker_list.append(tracker, )
        if hasattr(tracker_list[i], 'model'):
            if hasattr(tracker_list[i].model, 'warmup'):
                tracker_list[i].model.warmup()
    outputs = [None] * bs

    # Run tracking
    model.warmup(imgsz=(1 if pt else bs, 3, *imgsz))  # warmup
    seen, windows, dt = 0, [], (Profile(), Profile(), Profile(), Profile())
    curr_frames, prev_frames = [None] * bs, [None] * bs

    # entrance count
    entrance, records, center_traj = None, None, None

    # customize door position
    with open('region_setting.json') as file:
        data = json.load(file)
    region_type = data['type']
    region_line1 = int(data['number1'])
    region_line2 = int(data['number2'])
    # do_entrance_counting
    id_set = set()
    interval_id_set = set()
    in_id_list = list()
    out_id_list = list()
    prev_center = dict()
    records = list()

    start_runtime = time.time()
    count_frame = 1
    for frame_idx, batch in enumerate(dataset):
        if count_frame < 3 :
            count_frame = count_frame + 1
        elif count_frame == 3:
            count_frame = 1
            continue
        path, im, im0s, vid_cap, s = batch
        visualize = increment_path(save_dir / Path(path[0]).stem, mkdir=True) if visualize else False
        with dt[0]:
            im = torch.from_numpy(im).to(device)
            im = im.half() if half else im.float()  # uint8 to fp16/32
            im /= 255.0  # 0 - 255 to 0.0 - 1.0
            if len(im.shape) == 3:
                im = im[None]  # expand for batch dim

        # Inference
        with dt[1]:
            # yolov8 predict
            preds = model(im, augment=augment, visualize=visualize)

        # Apply NMS
        with dt[2]:
            if is_seg:
                masks = []
                p = non_max_suppression(preds[0], conf_thres, iou_thres, classes, agnostic_nms, max_det=max_det)
                # nc number of classes
                proto = preds[1][-1]
            else:
                p = non_max_suppression(preds, conf_thres, iou_thres, classes, agnostic_nms, max_det=max_det)

        # Process detections
        for i, det in enumerate(p):  # detections per image
            seen += 1
            if webcam:  # bs >= 1
                p, im0, _ = path[i], im0s[i].copy(), dataset.count
                p = Path(p)  # to Path
                s += f'{i}: '
                txt_file_name = p.name
                save_path = str(save_dir / p.name)  # im.jpg, vid.mp4, ...
            else:
                p, im0, _ = path, im0s.copy(), getattr(dataset, 'frame', 0)
                p = Path(p)  # to Path
                # video file
                if source.endswith(VID_FORMATS):
                    txt_file_name = p.stem
                    save_path = str(save_dir / p.name)  # im.jpg, vid.mp4, ...
                # folder with imgs
                else:
                    txt_file_name = p.parent.name  # get folder name containing current img
                    save_path = str(save_dir / p.parent.name)  # im.jpg, vid.mp4, ...
            curr_frames[i] = im0

            txt_path = str(save_dir / 'tracks' / txt_file_name)  # im.txt
            s += '%gx%g ' % im.shape[2:]  # print string
            imc = im0.copy() if save_crop else im0  # for save_crop

            annotator = Annotator(im0, line_width=line_thickness, example=str(names))

            if hasattr(tracker_list[i], 'tracker') and hasattr(tracker_list[i].tracker, 'camera_update'):
                if prev_frames[i] is not None and curr_frames[i] is not None:  # camera motion compensation
                    tracker_list[i].tracker.camera_update(prev_frames[i], curr_frames[i])

            # entrance count setting
            h, w_img, c = imc.shape
            if region_type == 'both':
                entrance = [0, region_line1, w_img, region_line1, 0, region_line2, w_img,
                                 region_line2]
            elif region_type == 'upper':
                entrance = [0, region_line1, w_img, region_line1]
            elif region_type == 'under':
                entrance = [0, 0, 0, 0, 0, region_line2, w_img, region_line2]
            elif region_type == 'close':
                entrance = [0, 0, 0, 0, 0, 0, 0, 0]
            else:
                raise ValueError("region_type:{} unsupported.".format(
                    region_type))

            if det is not None and len(det):
                if is_seg:
                    shape = im0.shape
                    # scale bbox first the crop masks
                    if retina_masks:
                        det[:, :4] = scale_boxes(im.shape[2:], det[:, :4], shape).round()  # rescale boxes to im0 size
                        masks.append(process_mask_native(proto[i], det[:, 6:], det[:, :4], im0.shape[:2]))  # HWC
                    else:
                        masks.append(process_mask(proto[i], det[:, 6:], det[:, :4], im.shape[2:], upsample=True))  # HWC
                        det[:, :4] = scale_boxes(im.shape[2:], det[:, :4], shape).round()  # rescale boxes to im0 size
                else:
                    det[:, :4] = scale_boxes(im.shape[2:], det[:, :4], im0.shape).round()  # rescale boxes to im0 size

                # Print results
                for c in det[:, 5].unique():
                    n = (det[:, 5] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                # pass detections to strongsort
                with dt[3]:
                    outputs[i] = tracker_list[i].update(det.cpu(), im0)

                # draw boxes for visualization
                if len(outputs[i]) > 0:
                    # print(outputs[i]) # ONLY WHEN PERSON DETECTED
                    # [[78.55380582603595, 1.253917867853147, 609.2233536181316, 479.00513185089454, 1, 0.0, 0.84351504]]
                    # bbox                                                                           id cls conf
                    # [[bbox,id,cls,conf],[...],[...]]
                    if is_seg:
                        # Mask plotting
                        annotator.masks(
                            masks[i],
                            colors=[colors(x, True) for x in det[:, 5]],
                            im_gpu=torch.as_tensor(im0, dtype=torch.float16).to(device).permute(2, 0, 1).flip(
                                0).contiguous() /
                                   255 if retina_masks else im[i]
                        )

                    for j, (output) in enumerate(outputs[i]):

                        bbox = output[0:4]
                        id = output[4]
                        cls = output[5]
                        conf = output[6]

                        # to MOT format
                        bbox_left = output[0]
                        bbox_top = output[1]
                        bbox_w = output[2] - output[0]
                        bbox_h = output[3] - output[1]
                        tlwh = [bbox_left, bbox_top, bbox_w, bbox_h]


                        # Write MOT compliant results to file
                        if save_txt:
                            with open(txt_path + '.txt', 'a') as f:
                                f.write(('%g ' * 10 + '\n') % (frame_idx + 1, id, bbox_left,  # MOT format
                                                               bbox_top, bbox_w, bbox_h, -1, -1, -1, i))

                    # add annotator -> info to image
                    if save_vid or save_crop or show_vid:  # Add bbox/seg to image
                        c = int(cls)  # integer class
                        id = int(id)  # integer id
                        label = None if hide_labels else (f'{id} {names[c]}' if hide_conf else \
                                                              (
                                                                  f'{id} {conf:.2f}' if hide_class else f'{id} {names[c]} {conf:.2f}'))
                        color = colors(c, True)
                        center_x = bbox_left + bbox_w / 2.
                        center_y = bbox_top + bbox_h / 2.
                        annotator.box_label(bbox, label, color=color)
                        annotator.circle((int(center_x),int(center_y)), radius=4, color=color)

                        if save_trajectories and tracking_method == 'strongsort':
                            q = output[7]
                            tracker_list[i].trajectory(im0, q, color=color)
                        if save_crop:
                            txt_file_name = txt_file_name if (isinstance(path, list) and len(path) > 1) else ''
                            save_one_box(np.array(bbox, dtype=np.int16), imc,
                                         file=save_dir / 'crops' / txt_file_name / names[
                                             c] / f'{id}' / f'{p.stem}.jpg', BGR=True)

                        # MOT results
                        tlwh_mot=[tlwh]
                        conf_mot = [conf]
                        id_mot = [id]
                        mot_result = [frame_idx + 1, tlwh_mot, conf_mot, id_mot]
                        # entrance counting
                        statistic = human_flow_counting(True,
                                            mot_result,
                                            entrance,
                                            region_type,
                                            id_set,
                                            interval_id_set,
                                            in_id_list,
                                            out_id_list,
                                            prev_center,
                                            records,
                                            30,
                                            2
                                            )
                        records = statistic['records']
                        annotator.record(records)
            else:
                pass
                # tracker_list[i].tracker.pred_n_update_all_tracks()

            # add lines to image
            entrance_line = tuple(map(int, entrance))
            try:
                if region_type == "upper":
                    annotator.box_label(entrance_line[0:4], "DOOR1", color=(0, 0, 255))
                elif region_type == "under":
                    annotator.box_label(entrance_line[4:8], "DOOR2", color=(255, 0, 0))
                elif region_type == "both":
                    annotator.box_label(entrance_line[0:4], "DOOR1", color=(0, 0, 255))
                    annotator.box_label(entrance_line[4:8], "DOOR2", color=(255, 0, 0))
            except:
                pass

            # Stream results
            im0 = annotator.result()

            if True:    # if update: #show_vid
    #     strip_optimizer(yolo_weights)  # update model (to fix SourceChangeWarning)
                if platform.system() == 'Linux' and p not in windows:
                    windows.append(p)
                    cv2.namedWindow("APM--CAM", cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)  # allow window resize (Linux)
                    cv2.resizeWindow("APM--CAM", im0.shape[1], im0.shape[0])
                elapsed_time = time.time() - start_runtime
                fps_s = 1 / elapsed_time
                cv2.putText(im0, f'FPS: {fps_s:.2f}', (im0.shape[1] - 180, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.imshow("APM--CAM", im0)
                if cv2.waitKey(1) == ord('q'):  # 1 millisecond
                    exit()

            # Save results (image with detections)
            if save_vid:
                if vid_path[i] != save_path:  # new video
                    vid_path[i] = save_path
                    if isinstance(vid_writer[i], cv2.VideoWriter):
                        vid_writer[i].release()  # release previous video writer
                    if vid_cap:  # video
                        fps = vid_cap.get(cv2.CAP_PROP_FPS)
                        w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    else:  # stream
                        fps, w, h = 30, im0.shape[1], im0.shape[0]
                    save_path = str(Path(save_path).with_suffix('.mp4'))  # force *.mp4 suffix on results videos
                    vid_writer[i] = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
                elapsed_time = time.time() - start_runtime
                fps_s = 1 / elapsed_time
                cv2.putText(im0, f'FPS: {fps_s:.2f}', (im0.shape[1] - 180, 30), cv2.FONT_HERSHEY_SIMPLEX, 1,
                            (0, 0, 255), 2)
                vid_writer[i].write(im0)

            prev_frames[i] = curr_frames[i]

        # Print total time (preprocessing + inference + NMS + tracking)
        LOGGER.info(
            f"{s}{'' if len(det) else '(no detections), '}{sum([dt.dt for dt in dt if hasattr(dt, 'dt')]) * 1E3:.1f}ms")
        start_runtime = time.time()

    # Print results
    t = tuple(x.t / seen * 1E3 for x in dt)  # speeds per image
    LOGGER.info(
        f'Speed: %.1fms pre-process, %.1fms inference, %.1fms NMS, %.1fms {tracking_method} update per image at shape {(1, 3, *imgsz)}' % t)
    if save_txt or save_vid:
        s = f"\n{len(list((save_dir / 'tracks').glob('*.txt')))} tracks saved to {save_dir / 'tracks'}" if save_txt else ''
        LOGGER.info(f"Results saved to {colorstr('bold', save_dir)}{s}")



def human_flow_counting(do_entrance_counting,
                        result,
                        entrance,
                        region_type,
                        id_set,
                        interval_id_set,
                        in_id_list,
                        out_id_list,
                        prev_center,
                        records,
                        video_fps,
                        secs_interval
                        ):
    # Count in/out number:
    if do_entrance_counting:
        assert region_type in [
            'both', "upper", "under", 'close'
        ], "region_type should be 'horizontal' or 'vertical' or 'custom_1' or 'custom_2' when do entrance counting."

        # test
        # print(f"Test:{region_type} && {entrance}")

        if region_type == 'upper':
            entrance_x, entrance_y = entrance[0], entrance[1]
        elif region_type == 'under':
            entrance_x, entrance_y = entrance[4], entrance[5]
        else:
            entrance_x1, entrance_y1 = entrance[0], entrance[1]
            entrance_x2, entrance_y2 = entrance[4], entrance[5]

        # print(entrance_x, entrance_y)
        frame_id, tlwhs, tscores, track_ids = result
        for tlwh, score, track_id in zip(tlwhs, tscores, track_ids):
            if track_id < 0: continue
            x1, y1, w, h = tlwh
            center_x = x1 + w / 2.
            center_y = y1 + h / 2.
            if track_id in prev_center:
                if region_type == 'under':
                    if prev_center[track_id][1] >= entrance_y and \
                            center_y < entrance_y:
                        in_id_list.append(track_id)
                    if prev_center[track_id][1] <= entrance_y and \
                            center_y > entrance_y:
                        out_id_list.append(track_id)
                elif region_type == 'upper':
                    if prev_center[track_id][1] <= entrance_y and \
                            center_y > entrance_y:
                        in_id_list.append(track_id)
                    if prev_center[track_id][1] >= entrance_y and \
                            center_y < entrance_y:
                        out_id_list.append(track_id)
                elif region_type == 'both':
                    # horizontal customized center lines
                    # print(entrance_x1, entrance_y1,entrance_x2, entrance_y2)
                    if prev_center[track_id][1] <= entrance_y1 and \
                            center_y > entrance_y1:
                        in_id_list.append(track_id)
                    if prev_center[track_id][1] >= entrance_y1 and \
                            center_y < entrance_y1:
                        out_id_list.append(track_id)
                    if prev_center[track_id][1] <= entrance_y2 and \
                            center_y > entrance_y2:
                        out_id_list.append(track_id)
                    if prev_center[track_id][1] >= entrance_y2 and \
                            center_y < entrance_y2:
                        in_id_list.append(track_id)
                else:
                    continue
                prev_center[track_id][0] = center_x
                prev_center[track_id][1] = center_y
            else:
                prev_center[track_id] = [center_x, center_y]

        # Count totol number, number at a manual-setting interval
        frame_id, tlwhs, tscores, track_ids = result
        for tlwh, score, track_id in zip(tlwhs, tscores, track_ids):
            if track_id < 0: continue
            id_set.add(track_id)
            interval_id_set.add(track_id)

        # Reset counting at the interval beginning
        if frame_id % video_fps == 0 and frame_id / video_fps % secs_interval == 0:
            curr_interval_count = len(interval_id_set)
            interval_id_set.clear()
        info = "Frame id: {}, Total count: {}".format(frame_id, len(id_set))
        if do_entrance_counting:
            info += ", In count: {}, Out count: {}".format(
                len(in_id_list), len(out_id_list))
        if frame_id % video_fps == 0 and frame_id / video_fps % secs_interval == 0:
            info += ", Count during {} secs: {}".format(secs_interval,
                                                        curr_interval_count)
            interval_id_set.clear()
        # print(info)
        info += "\n"
        records.append(info)

        return {
            "id_set": id_set,
            "interval_id_set": interval_id_set,
            "in_id_list": in_id_list,
            "out_id_list": out_id_list,
            "prev_center": prev_center,
            "records": records,
        }

def parse_opt():
    parser = argparse.ArgumentParser()
    parser.add_argument('--yolo-weights', nargs='+', type=Path, default=WEIGHTS / 'weights/sf480.pt', help='model.pt path(s)')
    parser.add_argument('--reid-weights', type=Path, default=WEIGHTS / 'osnet_x1_0_imagenet.pth')
    parser.add_argument('--tracking-method', type=str, default='bytetrack',
                        help='deepocsort, botsort, strongsort, ocsort, bytetrack')
    parser.add_argument('--tracking-config', type=Path, default=None)
    parser.add_argument('--source', type=str, default='two-doors_640.mp4',
                        help='file/dir/URL/glob, 0 for webcam')
    parser.add_argument('--imgsz', '--img', '--img-size', nargs='+', type=int, default=[480,640], help='inference size h,w')
    parser.add_argument('--conf-thres', type=float, default=0.3, help='confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.5, help='NMS IoU threshold')
    parser.add_argument('--max-det', type=int, default=1000, help='maximum detections per image')
    parser.add_argument('--device', default='0', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--show-vid', action='store_true', help='display tracking video results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--save-crop', action='store_true', help='save cropped prediction boxes')
    parser.add_argument('--save-trajectories', action='store_true', help='save trajectories for each track')
    parser.add_argument('--save-vid', default=True, action='store_true', help='save video tracking results')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    # class 0 is person, 1 is bycicle, 2 is car... 79 is oven
    parser.add_argument('--classes', nargs='+', type=int, default=0, help='filter by class: --classes 0, or --classes 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--visualize', action='store_true', help='visualize features')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default=ROOT / 'runs' / 'track/new', help='save results to project/name')
    parser.add_argument('--name', default=None, help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--line-thickness', default=2, type=int, help='bounding box thickness (pixels)')
    parser.add_argument('--hide-labels', default=False, action='store_true', help='hide labels')
    parser.add_argument('--hide-conf', default=False, action='store_true', help='hide confidences')
    parser.add_argument('--hide-class', default=False, action='store_true', help='hide IDs')
    parser.add_argument('--half', action='store_true', help='use FP16 half-precision inference')
    parser.add_argument('--dnn', action='store_true', help='use OpenCV DNN for ONNX inference')
    parser.add_argument('--vid-stride', type=int, default=1, help='video frame-rate stride')
    parser.add_argument('--retina-masks', action='store_true', help='whether to plot masks in native resolution')

    # entrance count
    parser.add_argument(
        "--line1",
        type=str,
        default=125,
        help="'horizontal' line for entrance counting or break in counting"
    )
    parser.add_argument(
        "--line2",
        type=str,
        default=250,
        help="'horizontal' line for entrance counting or break in counting"
    )
    parser.add_argument(
        "--region-type",
        type=str,
        default='both',
        help="Area type for entrance counting or break in counting"
    )
    parser.add_argument(
        "--do_entrance_counting",
        action='store_true',
        default=True,
        help="Whether counting the numbers of identifiers entering "
    )

    opt = parser.parse_args()
    opt.imgsz *= 2 if len(opt.imgsz) == 1 else 1  # expand
    opt.tracking_config = ROOT / 'trackers' / opt.tracking_method / 'configs' / (opt.tracking_method + '.yaml')
    print_args(vars(opt))
    return opt


def main(opt):
    # check_requirements(requirements=ROOT / 'requirements.txt', exclude=('tensorboard', 'thop'))
    run(**vars(opt))


if __name__ == "__main__":
    start_time = time.time()
    opt = parse_opt()
    main(opt)
