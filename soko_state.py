import numpy as np

from directions import *
from helpers import positions_true
from component2d import get_component, component_split

class SokoState:
    __slots__ = [
        # relevant for ML
        "height", "width", # the original size, without the added border
        "available", # complement of walls
        "sub_boxes", # the visible boxes, in general subset of real boxes
        "sup_boxes", # positions which are not blocked as unachievable
        "storages",
        "storekeepers", # component of the storekeeper

        # additional features
        "sub_full", #  boolean, all boxes are already represented by sub_boxes
        "storekeeper", # single storekeeper position
        "goal_storekeeper", # for dual sokoban
        "multi_component", # if True, self.storekeepers can consist of multiple components
    ]
    def __init__(self, available, sub_boxes, sup_boxes, storages,
                 storekeeper, storekeepers = None, sub_full = None,
                 goal_storekeeper = None, multi_component = None):
        h,w = available.shape
        self.height = h-2
        self.width = w-2
        self.available = available
        self.sub_boxes = sub_boxes
        self.sup_boxes = sup_boxes
        self.storages = storages

        self.storekeeper = storekeeper
        self.goal_storekeeper = goal_storekeeper
        if storekeepers is None:
            multi_component = False
            self.storekeepers = get_component(available & ~sub_boxes, [storekeeper])
        else: self.storekeepers = storekeepers
        if multi_component is not None:
            self.multi_component = multi_component
        else:
            sub_comp = get_component(self.storekeepers, positions_true(self.storekeepers)[:1])
            self.multi_component = (sub_comp != self.storekeepers).any()

        if sub_full is not None: self.sub_full = sub_full
        else: self.sub_full = (np.sum(sub_boxes) == np.sum(storages))

    def clone(self):
        return SokoState(
            available = self.available,
            sub_boxes = self.sub_boxes,
            sup_boxes = self.sup_boxes,
            storages = self.storages,
            storekeepers = self.storekeepers,
            storekeeper = self.storekeeper,
            sub_full = self.sub_full,
            goal_storekeeper = self.goal_storekeeper,
            multi_component = self.multi_component,
        )

    def action_mask(self, fw_mode = True): # size: [self.width, self.height, 4]
        def action_mask_in_dir(d):
            has_box = self.sub_boxes
            if not self.sub_full:
                has_box = np.array(has_box)
                has_box |= self.sup_boxes & dir_shift_array(op_dir(d), ~self.sup_boxes)
            dest_available = self.available & ~self.sub_boxes
            if fw_mode:
                sk_reachable = dir_shift_array(d, self.storekeepers)
                dest_available = dir_shift_array(op_dir(d), dest_available)
            else:
                sk_reachable = dir_shift_array(op_dir(d), self.storekeepers)
                for _ in range(2):
                    dest_available = dir_shift_array(op_dir(d), dest_available)
            return sk_reachable & dest_available & has_box

        return np.stack(
            [
                action_mask_in_dir(d)
                for d in directions
            ],
            axis = -1,
        )[1:-1,1:-1]

    def export(self):
        return np.stack(
            [self.available, self.sub_boxes, self.sup_boxes, self.storages, self.storekeepers],
            axis = -1,
        )[1:-1,1:-1]

    def is_solved(self):
        if self.goal_storekeeper is not None and not self.storekeepers[self.goal_storekeeper]:
            return False
        return (self.sub_boxes <= self.storages).all() \
            and (self.storages <= self.sup_boxes).all()
    def score(self):
        return (np.sum(self.sub_boxes & self.storages) + np.sum(self.sup_boxes & self.storages))/2

    def move(self, y, x, d, fw_mode = True):
        box = (y+1,x+1)
        box2 = dir_shift(d, box)
        assert not self.sub_boxes[box2]
        assert self.available[box2]
        assert self.sub_boxes[box] or (self.sup_boxes[box] and not self.sup_boxes[box2])
        if fw_mode:
            assert self.storekeepers[dir_shift(op_dir(d), box)]
            storekeeper_n = box
        else:
            assert self.storekeepers[box2]
            storekeeper_n = dir_shift(d, box2)
        sub_boxes_n = np.array(self.sub_boxes)
        sub_boxes_n[box] = False
        sub_boxes_n[box2] = True
        sup_boxes_n = np.array(self.sup_boxes)
        sup_boxes_n[box] = False
        sup_boxes_n[box2] = True
        return SokoState(self.available, sub_boxes_n, sup_boxes_n, self.storages,
                         storekeeper = storekeeper_n, goal_storekeeper = self.goal_storekeeper)

    def generalize(self, sub_boxes, sup_boxes, storekeepers = None):
        assert (sub_boxes <= self.sub_boxes).all()
        if not self.sub_full: assert (self.sup_boxes <= sup_boxes).all()
        if storekeepers is None:
            if (self.sub_boxes == sub_boxes).all():
                storekeepers = self.storekeepers
            else:
                storekeepers = get_component(
                    self.available & ~sub_boxes,
                    positions_true(self.storekeepers)
                )
        return SokoState(
            self.available, sub_boxes, sup_boxes, self.storages,
            storekeepers = storekeepers, storekeeper = self.storekeeper,
            goal_storekeeper = self.goal_storekeeper,
            multi_component = self.multi_component,
        )

    def is_generalized_by(self, other):
        return (
            (other.sub_boxes <= self.sub_boxes).all() and
            (self.sub_full or (self.sup_boxes <= other.sup_boxes).all()) and
            (self.storekeepers <= other.storekeepers).all()
        )

    def set_storekeeper(self, new_sk):
        if new_sk is not None:
            assert self.storekeepers[new_sk]
        return SokoState(
            self.available, self.sub_boxes, self.sup_boxes, self.storages,
            storekeeper = new_sk, storekeepers = self.storekeepers,
            sub_full = self.sub_full,
            goal_storekeeper = self.goal_storekeeper,
            multi_component = self.multi_component,
        )

def level_to_state(level):
    size_bord = level.height+2, level.width+2
    available = np.zeros(size_bord, dtype = bool)
    available[1:-1,1:-1] = ~level.walls
    boxes = np.zeros(size_bord, dtype = bool)
    boxes[1:-1,1:-1] = level.boxes
    storages = np.zeros(size_bord, dtype = bool)
    storages[1:-1,1:-1] = level.storages

    return SokoState(available, boxes, available, storages,
                     level.storekeeper, sub_full = True)
