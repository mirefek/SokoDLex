import numpy as np
from collections import defaultdict, deque

from directions import *
from helpers import *

def get_component_dist(available, start_positions):
    q = deque((pos, 0) for pos in start_positions)
    res = np.full(available.shape, -1, dtype = int)
    while q:
        pos,dist = q.popleft()
        if res[pos] >= 0 or not available[pos]: continue
        res[pos] = dist
        q.extend(
            (dir_shift(d, pos), dist+1)
            for d in directions
        )
    return res

def get_component(available, start_positions):
    q = deque(start_positions)
    res = np.zeros(available.shape, dtype = bool)
    while q:
        pos = q.popleft()
        if res[pos] or not available[pos]: continue
        res[pos] = True
        q.extend(
            dir_shift(d, pos)
            for d in directions
        )
    return res

def component_split(component):
    component = np.array(component)
    while component.any():
        pos = positions_true(component)[0]
        subcomp = get_component(component, [pos])
        yield pos, subcomp
        component = component & ~subcomp

def follow_l_wall(available, start_pos, start_d):
    pos = start_pos
    d = start_d
    while True:
        yield pos, d
        pos_n = dir_shift(d, pos)
        if not available[pos_n]:
            d = turn_right(d)
        else:
            pos = pos_n
            d = turn_left(d)
        if pos == start_pos and d == start_d:
            break

def update_jumps(jump_map, seq_it):
    visited = defaultdict(list)
    for pos,d in seq_it:
        visited[pos].append(d)

    for (y,x), ds in visited.items():
        for a,b in zip(ds, ds[1:]+ds[:1]):
            jump_map[y,x,a] = b

def update_jumps_from_pos(jump_map, available, pos, d):
    update_jumps(jump_map, follow_l_wall(available, pos, d))

def create_jump_map(available):
    h,w = available.shape
    jump_map = np.full([h,w,4], -1)
    for y in range(1,h-1):
        for x in range(1,w-1):
            if not available[y,x]: continue
            for d in directions:
                if jump_map[y,x,d] == -1:
                    update_jumps_from_pos(jump_map, available, (y,x), d)
    return jump_map

def jump_map_add_avail(pos, jump_map, available):
    available[pos] = True
    y,x = pos
    for d in directions:
        if jump_map[y,x,d] == -1:
            update_jumps_from_pos(jump_map, available, pos, d)

def jump_map_remove_avail(pos, jump_map, available):
    available[pos] = False
    jump_map[pos] = -1
    for d in directions:
        pos_n = dir_shift(d, pos)
        if available[pos_n]:
            update_jumps_from_pos(jump_map, available, pos_n, op_dir(d))

def available_pull_dirs(jump_map, pos, ori_d):
    jumps = jump_map[pos]
    d = ori_d
    while True:
        yield d
        d = turn_left(jumps[d])
        if d == ori_d: return

def box_positions(jump_map, available, start_pos, fw_mode):
    h,w = available.shape
    all_dirs = np.zeros([h,w,4], dtype = bool)
    fst_dir = np.full([h,w], -1)
    last_dir = np.full([h,w], -1)
    dists = np.full([h,w], -1)
    q = deque([(0, pos, d, d) for (pos,d) in start_pos])
    #for y in range(h):
    #    for x in range(w):
    #        if not available[y,x]: assert (jump_map[y,x] == -1).all(), (y,x)
    #        else: assert sorted(jump_map[y,x]) == directions, (y,x)
    #print("All OK")
    while q:
        dist,pos,d,fd = q.popleft()
        y,x = pos
        if all_dirs[y,x,d]: continue
        all_dirs[y,x,d] = True
        if last_dir[pos] < 0:
            fst_dir[pos] = fd
            last_dir[pos] = d
            dists[pos] = dist
        if fw_mode:
            pos_n = dir_shift(op_dir(d), pos)
            if not available[pos_n]: continue
        else:
            pos_n = dir_shift(d, pos)
            if not available[dir_shift(d, pos_n)]: continue
        q.extend(
            (dist+1,pos_n, d_n, fd)
            for d_n in available_pull_dirs(jump_map, pos_n, d)
        )

    return all_dirs, fst_dir, last_dir, dists

def available_box_moves(free_sq, boxes, component, fw_mode, jump_map = None):

    if jump_map is None: jump_map = create_jump_map(free_sq)
    res = dict()
    for pos in positions_true(boxes):
        start_pos = [
            (pos, d) for d in directions
            if component[dir_shift(d, pos)]
        ]
        if not start_pos: continue
        #print("Calculate", y, x)
        jump_map_add_avail(pos, jump_map, free_sq)
        all_last_dirs, fst_dir, last_dir, dists = box_positions(
            jump_map, free_sq, start_pos, fw_mode
        )
        if np.sum(last_dir >= 0) > 1:
            res[pos] = all_last_dirs, fst_dir, last_dir, dists
        jump_map_remove_avail(pos, jump_map, free_sq)

    return res
