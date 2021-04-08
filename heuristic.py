import numpy as np
from helpers import *
from directions import *
from component2d import *

def heurictic_to_storage(state, fw_mode = True, storages = None):
    if storages is None: storages = state.storages
    cur_avail = state.available & ~state.sub_boxes
    jump_map = create_jump_map(cur_avail)
    storages_start = []
    for stor in positions_true(storages & ~state.sub_boxes):
        for d in directions:
            if fw_mode: sk = dir_shift(d, stor)
            else: sk = dir_shift(op_dir(d), stor)
            if state.storekeepers[sk]:
                storages_start.append((stor, d))

    storages_jumps = find_box_jumps(
        jump_map, cur_avail, storages_start, not fw_mode
    )
    if storages_jumps is not None:
        _, stor_last_move = storages_jumps
        res = np.stack([
            stor_last_move[:,:,op_dir(d)] == op_dir(d)
            for d in directions
        ], axis = -1)
    else:
        res = np.zeros(state.available.shape + (4,))

    box_jumps = find_all_box_jumps(
        cur_avail,
        state.sub_boxes,
        state.storekeepers,
        fw_mode,
        jump_map = jump_map
    )
    for box, (fst_dir, _) in box_jumps.items():
        res[box] = False
        if storages[box]: continue
        for d in directions:
            if ((fst_dir == d).any(axis = -1) & storages).any():
                res[box+(d,)] = True
                #print("To storage", box, dir_to_str(box_d))

    return res[1:-1,1:-1].astype(int) * 2
