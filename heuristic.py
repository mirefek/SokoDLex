import numpy as np
from helpers import *
from directions import *
from component2d import *

def heurictic_to_storage(state, fw_mode = True):
    cur_avail = state.available & ~state.sub_boxes
    jump_map = create_jump_map(cur_avail)
    storages_start = [
        (pos, d)
        for pos in positions_true(state.storages & ~state.sub_boxes)
        for d in directions
        if state.storekeepers[dir_shift(d, pos)]
    ]
    from_storages, _, _, _ = box_positions(
        jump_map, cur_avail, storages_start, not fw_mode
    )
    res = np.stack([
        from_storages[:,:,op_dir(d)]
        for d in directions
    ], axis = -1)
    box_moves = available_box_moves(
        cur_avail,
        state.sub_boxes,
        state.storekeepers,
        fw_mode,
        jump_map = jump_map
    )
    for box, (_, fst_dir, _, _) in box_moves.items():
        res[box] = False
        if state.storages[box]: continue
        for d in directions:
            if ((fst_dir == d) & state.storages).any():
                if fw_mode: box_d = op_dir(d)
                else: box_d = d
                res[box+(box_d,)] = True
                #print("To storage", box, dir_to_str(box_d))

    return res[1:-1,1:-1].astype(int) * 2
