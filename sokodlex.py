#!/usr/bin/python3

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import itertools
import numpy as np
import os
import random

from move_stack import MoveStack
from auto_select import AutoSelect
from data_loader import load_xsb_levels
from soko_state import *
from directions import *
from helpers import *
from component2d import *
from heuristic import heurictic_to_storage

class SokoGUI(Gtk.Window):

    def __init__(self, levelset_fname, level_i, var_dir = 'var', win_size = (800, 600)):

        super(SokoGUI, self).__init__()

        self.dragged = None
        self.active_box = None
        self.painting = None
        self.timer_id = None

        self.levelset_fname = levelset_fname
        self.levelset_basename, _ = os.path.splitext(os.path.basename(levelset_fname))
        self.levels = load_xsb_levels(levelset_fname)
        print("{} levels loaded".format(len(self.levels)))
        self.level_i = np.clip(level_i, 1, len(self.levels))
        self.var_dir = var_dir

        self.fw_mode = True
        self.make_move_stacks()

        self.darea = Gtk.DrawingArea()
        self.darea.connect("draw", self.on_draw)
        self.darea.set_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                              Gdk.EventMask.BUTTON_RELEASE_MASK |
                              Gdk.EventMask.KEY_PRESS_MASK |
                              #Gdk.EventMask.SCROLL_MASK |
                              Gdk.EventMask.POINTER_MOTION_MASK )
        self.add(self.darea)

        self.darea.connect("button-press-event", self.on_button_press)
        self.darea.connect("button-release-event", self.on_button_release)
        self.darea.connect("motion-notify-event", self.on_motion)
        self.connect("key-press-event", self.on_key_press)

        self.set_title("SokoDLex")
        self.resize(*win_size)
        self.screen_border = [10, 30, 10, 10]
        self.scale = 1
        self.grid_center = np.array([0, 0])
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", Gtk.main_quit)
        self.show_all()

    def make_move_stacks(self):

        print("Level {}".format(self.level_i))
        state = level_to_state(self.levels[self.level_i-1])
        dual_state = level_to_dual_state(self.levels[self.level_i-1])
        level_basename = self.levelset_basename + '_l' + str(self.level_i)
        level_var_dir = os.path.join(self.var_dir, level_basename)
        os.makedirs(level_var_dir, exist_ok = True)
        dl_fname = os.path.join(level_var_dir, 'deadlocks')
        dual_dl_fname = os.path.join(level_var_dir, 'dual_deadlocks')
        print('Preparing forward stack')
        move_stack = MoveStack(state, dl_fname = dl_fname)
        print('Preparing backward stack')
        dual_move_stack = MoveStack(dual_state, dl_fname = dual_dl_fname, fw_mode = False)
        self.move_stacks = [
            dual_move_stack, move_stack
        ]
        self.was_solved = False
        self.auto_selection = AutoSelect(move_stack, self.heuristic)
        self.update_box_jumps()
        self.level_var_dir = level_var_dir
        self.level_basename = level_basename

    def update_box_jumps(self):
        self.box_jumps = dict()
        self.box_jump_health = dict()

    def get_box_jumps(self, src):
        if src in self.box_jumps: return self.box_jumps[src]
        src1 = src[0]+1, src[1]+1
        if not self.state.sub_boxes[src1]:
            box_jumps = None
        else:
            state = self.state
            box_jumps = find_box_jumps_from_sk(
                state.available, state.sub_boxes, src1, state.storekeepers, self.fw_mode
            )
            if box_jumps is not None:
                box_jumps = box_jumps[1][1:-1,1:-1]

        self.box_jumps[src] = box_jumps
        return box_jumps

    def get_box_jump_health(self, src):
        res = self.box_jump_health.get(src, None)
        if res is not None: return res
        last_move = self.get_box_jumps(src)
        if last_move is None: return None
        
        positions = positions_true(last_move == range(4))
        if self.fw_mode: dir_f = op_dir
        else: dir_f = lambda d: d
        box_moves = [
            ((src[0]+1,src[1]+1), (y+1,x+1), dir_f(d))
            for (y,x,d) in positions
        ]
        locks = self.move_stack.deadlocks.dl_set.find_for_box_moves(
            self.state, box_moves)

        res = np.zeros_like(last_move)
        for pos, lock in zip(positions, locks):
            if lock is None: res[pos] = 3
            elif lock.stack_index >= self.move_stack.cur_move_i:
                res[pos] = 3
            elif lock.stack_index >= 0: res[pos] = 2
            else: res[pos] = 1

        self.box_jump_health[src] = res
        return res

    def cancel_box_jumps(self):
        self.box_jumps = dict()
        self.box_jump_health = dict()
    def apply_box_jump(self, src, dest):
        if src == dest: return
        pushes_candidates = []
        box_jumps = self.get_box_jumps(src)
        for d, ld in enumerate(box_jumps[dest]):
            if d == ld:
                pushes_candidates.append(box_jump_to_pushes(dest, d, box_jumps))
        pushes = min(pushes_candidates, key = len)
        for (y,x), d in pushes:
            self.move_stack.apply_action((y,x,d))
        self.update_box_jumps()

    @property
    def move_stack(self): return self.move_stacks[self.fw_mode]
    @property
    def dual_move_stack(self): return self.move_stacks[not self.fw_mode]
    @property
    def state(self): return self.move_stack.state
    @property
    def base_state(self): return self.move_stack.base_state
    @property
    def dual_state(self): return self.dual_move_stack.base_state
    @property
    def storekeeper_goal(self):
        if self.fw_mode and self.dual_move_stack.is_on_start():
            return None
        sk = self.dual_move_stack.state.storekeeper
        if self.dual_state.storekeepers[sk]: return sk
        else: return self.dual_state.storekeeper

    def heuristic(self, state, fw_mode):
        storages = self.dual_state.sub_boxes
        return heurictic_to_storage(state, fw_mode, storages = storages)
    def is_solved(self):
        is_solved = self.state.is_solved(
            other_goal = (self.dual_state.sub_boxes, self.storekeeper_goal)
        )
        if is_solved and not self.move_stack.was_generalized() and not self.was_solved:
            self.was_solved = True
            bw_move_stack, fw_move_stack = self.move_stacks
            fw_actions = fw_move_stack.get_past_actions()
            bw_actions = bw_move_stack.get_past_actions()
            fw_states = fw_move_stack.get_past_states()
            bw_states = bw_move_stack.get_past_states()
            fw_moves = []
            for state, action in zip(fw_states, fw_actions):
                fw_moves.extend(state.action_to_basic_moves(action, fw_mode = True))
            if bw_actions:
                bw_moves = [bw_actions[0][-1]]
                for state, action in zip(bw_states[1:], bw_actions[1:]):
                    bw_moves.extend(state.action_to_basic_moves(action, fw_mode = False))
                fw_state = fw_states[-1]
                bw_state = bw_states[-1]
                fw_moves.extend(
                    find_path(
                        fw_state.available & ~fw_state.sub_boxes,
                        fw_state.storekeeper,
                        bw_state.storekeeper,
                    )
                )
                bw_actions.reverse()
                bw_moves.reverse()
                fw_actions.extend(dual_action(a) for a in bw_actions)
                fw_moves.extend(op_dir(d) for d in bw_moves)

            sol_fname = "solution_{}_{}".format(len(fw_moves), len(fw_actions))
            move_fname = os.path.join(self.level_var_dir, sol_fname+".mov")
            action_fname = os.path.join(self.level_var_dir, sol_fname+".act")
            with open(move_fname, 'w') as f:
                f.write(''.join(
                    dir_to_c(d) for d in fw_moves
                )+'\n')
            with open(action_fname, 'w') as f:
                for y,x,d in fw_actions:
                    print(y, x, dir_to_c(d), file = f)
            print("Saved solution: {} moves, {} pushes".format(
                len(fw_moves), len(fw_actions)))

        return is_solved
    def search_step(self, min_move = None):
        if self.is_solved(): return False
        if self.move_stack.redo():
            if self.move_stack.is_locked(): self.move_stack.undo()
            else: return True

        if self.move_stack.search_step(heuristic = self.heuristic, min_move = min_move):
            return True
        if self.move_stack.is_solved(): self.dual_move_stack.reset()
        return False
    def auto_move(self):
        if not self.state.sub_full:
            self.move_stack.change_sub_boxes(self.base_state.sub_boxes)

        if self.is_solved():
            if self.dual_move_stack.is_on_start(): return False
            action = dual_action(self.dual_move_stack.last_action)
            if not self.move_stack.is_on_end() and action == self.move_stack.next_action:
                self.move_stack.redo()
            else: self.move_stack.apply_action(action)
            self.dual_move_stack.undo()
            return True
        elif self.move_stack.redo(): return True
        else:
            action = self.move_stack.choose_action(
                heuristic = self.heuristic)
            if action is None: return False
            self.move_stack.apply_action(action)
            return True
    def basic_move(self, d):
        sk2 = dir_shift(d, self.state.storekeeper)
        if self.state.storekeepers[sk2]:
            self.move_stack.set_storekeeper(sk2)
            return True
        elif self.state.sub_boxes[sk2]:
            y,x = sk2
            if not self.fw_mode: d = op_dir(d)
            action = y-1,x-1,d
            if self.state.action_mask(self.fw_mode)[action]:
                self.move_stack.apply_action(action)
                return True
        return False

    def on_key_press(self,w,e):

        keyval = e.keyval
        keyval_name = Gdk.keyval_name(keyval)
        #print(keyval_name)

        shift_pressed = bool(e.state & Gdk.ModifierType.SHIFT_MASK)

        if keyval_name in key_to_dir:
            d = key_to_dir[keyval_name]
            redraw = self.basic_move(d)
            self.cancel(redraw = redraw)
        elif keyval_name == 'p':
            self.auto_selection.step()
            self.cancel()
        elif keyval_name == 'P':
            self.cancel_box_jumps()
            if self.timer_id is None:
                self.cancel()
                self.timer_start(self.auto_selection.step)
            else:
                self.cancel()
        elif keyval_name == 'space':
            self.move_stack.revert_generalizations()
            self.fw_mode = not self.fw_mode
            self.update_box_jumps()
            self.cancel()
        elif keyval_name == 's':
            self.search_step()
            self.update_box_jumps()
            self.cancel()
        elif keyval_name == 'S':
            self.cancel_box_jumps()
            if self.timer_id is None:
                self.cancel()
                self.timer_start(self.search_step, self.move_stack.cur_move_i)
            else:
                self.cancel()
        elif keyval_name == 'd':
            self.cancel_box_jumps()
            if self.timer_id is None:
                self.cancel()
                self.timer_start(self.auto_move)
                self.move_stack.revert_generalizations()
            else:
                self.cancel()
        elif keyval_name == "Page_Up":
            if self.level_i > 1:
                self.cancel()
                self.level_i -= 1
                self.make_move_stacks()
                self.darea.queue_draw()
        elif keyval_name == "Page_Down":
            if self.level_i < len(self.levels):
                self.cancel()
                self.level_i += 1
                self.make_move_stacks()
                self.darea.queue_draw()
        elif keyval_name in ('Return', 'r', 'R'):
            if shift_pressed:
                self.move_stack.redo_max()
            else: self.move_stack.reset()
            self.update_box_jumps()
            self.cancel()
        elif keyval_name in ('BackSpace', 'z'):
            self.move_stack.undo()
            self.update_box_jumps()
            self.cancel()
        elif keyval_name in ('equal', 'Z'):
            self.move_stack.redo()
            self.update_box_jumps()
            self.cancel()
        elif keyval_name == 'a':
            self.move_stack.change_sub_boxes(self.base_state.sub_boxes)
            self.update_box_jumps()
            self.cancel()
        elif keyval_name == 'A':
            self.move_stack.change_sup_boxes(self.state.available)
            self.update_box_jumps()
            self.cancel()
        elif keyval_name == 'x':
            self.move_stack.change_sub_boxes(
                self.base_state.sub_boxes & ~self.state.sub_boxes
            )
            self.update_box_jumps()
            self.cancel()
        elif keyval_name == 'X':
            if self.base_state.sub_full: sup_boxes = self.base_state.sub_boxes
            else: sup_boxes = self.base_state.sup_boxes
            self.move_stack.change_sup_boxes(
                (sup_boxes | ~self.state.sup_boxes) & self.state.available
            )
            self.update_box_jumps()
            self.cancel()
        elif keyval_name == 'Escape':
            Gtk.main_quit()

    def to_local_coor(self, e):
        screen_width = self.darea.get_allocated_width()
        screen_height = self.darea.get_allocated_height()
        coor = np.array([e.y, e.x])
        coor = (coor - self.grid_center[::-1]) / self.scale
        coor += np.array([self.state.height, self.state.width])/2
        return coor
    def mouse_to_square(self, e, base1_index = True):
        coor = self.to_local_coor(e)
        coor = np.floor(coor).astype(int)
        y,x = coor
        if not (0 <= x < self.state.width and 0 <= y < self.state.height):
            return None

        if base1_index: return y+1,x+1
        else: return y,x

    def on_button_press(self, w, e):
        if e.type != Gdk.EventType.BUTTON_PRESS: return # ignore double clicks etc.

        if e.button == 1:
            if self.active_box is not None:
                self.apply_box_jump(*self.active_box)
                self.active_box = None
                self.darea.queue_draw()
                return
            if self.cancel(redraw = False): return
            pos = self.mouse_to_square(e, base1_index = False)
            if pos is None: return
            y,x = pos
            action_mask = self.state.action_mask(fw_mode = self.fw_mode)[pos]
            if action_mask.any():
                self.dragged = pos, action_mask, 'click'
                self.darea.queue_draw()
        elif e.button == 2:
            self.cancel(redraw = False)
            pos = self.mouse_to_square(e, base1_index = True)
            if pos is None or not self.state.storekeepers[pos]: return
            self.move_stack.set_storekeeper(pos)
            self.darea.queue_draw()

        elif e.button == 3:
            if self.cancel(redraw = False): return
            pos = self.mouse_to_square(e)
            if pos is None: return
            if self.base_state.sub_boxes[pos]:
                sub_boxes = np.array(self.state.sub_boxes)
                sub_boxes[pos] ^= True
                self.painting = (0, sub_boxes[pos])
                self.move_stack.change_sub_boxes(sub_boxes)
                self.darea.queue_draw()
            elif self.base_state.available[pos]:
                if self.base_state.sub_full or not self.base_state.sup_boxes[pos]:
                    sup_boxes = np.array(self.state.sup_boxes)
                    sup_boxes[pos] ^= True
                    self.painting = (1, sup_boxes[pos])
                    self.move_stack.change_sup_boxes(sup_boxes)
                    self.darea.queue_draw()
                else:
                    print("Cannot block a square, could be occupied by a hidden box")

    def on_button_release(self,w,e):
        if self.dragged is not None:
            box, _, drag_state = self.dragged
            if drag_state == 'click' and self.get_box_jumps(box) is not None:
                self.active_box = box, box
            elif drag_state == 'moved':
                self.update_box_jumps()
            self.darea.queue_draw()
            self.dragged = None
        if self.painting is not None:
            self.painting = None

    def apply_painting(self, pos):
        if pos is None: return
        paint_sup, val = self.painting
        if paint_sup:
            sup_boxes = self.state.sup_boxes
            if sup_boxes[pos] == val: return
            if not val:
                if not self.base_state.sub_full \
                   and self.base_state.sup_boxes[pos]: return
                if self.base_state.sub_boxes[pos]: return
            else:
                if not self.base_state.available[pos]: return
            sup_boxes = np.array(sup_boxes)
            sup_boxes[pos] = val
            self.move_stack.change_sup_boxes(sup_boxes)
        else:
            sub_boxes = self.state.sub_boxes
            if sub_boxes[pos] == val: return
            if val and not self.base_state.sub_boxes[pos]: return
            sub_boxes = np.array(sub_boxes)
            sub_boxes[pos] = val
            self.move_stack.change_sub_boxes(sub_boxes)
            
        self.darea.queue_draw()

    def drag_box(self, coor):
        box, action_mask, drag_state = self.dragged

        if box == tuple(np.floor(coor).astype(int)): return
        y,x = coor - (np.array(box)+0.5)
        if abs(y) > abs(x):
            if y > 0: d = DOWN
            if y < 0: d = UP
        else:
            if x > 0: d = RIGHT
            if x < 0: d = LEFT
        if not action_mask[d]:
            if drag_state == 'click':
                self.dragged = box, action_mask, 'start'
            return

        self.move_stack.apply_action(box+(d,))
        #self.update_box_jumps()
        box2 = dir_shift(d, box)
        action_mask = self.state.action_mask(fw_mode = self.fw_mode)
        cur_action_mask = action_mask[box2]
        if cur_action_mask.any():
            self.dragged = box2, cur_action_mask, 'moved'
            next_positions = np.full(action_mask.shape, -1)
            for (d,) in positions_true(cur_action_mask):
                y,x = dir_shift(d, box2)
                next_positions[y,x,d] = d
            self.box_jumps = { box2 : next_positions }
            self.box_jump_health = dict()
        else:
            self.dragged = None
            self.update_box_jumps()
        self.darea.queue_draw()

    def update_active_box(self, dest):
        if dest is None: return
        src, ori_dest = self.active_box
        if not (self.get_box_jumps(src)[dest] >= 0).any():
            dest = src
        self.active_box = src, dest
        if dest != ori_dest: self.darea.queue_draw()

    def on_motion(self,w,e):
        if self.painting is not None:
            self.apply_painting(self.mouse_to_square(e))
        elif self.dragged is not None:
            self.drag_box(self.to_local_coor(e))
        elif self.active_box is not None:
            self.update_active_box(self.mouse_to_square(e, base1_index = False))

    def cancel(self, redraw = True):
        redraw = (
            redraw
            or self.dragged is not None
            or self.active_box is not None
        )
        canceled = (
            self.timer_id is not None
            or self.dragged is not None
            or self.painting is not None
            or self.active_box is not None
        )
        self.timer_stop()
        if self.dragged is not None and self.dragged[-1] == 'moved':
            self.update_box_jumps()
        self.dragged = None
        self.active_box = None
        self.painting = None
        if redraw: self.darea.queue_draw()
        return canceled

    def timer_stop(self):
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None
            self.update_box_jumps()
    def timer_start(self, *f_args):
        self.cancel_box_jumps()
        self.timer_stop()
        self.timer_id = GLib.timeout_add(30, self.timer_step, f_args)

    def timer_step(self, f_args):
        f, *args = f_args
        repeat = f(*args)
        self.darea.queue_draw()
        if not repeat:
            self.update_box_jumps()
            self.timer_id = None
        return repeat

    # drawing
    def draw_to_yx(self, cr, draw_method, yx, base1_index = False):
        y,x = yx
        if base1_index:
            y -= 1
            x -= 1
        cr.save()
        cr.translate(x+0.5, y+0.5)
        draw_method(cr)
        cr.restore()
    def draw_array(self, cr, draw_method, arr):
        for pos in positions_true(arr):
            self.draw_to_yx(cr, draw_method, pos)

    def draw_wall(self, cr):
        cr.rectangle(-0.51, -0.51, 1.02, 1.02)
        cr.set_source_rgb(0, 0, 0)
        cr.fill()
        cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.set_line_width(0.07)
        y = 0.32
        if not self.fw_mode:
            for i in range(3):
                x = (i-1)*0.2+0.1
                x2 = x-0.2
                cr.move_to(x,-y)
                cr.line_to(x2,0)
                cr.line_to(x,y)
                cr.stroke()
    def draw_blocked(self, cr):
        cr.rectangle(-0.51, -0.51, 1.02, 1.02)
        cr.set_source_rgb(1, 0.8, 0.8)
        cr.fill()
    def draw_blockable(self, cr):
        cr.rectangle(-0.51, -0.51, 1.02, 1.02)
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.fill()
    def draw_box(self, cr):
        cr.rectangle(-0.25, -0.25, 0.5, 0.5)
        #cr.set_source_rgb(0.94, 0.63, 0.38)
        cr.set_source_rgb(0.8, 0.5, 0.2)
        cr.fill()
    def draw_disabled_box(self, cr):
        cr.rectangle(-0.25, -0.25, 0.5, 0.5)
        cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.fill()
    def draw_ghost_box(self, health):
        if health >= 3: color = 0.9, 1, 0.5
        elif health >= 2: color = 1, 0.8, 0.5
        else: color = 1, 0.5, 0.5
        def draw_ghost_box(cr):
            cr.rectangle(-0.25, -0.25, 0.5, 0.5)
            cr.set_source_rgb(*color)
            cr.fill()
        return draw_ghost_box
    def draw_active_box(self, cr):
        cr.rectangle(-0.25, -0.25, 0.5, 0.5)
        cr.set_source_rgb(1, 0.5, 0)
        cr.fill()
    def draw_storage(self, cr):
        cr.rectangle(-0.25, -0.25, 0.5, 0.5)
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(0.05)
        cr.stroke()
    def draw_happy_storage(self, cr):
        cr.rectangle(-0.25, -0.25, 0.5, 0.5)
        cr.set_source_rgb(0, 0.5, 0)
        cr.set_line_width(0.08)
        cr.stroke()
    def draw_storekeeper(self, cr):
        cr.arc(0, 0, 0.15, 0, 2*np.pi)
        cr.set_source_rgb(0, 0, 1)
        cr.fill()
    def draw_ghost_storekeeper(self, cr):
        cr.arc(0, 0, 0.15, 0, 2*np.pi)
        cr.set_source_rgba(0, 0, 0.5, 0.3)
        cr.fill()
    def draw_storekeeper_goal(self, cr):
        cr.arc(0, 0, 0.15, 0, 2*np.pi)
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(0.05)
        cr.stroke()
    def draw_happy_storekeeper_goal(self, cr):
        cr.arc(0, 0, 0.15, 0, 2*np.pi)
        cr.set_source_rgb(0, 0.5, 0)
        cr.set_line_width(0.05)
        cr.stroke()

    def on_draw(self, win, cr):

        # fitting to the window center

        screen_border = self.screen_border
        screen_width = self.darea.get_allocated_width()
        screen_height = self.darea.get_allocated_height()
        self.grid_center = np.array([screen_width, screen_height], dtype = float)
        self.grid_center[0] += screen_border[LEFT]
        self.grid_center[0] -= screen_border[RIGHT]
        self.grid_center[1] += screen_border[UP]
        self.grid_center[1] -= screen_border[DOWN]
        self.grid_center /= 2

        cr.rectangle(0,0, screen_width, screen_height)
        text_color = (1,1,1)
        if self.is_solved() or self.auto_selection.is_solvable(self.state):
            cr.set_source_rgb(0.0, 0.5, 0.0)
        elif self.move_stack.is_locked():
            if self.move_stack.is_locked_full():
                cr.set_source_rgb(0.5, 0.0, 0.0)
            else:
                cr.set_source_rgb(0.3, 0.3, 0.3)
        else:
            text_color = (0,0,0)
            cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.fill()

        cr.save()

        screen_border_v = screen_border[UP] + screen_border[DOWN]
        screen_border_h = screen_border[LEFT] + screen_border[RIGHT]
        self.scale = min(
            (screen_width - screen_border_h) / self.state.width,
            (screen_height - screen_border_v) / self.state.height,
        )

        cr.save()
        cr.translate(*self.grid_center)
        cr.scale(self.scale, self.scale)
        cr.translate(-self.state.width/2, -self.state.height/2)

        cr.rectangle(0,0, self.state.width, self.state.height)
        cr.set_source_rgb(1, 1, 1)
        cr.fill()

        self.draw_state(cr)
        cr.restore()

        cr.set_font_size(20)
        cr.set_source_rgb(*text_color)
        cr.move_to(10, screen_height-7)
        cr.show_text(self.level_basename)

        bw_moves, fw_moves = [stack.cur_move_i for stack in self.move_stacks]
        if bw_moves:
            text = "{} + {}".format(fw_moves, bw_moves)
        else: text = str(fw_moves)
        _, _, _, _, dx, _ = cr.text_extents(text)
        cr.move_to(screen_width-10-dx, screen_height-7)
        cr.show_text(text)

    # drawing the level
    def draw_state(self, cr):
        state = self.state
        base_state = self.base_state
        dual_state = self.dual_state
        available = state.available[1:-1,1:-1]
        sub_boxes = state.sub_boxes[1:-1,1:-1]
        sup_boxes = state.sup_boxes[1:-1,1:-1]
        storekeepers = state.storekeepers[1:-1,1:-1]
        storages = dual_state.sub_boxes[1:-1,1:-1]
        base_sub_boxes = base_state.sub_boxes[1:-1,1:-1]
        base_sup_boxes = base_state.sup_boxes[1:-1,1:-1]
        sk_goal = self.storekeeper_goal

        blocked = available & ~sup_boxes
        disabled_boxes = base_sub_boxes & ~sub_boxes

        if not base_state.sub_full:
            blockable = available & ~base_sup_boxes & ~blocked
            self.draw_array(cr, self.draw_blockable, blockable)
        self.draw_array(cr, self.draw_blocked, blocked)
        self.draw_array(cr, self.draw_box, sub_boxes)
        self.draw_array(cr, self.draw_disabled_box, disabled_boxes)
        if not self.active_box:
            self.draw_array(cr, self.draw_ghost_storekeeper, storekeepers)
        self.draw_to_yx(cr, self.draw_storekeeper, state.storekeeper,
                        base1_index = True)
        self.draw_array(cr, self.draw_wall, ~available)
        if self.dragged is not None:
            box, action_mask, _ = self.dragged
            self.draw_to_yx(cr, self.draw_active_box, box)
            for d in directions:
                if action_mask[d]:
                    box2 = dir_shift(d, box)
                    if self.get_box_jump_health(box) is None: h = 0
                    else: h = np.max(self.get_box_jump_health(box)[box2])
                    self.draw_to_yx(cr, self.draw_ghost_box(h), box2)
        elif self.active_box is not None:
            src, dest = self.active_box
            jump_health = self.get_box_jump_health(src)
            jump_health = np.max(jump_health, axis = -1)
            jump_health[src] = 3
            for h in (1,2,3):
                self.draw_array(cr, self.draw_ghost_box(h), jump_health == h)
            self.draw_to_yx(cr, self.draw_active_box, dest)
        self.draw_array(cr, self.draw_storage, storages & ~sub_boxes)
        self.draw_array(cr, self.draw_happy_storage, storages & sub_boxes)
        if sk_goal is not None:
            if state.storekeepers[sk_goal]:
                self.draw_to_yx(cr, self.draw_happy_storekeeper_goal, sk_goal,
                                base1_index = True)
            else:
                self.draw_to_yx(cr, self.draw_storekeeper_goal, sk_goal,
                                base1_index = True)
        self.draw_array(cr, self.draw_storage, storages & ~sub_boxes)

if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser(prog='sokodlex',
                                     description='GUI for examining sokoban deadlocks',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('level', type=int, nargs='?', default = 1, help='Level number 1 ... len(levels)')
    parser.add_argument('levelset', type=str, nargs='?',
                        default = './data/Large Test Suite Sets/XSokoban_90.xsb',
                        help='file to load the level set (in xsb format)')
    args = parser.parse_args()

    win = SokoGUI(args.levelset, args.level)
    Gtk.main()
