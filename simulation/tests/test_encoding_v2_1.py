import math
from tqdm import tqdm
import json

from data_v2.taffic_signs import TrafficSignsData
from sign_boards import TrafficSignBoard
from lidar_points import LiDARSampling
from encoding_v2_1.encode_v2_1 import encode
from encoding_v2_1.decode_v2_1 import decode
import utils
from simulation.exceptions import *

ALL_SETTINGS = {
    "tri11": {
        "sample": {"category": 1, "sign": 85},
        "canvas": {"height": 1150, "width": 1350},
        "board": {"shape": "triangle", "kwargs": {"tri_length": 1300}},
        "encoding": {"scaled": True, "height": 221, "width": 67, "orientation": "bottom"},
    },  # Triangle (*1300): Scaled Height + 3.3 Ratio (221*67)
    "cir11": {
        "sample": {"category": 1, "sign": 85},
        "canvas": {"height": 1250, "width": 1250},
        "board": {"shape": "circle", "kwargs": {"cir_radius": 600}},
        "encoding": {"scaled": True, "height": 311, "width": 94, "orientation": "center"},
    },  # Circle (*600): Scaled Height + 3.3 Ratio (311*94)

    "rect11": {
        "sample": {"category": 1, "sign": 85},
        "canvas": {"height": 1300, "width": 1300},
        "board": {"shape": "rectangle", "kwargs": {"rect_height": 1200, "rect_width": 1200}},
        "encoding": {"scaled": True, "height": 400, "width": 121, "orientation": "center"},
    },  # Rectangle (1300*1300): Scaled Height + 3.3 Ratio (400*121)
    "rect10": {
        "sample": {"category": 1, "sign": 85},
        "canvas": {"height": 1300, "width": 1300},
        "board": {"shape": "rectangle", "kwargs": {"rect_height": 1200, "rect_width": 1200}},
        "encoding": {"scaled": True, "height": 400, "width": 100, "orientation": "center"},
    },  # Rectangle (1300*1300): Scaled Height, NO Ratio (400*100)
    "rect00": {
        "sample": {"category": 1, "sign": 85},
        "canvas": {"height": 1300, "width": 1300},
        "board": {"shape": "rectangle", "kwargs": {"rect_height": 1200, "rect_width": 1200}},
        "encoding": {"scaled": False, "height": 600, "width": 100, "orientation": "center"},
    },  # Rectangle (1300*1300): NO Scaled Height, NO Ratio (600*100)
}

setting = ALL_SETTINGS["rect11"]
print(json.dumps(setting, indent=2))

# sample a traffic sign
data_obj = TrafficSignsData()
data_sample = data_obj.get_sample(category_idx=1, sign_idx=85)
print(data_sample)

# encode the sampled traffic sign
data_sample_encoding = encode(sample=data_sample, use_scaled_height=setting["encoding"]["scaled"])
print(data_sample_encoding)
height, width = setting["encoding"]["height"], setting["encoding"]["width"]  # milli-meters
data_sample_raw_bar = utils.encoding_2_raw_bar(encoding=data_sample_encoding,
                                               elem_height=height, elem_width=width)

# test draw rectangle
sign_board_obj = TrafficSignBoard(height=setting["canvas"]["height"], width=setting["canvas"]["width"])
sign_board_obj.draw_sign_board(shape=setting["board"]["shape"], **setting["board"]["kwargs"])

sign_board_obj.place_encoding(encoding=data_sample_raw_bar, orientation=setting["encoding"]["orientation"])
# sign_board_obj.render().show()
sign_board_obj.render().savefig("./canvas_v2_1.png")

# sample points on the canvas
distance = 130  # meters
hori_angle_resol, vert_angle_resol = 0.1, 0.33
pt_sample_obj = LiDARSampling(canvas=sign_board_obj,
                              hori_angle_resol=hori_angle_resol, vert_angle_resol=vert_angle_resol)
sample_res, sample_res_loc = pt_sample_obj.sample_at_distance(dist=distance)
# print(sample_res)

ENABLE_STATS_ANA = True
# statistical analysis settings
STATS_ANA_MAX_ATTEMPTS = 5000
sample_step_size = math.ceil(len(sample_res) * 1. / STATS_ANA_MAX_ATTEMPTS)
cnt_success, cnt_suc_full, cnt_suc_not_full_not_tol, cnt_suc_tol, cnt_fail, cnt_wrong = 0, 0, 0, 0, 0, 0
cnt_suc_levels = {1: 0, 2: 0}
_iter_obj = range(0, len(sample_res)) if not ENABLE_STATS_ANA else tqdm(range(0, len(sample_res), sample_step_size))
# actual iteration starts here
for _sample_idx in _iter_obj:
    _sample = sample_res[_sample_idx]
    _sample_loc = sample_res_loc[_sample_idx]
    try:
        _sample_decoded, _sample_decoded_info = decode(
            sign_data_obj=data_obj,
            points=_sample,
            hori_margin=utils.dist_2_margin(dist=distance, angle_resol=hori_angle_resol),
            vert_margin=utils.dist_2_margin(dist=distance, angle_resol=vert_angle_resol),
            height=height, width=width,
            tolerable=True)
        if not ENABLE_STATS_ANA:  # debug printing
            print(_sample_decoded, _sample_decoded_info)
        else:  # statistical analysis
            _is_suc = True
            if _is_suc is True and _sample_decoded["category_1"] is not None:
                _is_suc = (_sample_decoded["category_1"] == data_sample["encoding"]["category"])
            if _is_suc is True and _sample_decoded["category_2"] is not None:
                _is_suc = (_sample_decoded["category_2"] == data_sample["encoding"]["idx"])
            if _is_suc is True:
                _cnt_levels = int(_sample_decoded["category_1"] is not None) + \
                              int(_sample_decoded["category_2"] is not None)
                cnt_suc_levels[_cnt_levels] += 1
            # update counts
            if _is_suc is False:
                cnt_wrong += 1
                continue
            cnt_success += 1
            if _sample_decoded_info["is_complete"] is True:
                cnt_suc_full += 1
            if (_sample_decoded_info["is_complete"] is False) and _sample_decoded_info.get("is_tolerated") is None:
                cnt_suc_not_full_not_tol += 1
            if _sample_decoded_info.get("is_tolerated") is True:
                cnt_suc_tol += 1
    except DecodeFailure as err:
        if not ENABLE_STATS_ANA:  # debug printing
            print("Decode Failed for Sample Loc (%d,%d): %s" % (_sample_loc["hori"], _sample_loc["vert"], str(err)))
        else:  # statistical analysis
            cnt_fail += 1
        continue
if ENABLE_STATS_ANA:  # statistical analysis
    print(
        "[ALL] %d\n"
        "\t[SUCCESS] %d (full=%d, !full!tol=%d, tolerated=%d)\n\t\tLevels: 1=%d, 2=%d\n"
        "\t[WRONG] %d\n\t[FAILURE] %d"
        % (len(_iter_obj), cnt_success, cnt_suc_full, cnt_suc_not_full_not_tol, cnt_suc_tol,
           cnt_suc_levels[1], cnt_suc_levels[2], cnt_wrong, cnt_fail))
print()
