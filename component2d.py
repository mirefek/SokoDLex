import numpy as np
from collections import defaultdict, deque

from directions import *
from helpers import *

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

def find_path(available, start_pos, end_pos):
    q = deque([(start_pos, 4)])
    last_move = np.full(available.shape, -1)
    used = np.zeros
    while q:
        pos,d = q.popleft()
        if last_move[pos] >= 0 or not available[pos]: continue
        last_move[pos] = d
        if pos == end_pos: break
        q.extend(
            (dir_shift(d, pos), d)
            for d in directions
        )
    if last_move[end_pos] < 0: return None
    res = []
    while end_pos != start_pos:
        d = last_move[end_pos]
        res.append(d)
        end_pos = dir_shift(op_dir(d), end_pos)
    res.reverse()
    return res

# currently unused
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
def available_push_dirs(jump_map, pos, ori_d):
    for d in available_pull_dirs(jump_map, pos, op_dir(ori_d)):
        yield op_dir(d)

def find_box_jumps(jump_map, available, start_pos, fw_mode):

    h,w = available.shape
    fst_move = np.full([h,w,4], -1)
    last_move = np.full([h,w,4], -1)
    q = deque([(pos, d, d, -1) for (pos,d) in start_pos])

    if fw_mode: available_dirs = available_push_dirs
    else: available_dirs = available_pull_dirs
    #for y in range(h):
    #    for x in range(w):
    #        if not available[y,x]: assert (jump_map[y,x] == -1).all(), (y,x)
    #        else: assert sorted(jump_map[y,x]) == directions, (y,x)
    #print("All OK")
    while q:
        pos,d,fd,ld = q.popleft()
        y,x = pos
        if fst_move[y,x,d] >= 0: continue
        fst_move[y,x,d] = fd
        last_move[y,x,d] = ld

        pos_n = dir_shift(d, pos)
        if fw_mode:
            if not available[pos_n]: continue
        else:
            if not available[dir_shift(d, pos_n)]: continue

        q.extend(
            (pos_n, d_n, fd, d)
            for d_n in available_dirs(jump_map, pos_n, d)
        )

    if np.sum(last_move >= 0):
        return fst_move, last_move
    else:
        return None

def find_box_jumps_from_sk(available, boxes, box, storekeepers, fw_mode):
    clear = available & ~boxes
    clear[box] = True
    jump_map = create_jump_map(clear)
    start_pos = []
    for d in directions:
        if fw_mode: sk = dir_shift(op_dir(d), box)
        else: sk = dir_shift(d, box)
        if storekeepers[sk]: start_pos.append((box, d))

    return find_box_jumps(jump_map, clear, start_pos, fw_mode)

def find_all_box_jumps(clear, boxes, storekeepers, fw_mode, jump_map = None):

    if jump_map is None: jump_map = create_jump_map(clear)
    res = dict()
    for box in positions_true(boxes):
        start_pos = []
        for d in directions:
            if fw_mode: sk = dir_shift(op_dir(d), box)
            else: sk = dir_shift(d, box)
            if storekeepers[sk]: start_pos.append((box, d))

        if not start_pos: continue
        jump_map_add_avail(box, jump_map, clear)
        box_jumps = find_box_jumps(
            jump_map, clear, start_pos, fw_mode
        )
        if box_jumps is not None: res[box] = box_jumps
        jump_map_remove_avail(box, jump_map, clear)

    return res

def box_jump_to_pushes(dest, last_d, last_move):
    res = []
    while True:
        last_d = last_move[dest+(last_d,)]
        if last_d < 0: break
        dest = dir_shift(op_dir(last_d), dest)
        res.append((dest, last_d))
    res.reverse()
    return res
