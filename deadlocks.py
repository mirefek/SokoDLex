from collections import defaultdict
from itertools import combinations, chain
import sys
import os
import random

from helpers import *
from directions import *
from digraph import Digraph
from soko_state import SokoState
from component2d import get_component, component_split

class Deadlock:
    __slots__ = ["boxes", "not_boxes", "sk_component",
                 "full_index", "descendants", "stack_index" ]
    def __init__(self, boxes_sorted, not_boxes, sk_component):

        # copy of a SokoState stored in a different format
        self.boxes = boxes_sorted
        self.not_boxes = not_boxes
        self.sk_component = sk_component

        # Deadlock types:
        # options:
        # a) on stack ->
        #    relevant: stack_index,
        #    None: descendants, full_index, low_stack_jump
        #    dependencies: only B node
        # b) out of stack ->
        #    relevant: stack_index, descendands,
        #      stack_index = highest i on stack where I can jump to
        #         < original stack_index
        #    None: full_index
        #    dependencies: AB node
        # c) full ->
        #    relevant: descendands, full_index,
        #    None: stack_index
        #    dependencies: out of the graph

        self.stack_index = -1
        self.full_index = None
        self.descendants = None

    ###  Deadlock checking

    def check_sets(self, boxes_set, nboxes_set, storekeeper):
        return (
            all(box in boxes_set for box in self.boxes)
            and self.nboxes_check_sets(boxes_set, nboxes_set)
            and self.sk_component[storekeeper]
        )
    def nboxes_check_sets(self, boxes_set, nboxes_set):
        if nboxes_set is None: return all(box not in boxes_set for box in self.not_boxes)
        else: return all(box in nboxes_set for box in self.not_boxes)

    def check_state(self, state):
        if state.multi_component:
            if not (state.storekeepers <= self.sk_component).all(): return False
        else:
            if not self.sk_component[state.storekeeper]: return False
        if state.sub_full:
            if any(state.sub_boxes[nbox] for nbox in self.not_boxes): return False
        else:
            if any(state.sup_boxes[nbox] for nbox in self.not_boxes): return False

        return all(state.sub_boxes[box] for box in self.boxes)

    def check_dependencies(self, base_state, fw_mode = True):
        state = self.to_soko_state(base_state)
        assert not state.is_solved()
        for action in positions_true(state.action_mask(fw_mode = fw_mode)):
            state2 = state.move(*action, fw_mode = fw_mode)
            dl2 = self.descendants[action]
            assert dl2.check_state(state2)

    ### Export

    def to_soko_state(self, base_state):
        sub_boxes = np.zeros_like(base_state.available)
        sup_boxes = np.array(base_state.available)
        for box in self.boxes: sub_boxes[box] = True
        for nbox in self.not_boxes: sup_boxes[nbox] = False
        storekeeper = positions_true(self.sk_component)[0]
        return SokoState(
            base_state.available, sub_boxes, sup_boxes,
            base_state.storages,
            storekeeper, self.sk_component,
        )

    def print_self(self, file = sys.stdout):
        print("Deadlock {}".format(self.full_index), file = file)
        print("  Storekeeper:", ", ".join(
            "{} {}".format(y-1,x-1)
            for (y,x),_ in component_split(self.sk_component)
        ),  file = file)
        print("  Boxes:", ", ".join("{} {}".format(y-1,x-1)
                                    for y,x in self.boxes), file = file)
        print("  Blocked:", ", ".join("{} {}".format(y-1,x-1)
                                      for y,x in self.not_boxes), file = file)
        if self.descendants is None:
            print("  Actions unknown")
        else:
            for (y,x,d), desc in self.descendants.items():
                print("  Action {} {} {} -> {}".format(
                    y,x,dir_to_c(d), desc.full_index
                ), file = file)

def deadlock_from_state(state):
    boxes_sorted = positions_true(state.sub_boxes)
    if state.sub_full: not_boxes = ()
    else: not_boxes = positions_true(state.available & ~state.sup_boxes)
    return Deadlock(boxes_sorted, not_boxes, state.storekeepers)

