#!/usr/bin/python3
import numpy as np
import os
from itertools import chain

class SokobanLevel:
    def __init__(self, walls, storages, boxes, storekeeper):
        self.walls = np.array(walls, dtype = bool)
        self.storages = np.array(storages, dtype = bool)
        self.boxes = np.array(boxes, dtype = bool)
        assert self.walls.shape == self.storages.shape
        assert self.walls.shape == self.boxes.shape
        assert np.sum(storages) == np.sum(boxes)
        assert not (self.walls & self.boxes).any()
        assert not (self.walls & self.storages).any()
        assert (self.storages != self.boxes).any()

        self.storekeeper = tuple(storekeeper)
        self.height, self.width = self.walls.shape
        assert 1 <= self.storekeeper[0] <= self.height
        assert 1 <= self.storekeeper[1] <= self.width
        # positions are indexed from 1 (to simplify wall check)
        storekeeper_m = tuple(x-1 for x in self.storekeeper)
        assert not self.boxes[storekeeper_m] and not self.walls[storekeeper_m]

def encode_sokoban_level_to_lines(level):
    num_d = {
        0  : ' ',
        1  : '#',
        2  : '.',
        4  : '$',
        6  : '*',
        8  : '@',
        10 : '+',
    }
    mix = level.walls + 2*level.storages + 4*level.boxes
    y,x = level.storekeeper
    mix[y-1,x-1] += 8
    return [
        ''.join(num_d[n] for n in n_line)
        for n_line in mix
    ]

def decode_sokoban_level_from_lines(lines):
    char_d = {
        ' ': (0,0,0,0),
        '#': (1,0,0,0),
        '.': (0,1,0,0),
        '$': (0,0,1,0),
        '*': (0,1,1,0),
        '@': (0,0,0,1),
        '+': (0,1,0,1),
    }
    m = max(len(line) for line in lines)
    lines = [
        line+(' '*(m-len(line)))
        for line in lines
    ]
    np_level = np.array([
        [char_d[x] for x in line]
        for line in lines
    ])
    walls, storages, boxes, storekeeper = np.transpose(np_level, (2,0,1))
    assert np.sum(storekeeper) == 1
    storekeeper = np.unravel_index(np.argmax(storekeeper), storekeeper.shape)
    storekeeper = tuple(x+1 for x in storekeeper)
    return SokobanLevel(walls, storages, boxes, storekeeper)

def decode_sokoban_level(item):
    return decode_sokoban_level_from_lines(item.split('|'))

def load_xsb_levels(fname):
    valid_chars = {' ', '#', '.', '$', '*', '@', '+'}
    levels = []
    with open(fname, encoding = 'windows-1250') as f:
        level_lines = []
        for line in f:
            line = line.rstrip()
            if any(c not in valid_chars for c in line): line = ""
            if line: level_lines.append(line)
            elif level_lines:
                levels.append(decode_sokoban_level_from_lines(level_lines))
                level_lines = []
        if level_lines: levels.append(decode_sokoban_level_from_lines(level_lines))

    return levels
