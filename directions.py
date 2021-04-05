import numpy as np

UP    = 0
DOWN  = 1
LEFT  = 2
RIGHT = 3

directions = [UP, DOWN, LEFT, RIGHT]

def dir_to_str(d):
    return ["UP", "DOWN", "LEFT", "RIGHT", "IDLE"][d]
def dir_to_c(d):
    return ["^", "v", "<", ">"][d]
def dir_shift(d, coor):
    if d == UP: return (coor[0]-1, coor[1])
    elif d == DOWN: return (coor[0]+1, coor[1])
    elif d == LEFT: return (coor[0], coor[1]-1)
    elif d == RIGHT: return (coor[0], coor[1]+1)
    else: raise Exception("unexpected direction {}".format(d))
def dir_shift_array(d, arr):
    res = np.zeros_like(arr)
    if d == UP: res[:-1] = arr[1:]
    elif d == DOWN: res[1:] = arr[:-1]
    elif d == LEFT: res[:,:-1] = arr[:,1:]
    elif d == RIGHT: res[:,1:] = arr[:,:-1]
    else: raise Exception("unexpected direction {}".format(d))
    return res

def op_dir(d):
    return [ DOWN, UP, RIGHT, LEFT ][d]
def turn_left(d):
    return [ LEFT, RIGHT, DOWN, UP ][d]
def turn_right(d):
    return [ RIGHT, LEFT, UP, DOWN ][d]

key_to_dir = {
    "Up"    : UP,
    "Down"  : DOWN,
    "Left"  : LEFT,
    "Right" : RIGHT,
}
c_to_dir = {
    dir_to_c(d) : d
    for d in directions
}