class DeadlockSet:
    def __init__(self):
        self.box_dl = Digraph() # box node -> deadlocks

        self._boxes_to_deadlock = defaultdict(list)
        self._box_to_size_to_nodeA = defaultdict(dict)
        self._nbox_to_size_to_nodeA = defaultdict(dict)
        self._last_node = -1

    def _get_node(self, d, box, size):
        node = d[box].get(size, None)
        if node is not None: return node
        self._last_node += 1
        d[box][size] = self._last_node
        self.box_dl.add_node_A(self._last_node)
        return self._last_node
    
    def add(self, deadlock):
        if isinstance(deadlock, SokoState):
            deadlock = deadlock_from_state(deadlock)
        self.box_dl.add_node_B(deadlock)
        self._boxes_to_deadlock[deadlock.boxes].append(deadlock)
        size = len(deadlock.boxes)
        for box in deadlock.boxes:
            node = self._get_node(self._box_to_size_to_nodeA, box, size)
            self.box_dl.add_edge(node, deadlock)
        for nbox in deadlock.not_boxes:
            node = self._get_node(self._nbox_to_size_to_nodeA, nbox, size)
            self.box_dl.add_edge(node, deadlock)
        return deadlock

    def remove(self, deadlock):
        self._boxes_to_deadlock[deadlock.boxes].remove(deadlock)
        self.box_dl.remove_node_B(deadlock)

    def find(self, new_boxes, new_nboxes, ori_boxes, ori_nboxes, storekeeper):

        size_to_nodes = defaultdict(list)
        def gen_size_to_node():
            for box in new_boxes:
                size_to_node = self._box_to_size_to_nodeA.get(box, None)
                if size_to_node != None: yield size_to_node
            for nbox in new_nboxes:
                size_to_node = self._nbox_to_size_to_nodeA.get(nbox, None)
                if size_to_node != None: yield size_to_node
        for size_to_node in gen_size_to_node():
            for size, nodeA in size_to_node.items():
                size_to_nodes[size].append(nodeA)

        if not size_to_nodes: return None

        boxes_set = set(ori_boxes)
        boxes_set.update(new_boxes)
        boxes_set.difference_update(new_nboxes)
        boxes_sorted = sorted(boxes_set)
        max_size = len(boxes_sorted)
        size_to_nodes_items = sorted(
            filter(lambda item: item[0] <= max_size,
                   size_to_nodes.items())
        )
        if ori_nboxes is None: nboxes_set = None
        else:
            nboxes_set = set(ori_nboxes)
            nboxes_set.update(new_nboxes)
            nboxes_set.difference_update(new_boxes)
        
        for size, box_nodes in size_to_nodes_items:
            candidate_sets = [self.box_dl.neighbors_A(box_node) for box_node in box_nodes]
            if sum(len(candidates) for candidates in candidate_sets) < size*binom(max_size, size):
                if len(candidate_sets) == 1: candidates = candidate_sets[0]
                else: candidates = set().union(*candidate_sets)
                for deadlock in candidates:
                    if deadlock.check_sets(boxes_set, nboxes_set, storekeeper):
                        yield deadlock
            else:
                for subboxes in combinations(boxes_sorted, size):
                    for deadlock in self._boxes_to_deadlock[subboxes]:
                        if deadlock.sk_component[storekeeper] \
                           and deadlock.nboxes_check_sets(boxes_set, nboxes_set):
                            yield deadlock

    def find_one(self, new_boxes, new_nboxes, ori_boxes, ori_nboxes, storekeeper,
                 condition = None):
        deadlocks = self.find(
            new_boxes, new_nboxes, ori_boxes, ori_nboxes, storekeeper)
        if condition is not None:
            deadlocks = filter(condition, deadlocks)
        return maybe_next(deadlocks)

    def find_by_state(self, state, ori_state = None):

        sub_boxes = state.sub_boxes
        if state.sub_full: sup_boxes = sub_boxes
        else: sup_boxes = state.sup_boxes

        if ori_state is None:
            ori_sub_boxes = np.zeros_like(state.available)
            ori_sup_boxes = state.available
        else:
            ori_sub_boxes = ori_state.sub_boxes
            if ori_state.sub_full:
                ori_sup_boxes = ori_state.sub_boxes
            else:
                ori_sup_boxes = ori_state.sup_boxes

        ori_boxes = positions_true(sub_boxes)
        ori_nboxes = positions_true(~sup_boxes & state.available)
        new_boxes = positions_true(sub_boxes & ~ori_sub_boxes)
        new_nboxes = positions_true(~sup_boxes & ori_sup_boxes)

        if state.storekeepers is not None:
            storekeeper = state.storekeeper
        else: storekeeper = positions_true(state.storekeepers)[0]
        if state.multi_component:
            condition = lambda deadlock: (state.storekeepers <= deadlock.sk_component).all()
        else: condition = None

        return self.find_one(
            new_boxes, new_nboxes, ori_boxes, ori_nboxes, storekeeper,
            condition = condition,
        )

    def find_for_box_moves(self, state, box_moves):

        if state.multi_component:
            for box_src, box_dest, sk_dir in box_moves:

                sub_boxes = np.array(state.sub_boxes)
                sup_boxes = np.array(state.sup_boxes)
                sub_boxes[box_src] = False
                sup_boxes[box_src] = False
                sub_boxes[box_dest] = True
                sup_boxes[box_dest] = True
                state2 = SokoState(
                    available = state.available,
                    sub_boxes = sub_boxes,
                    sup_boxes = sup_boxes,
                    storages = state.storages,
                    sub_full = state.sub_full,
                    storekeeper = dir_shift(sk_dir, box_dest),
                    storekeeper_goal = state.storekeeper_goal,
                )
                yield self.find_by_state(state2)

        else:
            ori_boxes = positions_true(state.sub_boxes)
            if state.sub_full: ori_nboxes = None
            else: ori_nboxes = positions_true(state.available & ~state.sup_boxes)

            for box_src, box_dest, sk_dir in box_moves:
                storekeeper = dir_shift(sk_dir, box_dest)
                yield self.find_one([box_dest], [box_src], ori_boxes, ori_nboxes, storekeeper)

    def find_for_actions(self, state, actions, fw_mode = True):
        box_moves = []
        for y,x,d in actions:
            box_src = (y+1,x+1)
            box_dest = dir_shift(d, box_src)
            if fw_mode: sk_dir = op_dir(d)
            else: sk_dir = d
            box_moves.append((box_src, box_dest, sk_dir))
        return self.find_for_box_moves(state, box_moves)

