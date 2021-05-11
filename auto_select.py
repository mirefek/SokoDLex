from collections import defaultdict
import random
import numpy as np

from helpers import *
from component2d import component_split

class AutoSelect:
    def __init__(self, move_stack, heuristic):
        self.stack = move_stack
        self.heuristic = heuristic
        self.box_size_to_solvable = defaultdict(list)
        self.solvable_exact = dict()

        available = move_stack.state.available
        storages = move_stack.state.storages
        for sk, sks in component_split(available & ~storages):
            self.add_solvable(storages, sk, sks)
        self.forbid_gener = None
        self.steps = 0

    def step(self):
        self.steps += 1
        if self.stack.is_locked():
            if self.forbid_gener == self.stack.cur_move_i:
                self.forbid_gener = None
            return self.stack.undo()
        elif self.is_solvable(self.stack.state):
            if (self.stack.state.sub_boxes < self.stack.base_state.sub_boxes).any():
                # ungeneralize
                self.stack.change_sub_boxes(self.stack.base_state.sub_boxes)
                return True

            # undo and set solvable
            if self.forbid_gener == self.stack.cur_move_i:
                self.forbid_gener = None
            if not self.stack.undo(): return False
            self.add_solvable(
                self.stack.state.sub_boxes,
                self.stack.state.storekeeper,
                self.stack.state.storekeepers,
            )
            return True

        # try a free action
        actions, action_locks, free_actions = \
            self.stack.find_actions_locks()
        if free_actions:
            action = self.stack.choose_action(
                heuristic = self.heuristic,
                actions = free_actions,
            )
            self.stack.apply_action(action, search_for_lock = False)
            return True

        # try to remove a box
        boxes = positions_true(self.stack.state.sub_boxes)
        if len(boxes) > 1 and self.forbid_gener is None:
            perm = np.random.permutation(len(boxes))
            sk = self.stack.state.storekeeper
            for i in perm:
                boxes2 = list(boxes)
                del boxes2[i]
                if self.is_solvable_exact(tuple(boxes2), sk): continue
                boxes2_a = np.array(self.stack.state.sub_boxes)
                boxes2_a[boxes[i]] = False
                self.stack.change_sub_boxes(boxes2_a)
                return True

        # set as deadlock
        self.stack._recheck_deadlocks_on_path(
            *self.stack.deadlocks.set_descendants(
                self.stack.cur_lock, actions, action_locks
            )
        )
        lock = self.stack.cur_lock
        if lock.stack_index >= 0: self.forbid_gener = lock.stack_index
        return True

    def add_solvable_exact(self, boxes, sks):
        sks_ori = self.solvable_exact.setdefault(boxes, sks)
        if sks_ori is not sks:
            self.solvable_exact[boxes] = sks_ori | sks

    def is_solvable_exact(self, boxes, sk):
        sks = self.solvable_exact.get(boxes, None)
        if sks is None: return False
        return sks[sk]

    def add_solvable(self, boxes_a, sk, sks):
        boxes = positions_true(boxes_a)
        self.add_solvable_exact(boxes, sks)
        for box in boxes:
            for size in range(1, len(boxes)):
                self.box_size_to_solvable[box, size].append((boxes_a, sk))


    def is_solvable(self, state):
        boxes = positions_true(state.sub_boxes)
        if not boxes: return True
        if self.is_solvable_exact(boxes, state.storekeeper): return True
        candidatess = [
            self.box_size_to_solvable.get((box, len(boxes)), ())
            for box in boxes
        ]
        candidates = min(candidatess, key = len)
        for boxes_cand, sk in candidates:
            if not state.storekeepers[sk]: continue
            for box in boxes:
                if not boxes_cand[box]: break
            else:
                self.add_solvable_exact(boxes, state.storekeepers)
                return True

        return False

    def generalization_is_free(self):
        if self.stack.is_locked: return True
        lock = self.stack.cur_lock
        dl_stack = self.stack.deadlocks
        return not dl_stack.dependencies.neighbors_B(lock)
