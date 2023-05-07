import ast
import yaml
import copy
import argparse
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path
FILE = Path(__file__).resolve()
ROOT = FILE.parents[0]  # yolov5 strongsort root directory
WEIGHTS = ROOT / 'weights'

class ArgsParser(ArgumentParser):
    def __init__(self):
        super(ArgsParser, self).__init__(
            formatter_class=RawDescriptionHelpFormatter)
        self.add_argument(
            "-o", "--opt", nargs='*', help="set configuration options")

    def parse_args(self, argv=None):
        args = super(ArgsParser, self).parse_args(argv)
        assert args.config is not None, \
            "Please specify --config=configure_file_path."
        args.opt = self._parse_opt(args.opt)
        return args

    def _parse_opt(self, opts):
        config = {}
        if not opts:
            return config
        for s in opts:
            s = s.strip()
            k, v = s.split('=', 1)
            if '.' not in k:
                config[k] = yaml.load(v, Loader=yaml.Loader)
            else:
                keys = k.split('.')
                if keys[0] not in config:
                    config[keys[0]] = {}
                cur = config[keys[0]]
                for idx, key in enumerate(keys[1:]):
                    if idx == len(keys) - 2:
                        cur[key] = yaml.load(v, Loader=yaml.Loader)
                    else:
                        cur[key] = {}
                        cur = cur[key]
        return config


def parse_opt():
    parser = argparse.ArgumentParser()
    parser.add_argument('--yolo-weights', nargs='+', type=Path, default=WEIGHTS / 'yolov8s.pt', help='model.pt path(s)')
    parser.add_argument('--reid-weights', type=Path, default=WEIGHTS / 'osnet_x1_0_imagenet.pth')
    parser.add_argument('--tracking-method', type=str, default='bytetrack',
                        help='deepocsort, botsort, strongsort, ocsort, bytetrack')
    parser.add_argument('--tracking-config', type=Path, default=None)
    parser.add_argument('--source', type=int, default=0,
                        help='file/dir/URL/glob, 0 for webcam')
    parser.add_argument('--imgsz', '--img', '--img-size', nargs='+', type=int, default=[640], help='inference size h,w')
    parser.add_argument('--conf-thres', type=float, default=0.2, help='confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.5, help='NMS IoU threshold')
    parser.add_argument('--max-det', type=int, default=1000, help='maximum detections per image')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--show-vid', action='store_true', help='display tracking video results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--save-crop', action='store_true', help='save cropped prediction boxes')
    parser.add_argument('--save-trajectories', action='store_true', help='save trajectories for each track')
    parser.add_argument('--save-vid', default=True, action='store_true', help='save video tracking results')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    # class 0 is person, 1 is bycicle, 2 is car... 79 is oven
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --classes 0, or --classes 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--visualize', action='store_true', help='visualize features')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default=ROOT / 'runs' / 'track', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--line-thickness', default=2, type=int, help='bounding box thickness (pixels)')
    parser.add_argument('--hide-labels', default=False, action='store_true', help='hide labels')
    parser.add_argument('--hide-conf', default=False, action='store_true', help='hide confidences')
    parser.add_argument('--hide-class', default=False, action='store_true', help='hide IDs')
    parser.add_argument('--half', action='store_true', help='use FP16 half-precision inference')
    parser.add_argument('--dnn', action='store_true', help='use OpenCV DNN for ONNX inference')
    parser.add_argument('--vid-stride', type=int, default=1, help='video frame-rate stride')
    parser.add_argument('--retina-masks', action='store_true', help='whether to plot masks in native resolution')
    parser.add_argument('--out-dir', type=str, default='runs/output.avi')

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
    #print_arguments(opt)
    return opt



def merge_cfg(args):
    # load config
    with open(args.config) as f:
        pred_config = yaml.safe_load(f)

    def merge(cfg, arg):
        # update cfg from arg directly
        merge_cfg = copy.deepcopy(cfg)
        for k, v in cfg.items():
            if k in arg:
                merge_cfg[k] = arg[k]
            else:
                if isinstance(v, dict):
                    merge_cfg[k] = merge(v, arg)

        return merge_cfg

    def merge_opt(cfg, arg):
        merge_cfg = copy.deepcopy(cfg)
        # merge opt
        if 'opt' in arg.keys() and arg['opt']:
            for name, value in arg['opt'].items(
            ):  # example: {'MOT': {'batch_size': 3}}
                if name not in merge_cfg.keys():
                    print("No", name, "in config file!")
                    continue
                for sub_k, sub_v in value.items():
                    if sub_k not in merge_cfg[name].keys():
                        print("No", sub_k, "in config file of", name, "!")
                        continue
                    merge_cfg[name][sub_k] = sub_v

        return merge_cfg

    args_dict = vars(args)
    pred_config = merge(pred_config, args_dict)
    pred_config = merge_opt(pred_config, args_dict)

    return pred_config


def print_arguments(cfg):
    print('-----------  Running Arguments -----------')
    buffer = yaml.dump(cfg)
    print(buffer)
    print('------------------------------------------')