class DeadlockStack:
    def __init__(self, dl_set = None, fname = None, sample_state = None):
        self.fname = fname
        self.dependencies = Digraph() # deadlock -> descendants
        if dl_set is None: dl_set = DeadlockSet()
        self.dl_set = dl_set
        self._last_full_index = -1

        self.debug_data = []
        self.debug_fname = "bug.log"

        if fname is not None:
            assert sample_state is not None
            if os.path.exists(fname):
                print("loading deadlocks...")
                try:
                    blocks = deadlocks_from_file(fname, sample_state)
                except:
                    blocks = None
                    def backup_fnames_gen():
                        base_fname = fname+"_backup"
                        yield base_fname
                        i = 0
                        while True:
                            yield base_fname+str(i)
                    backup_fnames = backup_fnames_gen()
                    while True:
                        backup_fname = next(backup_fnames)
                        if not os.path.exists(backup_fname): break
                    os.rename(fname, backup_fname)
                    print("deadlock file corrupted, renamed to '{}'".format(backup_fname))

                if blocks is not None:
                    for dl in chain.from_iterable(blocks):
                        self.debug_data.append(
                            "dummy_deadlocks[{}] = make_dummy_deadlock({})".format(
                                id(dl), dl.full_index
                            ))
                        self.dl_set.add(dl)
                        self._last_full_index = dl.full_index
                    print("loaded {} deadlocks".format(self._last_full_index+1))

    def add(self, deadlock, stack_index):
        assert stack_index >= 0
        if isinstance(deadlock, SokoState):
            deadlock = deadlock_from_state(deadlock)
        self.debug_data.append(
            "dummy_deadlocks[{}] = dl_stack.add(make_dummy_deadlock(), {})".format(
                id(deadlock), stack_index,
            ))
        deadlock.stack_index = stack_index
        self.dl_set.add(deadlock)
        self.dependencies.add_node_B(deadlock)
        return deadlock

    # supports removing multiple deadlocks at once
    # discards also deadlocks dependent on it
    def remove(self, deadlocks):
        if isinstance(deadlocks, Deadlock): deadlocks = [deadlocks]
        self.debug_data.append(
            "dl_stack.remove([dummy_deadlocks[i] for i in {}])".format(
                [id(dl) for dl in deadlocks]
            ))
        dependent = self.dependencies.closure_BA(deadlocks)
        for deadlock in dependent:
            self.dl_set.remove(deadlock)
            self.dependencies.remove_node_B(deadlock)
            if deadlock.descendants is not None:
                self.dependencies.remove_node_A(deadlock)

    def make_full(self, deadlock):
        assert deadlock.full_index == None
        deadlock.stack_index = -1
        self.dependencies.remove_node(deadlock)
        self._last_full_index += 1
        deadlock.full_index = self._last_full_index

    def set_descendants(self, deadlock, pushes, descendants):
        self.debug_data.append(
            "dl_stack.set_descendants(dummy_deadlocks[{}], [None]*{}, [dummy_deadlocks[i] for i in {}])".format(
                  id(deadlock), len(descendants),
                  [id(dl) for dl in descendants],
            ))

        try:

            assert deadlock.descendants is None
            assert len(pushes) == len(descendants)
            deadlock.descendants = dict(zip(pushes, descendants))

            # add to dependency graph

            self.dependencies.add_node_A(deadlock)
            for descendant in descendants:
                if descendant.stack_index >= 0:
                    self.dependencies.add_edge(deadlock, descendant)

            # update stack_index where necessary

            to_check = self.dependencies.closure_BA([deadlock])
            ori_stack_index = deadlock.stack_index
            assert all(dl.stack_index == ori_stack_index for dl in to_check)

            # find elements of to_check looking outside
            new_stack_indices = defaultdict(list)
            for dl in to_check:
                new_stack_index = max([
                    desc.stack_index for desc in self.dependencies.neighbors_A(dl)
                    if desc.stack_index != ori_stack_index
                ], default = -1)
                if new_stack_index >= 0:
                    assert (new_stack_index < ori_stack_index), (new_stack_index, ori_stack_index)
                    new_stack_indices[new_stack_index].append((dl, new_stack_index))
            dfs_stack = list(chain.from_iterable(
                new_stack_indices[i]
                for i in sorted(new_stack_indices.keys())
            ))

            # propagate the right stack_index backwards
            to_check_l = []
            size_of_index = defaultdict(int)
            while dfs_stack:
                dl,i = dfs_stack.pop()
                if dl not in to_check: continue
                to_check_l.append(dl)
                size_of_index[i] += 1
                to_check.remove(dl)
                dl.stack_index = i
                dfs_stack.extend(
                    (dl2, i)
                    for dl2 in self.dependencies.neighbors_B(dl)
                )

            # mark a strongly connected component as a full deadlock
            scc = list(to_check)
            if scc:
                for dl in scc: self.make_full(dl)

                if self.fname is not None:
                    with open(self.fname, 'a') as f:
                        print(file = f)
                        for dl in scc: dl.print_self(file = f)
                    if len(scc) == 1:
                        print("Saved deadlock {}".format(scc[0].full_index))
                    else:
                        print("Saved deadlocks {}-{}".format(
                            scc[0].full_index, scc[-1].full_index
                        ))

            # output for checking on path
            to_check_l.reverse()
            return scc, scc+to_check_l, size_of_index

        except Exception:
            if self.debug_fname is not None:
                with open(self.debug_fname, 'w') as f:
                    for l in self.debug_data:
                        print(l, file = f)
                print("error in DeadlockStack occured, debug data stored in "+self.debug_fname)
                self.debug_fname = None

            raise

    def check_correct(self):
        for dl in self.dependencies.nodes_A():
            assert dl.stack_index == max([
                dl2.stack_index for dl2 in dl.descendants.values()
            ], default = -1)

