import numpy as np
import itertools

from soko_state import SokoState
from deadlocks import DeadlockStack
from component2d import get_component
from helpers import *

class MoveStack:
    __slots__ = [
        "fw_mode",      # direction of moves
        "base_states",  # nonempty stack of states
        "gener_states", # gener_states[i] generalizes base_states[i]
        "state_locks",  # deadlocks corresponding to gener_states
        "moves",        # stack of moves, one shorter that the ones of states
        "cur_move_i",   # the current move index
        "deadlocks",    # structure for searching deadlocks
        "first_generalization", # index of first move where state is not sub_full
    ]

    def __init__(self, first_state, dl_fname = None, fw_mode = True):
        deadlocks = DeadlockStack(fname = dl_fname, sample_state = first_state)
        self.fw_mode = fw_mode
        self.base_states = [first_state]
        self.gener_states = [first_state]
        self.first_generalization = None
        lock = deadlocks.dl_set.find_by_state(first_state)
        if lock is None: lock = deadlocks.add(first_state, 0)
        self.state_locks = [lock]
        self.moves = []
        self.cur_move_i = 0
        self.deadlocks = deadlocks

    @property
    def state(self): return self.gener_states[self.cur_move_i]
    @property
    def base_state(self): return self.base_states[self.cur_move_i]
    @property
    def cur_lock(self): return self.state_locks[self.cur_move_i]
    @property
    def last_action(self): return self.moves[self.cur_move_i-1]
    @property
    def next_action(self): return self.moves[self.cur_move_i]

    def is_on_start(self): return self.cur_move_i == 0
    def is_on_end(self): return self.cur_move_i == len(self.moves)
    def is_solved(self): return self.state.is_solved()
    def is_locked(self):
        return self.cur_lock.stack_index != self.cur_move_i
    def is_locked_full(self): return self.cur_lock.stack_index < 0

    def drop_redo(self):
        #print("<drop_redo>", self.cur_move_i, len(self.moves))
        #print(list((i,dl.stack_index) for (i,dl) in enumerate(self.state_locks)))
        if (self.first_generalization is not None
            and self.first_generalization > self.cur_move_i):
            self.first_generalization = None
        dl_to_discard = []
        for i in range(self.cur_move_i+1, len(self.state_locks)):
            #print(i)
            if self.state_locks[i].stack_index == i:
                dl_to_discard.append(self.state_locks[i])
        self.deadlocks.remove(dl_to_discard)

        del self.base_states[self.cur_move_i+1:]
        del self.gener_states[self.cur_move_i+1:]
        del self.state_locks[self.cur_move_i+1:]
        del self.moves[self.cur_move_i:]
        #print(list((i,dl.stack_index) for (i,dl) in enumerate(self.state_locks)))
        #print("</drop_redo>")

    def generalize(self, state, check = True):
        if check: assert self.base_state.is_generalized_by(state)

        if self.cur_move_i < len(self.moves): self.drop_redo()
        prev_lock = self.state_locks.pop()
        if prev_lock.stack_index == self.cur_move_i:
            self.deadlocks.remove(prev_lock)
            prev_lock =  None

        prev_state = self.gener_states[-1]
        self.gener_states[-1] = state

        if prev_lock is None:
            lock = self.deadlocks.dl_set.find_by_state(state, ori_state = prev_state)
        elif prev_lock.check_state(state):
            lock = prev_lock
        else:
            lock = self.deadlocks.dl_set.find_by_state(state)

        if lock is None:
            lock = self.deadlocks.add(self.state, self.cur_move_i)
        self.state_locks.append(lock)

        if self.first_generalization == self.cur_move_i:
            self.first_generalization = None
        if self.first_generalization is None and not state.sub_full:
            self.first_generalization = self.cur_move_i

    def change_sub_boxes(self, new_sub_boxes):
        if (new_sub_boxes == self.state.sub_boxes).all(): return
        state = self.base_state.generalize(
            sub_boxes = new_sub_boxes,
            sup_boxes = self.state.sup_boxes,
        )
        sk = self.state.storekeeper
        if state.storekeepers[sk]:
            state = state.set_storekeeper(sk)
        self.generalize(state, check = False)
    def change_sup_boxes(self, new_sup_boxes):
        if (new_sup_boxes == self.state.sup_boxes).all(): return
        assert self.base_state.sub_full or \
            (new_sup_boxes >= self.base_state.sup_boxes).all()
        state = self.state.clone()
        # a bit of hack, using that sup_boxes don't influence anything else
        state.sup_boxes = new_sup_boxes
        self.generalize(state, check = True)

    def set_storekeeper(self, new_sk):
        self.gener_states[self.cur_move_i] = \
            self.gener_states[self.cur_move_i].set_storekeeper(new_sk)
    def set_cur_move_i(self, i):
        if i < 0: i = 0
        if i > len(self.moves): i = len(self.moves)
        if i == self.cur_move_i: return False
        self.cur_move_i = i
        return True
    def reset(self):
        return self.set_cur_move_i(0)
    def undo(self):
        return self.set_cur_move_i(self.cur_move_i - 1)
    def redo(self):
        return self.set_cur_move_i(self.cur_move_i + 1)
    def redo_max(self):
        return self.set_cur_move_i(len(self.moves))
    def revert_generalizations(self):
        if (self.first_generalization is not None
            and self.first_generalization <= self.cur_move_i):
            self.cur_move_i = self.first_generalization

    # adding to stack without deadlock check
    def _add_move(self, move, next_state, next_state_gener, lock):
        assert self.cur_move_i == len(self.moves)

        if next_state_gener is None: next_state_gener = next_state

        self.moves.append(move)
        self.cur_move_i += 1

        self.base_states.append(next_state)
        self.gener_states.append(next_state_gener)
        if lock is None:
            lock = self.deadlocks.add(next_state_gener, self.cur_move_i)
        self.state_locks.append(lock)
        if self.first_generalization is None and not next_state_gener.sub_full:
            self.first_generalization = self.cur_move_i

    def _find_next_lock(self, next_state):
        ori_lock = self.cur_lock
        if ori_lock.check_state(next_state): return ori_lock

        ori_state = None
        if not self.state.multi_component:
            if next_state.storekeepers[self.state.storekeeper]: ori_state = self.state
            elif self.state.storekeepers[next_state.storekeeper]: ori_state = self.state
        if ori_state is None:
            sk_intersect = get_component(
                next_state.available & ~next_state.sub_boxes & ~self.state.sub_boxes,
                positions_true(next_state.storekeepers),
            )
            if (self.state.storekeepers <= sk_intersect).all():
                ori_state = self.state

        return self.deadlocks.dl_set.find_by_state(next_state, ori_state = ori_state)

    # disable search_for_lock only if sure that the move does not lead to one
    def add_move(self, move, next_state, auto_generalize = True,
                 search_for_lock = True):
        if self.cur_move_i < len(self.moves): self.drop_redo()

        if search_for_lock: lock = self._find_next_lock(next_state)
        else: lock = None

        if auto_generalize:
            if lock is None or lock == self.cur_lock:
                if (next_state.sub_boxes & ~self.state.sup_boxes).any() \
                   and (self.state.sub_boxes &~ next_state.sub_boxes).any():
                    next_state_gener = next_state
                else:
                    next_state_gener = next_state.generalize(
                        next_state.sub_boxes,
                        next_state.sup_boxes | self.state.sup_boxes
                    )
            else:
                next_state_gener = lock.to_soko_state(next_state)
                next_state_gener = next_state_gener.set_storekeeper(
                    next_state.storekeeper
                )

        else: next_state_gener = next_state

        self._add_move(move, next_state, next_state_gener, lock)

    def apply_action(self, action, **kwargs):
        self.add_move(
            action,
            self.state.move(*action, fw_mode = self.fw_mode),
            **kwargs,
        )

    def find_actions_locks(self):
        
        self.drop_redo()

        action_mask = self.state.action_mask(fw_mode = self.fw_mode)
        actions = positions_true(action_mask)
        action_locks = list(self.deadlocks.dl_set.find_for_actions(
            self.state, actions, fw_mode = self.fw_mode
        ))
        free_actions = [
            action for action, dl in zip(actions, action_locks)
            if dl is None
        ]

        return actions, action_locks, free_actions

    def choose_action(self, heuristic = None, actions = None):
        if actions is None:
            if self.is_locked(): actions = None
            else: _,_,actions = self.find_actions_locks()
        if not actions: return None

        if heuristic is not None:
            logits_arr = heuristic(self.state, self.fw_mode)
            logits = [logits_arr[action] for action in actions]
            push_i = np_random_categ(np_softmax(logits))
        else: push_i = 0
        return actions[push_i]

    def search_step(self, heuristic = None, min_move = 0, auto_generalize = True):
        while True:
            # undo while deadlocked
            last_move_i = self.cur_move_i
            while self.is_locked():
                if self.cur_move_i == min_move:
                    print("Not solvable")
                    return False
                self.undo()

            if self.state.is_solved():
                print("Not a deadlock, each box is on a storage")
                return False

            # find actions not leading to a deadlock
            actions, action_locks, free_actions = \
                self.find_actions_locks()

            if free_actions: # apply an action

                self.apply_action(
                    self.choose_action(heuristic = heuristic, actions = free_actions),
                    search_for_lock = False,
                    auto_generalize = auto_generalize,
                )
                return True

            else: # store a deadlock
                self._recheck_deadlocks_on_path(
                    *self.deadlocks.set_descendants(
                        self.cur_lock, actions, action_locks
                    )
                )

    # recheck if positions in undo history are blocked by a new full deadlock
    def _recheck_deadlocks_on_path(self, scc, to_check, index_to_drop_num):

        # helper data for optimization
        nbox_union = set(itertools.chain.from_iterable(
            dl.not_boxes
            for dl in scc
        ))
        sup_intersection = np.array(self.state.available)
        for yx in nbox_union: sup_intersection = False

        dl_to_discard = []
        cur_viable = False

        # go through moves backwards
        for i in range(self.cur_move_i-1, -1, -1):

            drop_num = index_to_drop_num.get(i, 0)
            if drop_num:
                del to_check[-drop_num:]
                if not to_check: return

            state = self.gener_states[i+1]
            base_state = self.base_states[i+1]
            cur_viable = cur_viable or (state.sub_boxes < base_state.sub_boxes).any() \
                or (
                    (not state.sub_full)
                    and ((state.sup_boxes > base_state.sup_boxes) & sup_intersection).any()
                )

            if not cur_viable: continue
            if self.state_locks[i].stack_index < 0: continue
            elif self.state_locks[i].stack_index != i:
                cur_to_check = scc
            else: cur_to_check = to_check

            dl = maybe_next(filter(
                lambda dl: dl.check_state(self.gener_states[i]),
                cur_to_check,
            ))
            if dl is not None:
                ori_lock = self.state_locks[i]
                if ori_lock.stack_index == i:
                    dl_to_discard.append(ori_lock)
                self.state_locks[i] = dl
            else:
                cur_viable = False

        self.deadlocks.remove(dl_to_discard)