def deadlocks_from_file(fname, base_state):

    def tokenized_lines_gen(f):
        for line in f:
            line = line.strip()
            if not line: continue
            title_line = remove_prefix(line, "Deadlock")
            if title_line is not None:
                yield 'title', int(title_line)
                continue
            act_line = remove_prefix(line, "Action")
            if act_line is not None:
                y,x,d,arr,desc = act_line.split()
                y = int(y)
                x = int(x)
                d = c_to_dir[d]
                assert arr == '->'
                desc = int(desc)
                yield 'action', (y,x,d), desc
                continue
            else:
                label, data_s = line.split(':')
                if data_s.strip():
                    data = tuple(
                        tuple(int(x)+1 for x in pos.split())
                        for pos in data_s.split(',')
                    )
                else: data = ()
                assert all(len(pos) == 2 for pos in data)
                yield 'std', label, data

    def read_title(title_tokens):
        label, index = title_tokens
        assert label == 'title'
        return index
    def read_std(std_tokens, desired_label2):
        label, label2, data = std_tokens
        assert label == 'std'
        assert label2 == desired_label2
        return data
    def read_action(action_tokens):
        if action_tokens is None or action_tokens[0] != 'action': return None
        _, action, desc = action_tokens
        return action, desc

    def deadlock_data_gen(tokenized_lines):
        tokens = maybe_next(tokenized_lines)
        while True:
            if tokens is None: return
            index = read_title(tokens)
            storekeeper = read_std(next(tokenized_lines), "Storekeeper")
            boxes = read_std(next(tokenized_lines), "Boxes")
            blocked = read_std(next(tokenized_lines), "Blocked")
            action_data = []
            while True:
                tokens = maybe_next(tokenized_lines)
                action = read_action(tokens)
                if action is None: break
                action_data.append(action)
            yield index, storekeeper, boxes, blocked, action_data
            if tokens is None: break

    def deadlock_blocks_gen(deadlock_data):
        max_index = 0
        dl_list = []
        cur_block = []
        for index, storekeeper, boxes, blocked, action_data in deadlock_data:
            assert index == len(dl_list), (index, last_index)

            available = np.array(base_state.available)
            for box in boxes: available[box] = False
            sk_component = get_component(available, storekeeper)
            deadlock = Deadlock(boxes, blocked, sk_component)
            deadlock.full_index = index

            dl_list.append(deadlock)
            cur_block.append((deadlock, action_data))
            max_cur = max((desc for _,desc in action_data), default = max_index)
            max_index = max(max_cur, max_index)
            if max_index == index:
                max_index += 1
                for deadlock, action_data in cur_block:
                    deadlock.descendants = {
                        action : dl_list[i]
                        for action, i in action_data
                    }
                    #deadlock.check_dependencies(base_state)
                yield [dl for dl,_ in cur_block]
                cur_block = []
        assert not cur_block

    with open(fname) as f:
        tokenized_lines = tokenized_lines_gen(f)
        deadlock_data = deadlock_data_gen(tokenized_lines)
        deadlock_blocks = deadlock_blocks_gen(deadlock_data)
        out = list(deadlock_blocks)

    return out
        #for index, storekeeper, boxes, blocked, action_data in deadlock_data:
        #    print("Deadlock", index)
        #    print("  Storekeeper:", boxes)
        #    print("  Boxes:", boxes)
        #    print("  Blocked:", blocked)
        #    for action in action_data:
        #        print("  Action", action)

if __name__ == "__main__":
    deadlocks_from_file("var/XSokoban_90_l26/deadlocks")
