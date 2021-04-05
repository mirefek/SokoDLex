#!/usr/bin/python3

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import itertools
import numpy as np
import os
import random

from move_stack import MoveStack
from data_loader import load_xsb_levels
from soko_state import level_to_state
from directions import *
from helpers import *
from heuristic import heurictic_to_storage

class SokoGUI(Gtk.Window):

    def __init__(self, levelset_fname, level_i, var_dir = 'var', win_size = (800, 600)):

        super(SokoGUI, self).__init__()

        self.dragged = None
        self.painting = None
        self.timer_id = None

        self.levelset_fname = levelset_fname
        self.levelset_basename, _ = os.path.splitext(os.path.basename(levelset_fname))
        self.levels = load_xsb_levels(levelset_fname)
        print("{} levels loaded".format(len(self.levels)))
        self.level_i = np.clip(level_i, 0, len(self.levels)-1)
        self.var_dir = var_dir

        self.make_move_stack()

        self.darea = Gtk.DrawingArea()
        self.darea.connect("draw", self.on_draw)
        self.darea.set_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                              Gdk.EventMask.BUTTON_RELEASE_MASK |
                              Gdk.EventMask.KEY_PRESS_MASK |
                              #Gdk.EventMask.SCROLL_MASK |
                              Gdk.EventMask.BUTTON1_MOTION_MASK |
                              Gdk.EventMask.BUTTON3_MOTION_MASK )
        self.add(self.darea)

        self.darea.connect("button-press-event", self.on_button_press)
        self.darea.connect("button-release-event", self.on_button_release)
        self.darea.connect("motion-notify-event", self.on_motion)
        self.connect("key-press-event", self.on_key_press)

        self.set_title("Sokoban")
        self.resize(*win_size)
        self.screen_border = 10
        self.scale = 1
        self.size = np.array(win_size)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", Gtk.main_quit)
        self.show_all()

    def make_move_stack(self):
        print("Level {}".format(self.level_i))
        state = level_to_state(self.levels[self.level_i-1])
        level_basename = self.levelset_basename + '_l' + str(self.level_i)
        level_var_dir = os.path.join(self.var_dir, level_basename)
        os.makedirs(level_var_dir, exist_ok = True)
        dl_fname = os.path.join(level_var_dir, 'deadlocks')
        self.move_stack = MoveStack(state, dl_fname = dl_fname)

    @property
    def state(self): return self.move_stack.state
    @property
    def base_state(self): return self.move_stack.base_state

    def on_key_press(self,w,e):

        keyval = e.keyval
        keyval_name = Gdk.keyval_name(keyval)
        #print(keyval_name)

        shift_pressed = bool(e.state & Gdk.ModifierType.SHIFT_MASK)

        if keyval_name == 'p':
            if self.timer_id is None:
                self.cancel()
                self.autoplay_start()
            else:
                self.cancel()
        elif keyval_name == 's':
            self.move_stack.search_step(heuristic = heurictic_to_storage)
            self.cancel()
        elif keyval_name == "Page_Up":
            if self.level_i > 1:
                self.cancel()
                self.level_i -= 1
                self.make_move_stack()
                self.darea.queue_draw()
        elif keyval_name == "Page_Down":
            if self.level_i < len(self.levels):
                self.cancel()
                self.level_i += 1
                self.make_move_stack()
                self.darea.queue_draw()
        elif keyval_name in ('Return', 'r', 'R'):
            if shift_pressed:
                self.move_stack.set_cur_move_i(len(self.move_stack.moves))
            else: self.move_stack.reset()
            self.cancel()
        elif keyval_name == 'R':
            self.move_stack.reset()
            self.cancel()
        elif keyval_name in ('BackSpace', 'z'):
            self.move_stack.undo()
            self.cancel()
        elif keyval_name in ('equal', 'Z'):
            self.move_stack.redo()
            self.cancel()
        elif keyval_name == 'a':
            self.move_stack.change_sub_boxes(self.base_state.sub_boxes)
            self.cancel()
        elif keyval_name == 'A':
            self.move_stack.change_sup_boxes(self.state.available)
            self.cancel()
        elif keyval_name == 'x':
            self.move_stack.change_sub_boxes(
                self.base_state.sub_boxes & ~self.state.sub_boxes
            )
            self.cancel()
        elif keyval_name == 'X':
            if self.base_state.sub_full: sup_boxes = self.base_state.sub_boxes
            else: sup_boxes = self.base_state.sup_boxes
            self.move_stack.change_sup_boxes(
                (sup_boxes | ~self.state.sup_boxes) & self.state.available
            )
            self.cancel()
        elif keyval_name == 'Escape':
            Gtk.main_quit()

    def to_local_coor(self, e):
        screen_border = self.screen_border
        screen_width = self.darea.get_allocated_width()
        screen_height = self.darea.get_allocated_height()
        coor = np.array([e.x, e.y])
        coor = (coor - self.size/2) / self.scale
        coor += np.array([self.state.width, self.state.height])/2
        x,y = coor
        return y,x
    def mouse_to_square(self, e, base1_index = True):
        coor = self.to_local_coor(e)
        coor = np.floor(coor).astype(int)
        y,x = coor
        if not (0 < x <= self.state.width and 0 < y <= self.state.height):
            return None

        if base1_index: return y+1,x+1
        else: return y,x

    def on_button_press(self, w, e):
        if e.type != Gdk.EventType.BUTTON_PRESS: return # ignore double clicks etc.
        self.cancel()

        if e.button == 1:
            pos = self.mouse_to_square(e, base1_index = False)
            if pos is None: return
            y,x = pos
            action_mask = self.state.action_mask()[pos]
            if action_mask.any():
                self.dragged = pos, action_mask
                self.darea.queue_draw()
        elif e.button == 3:
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

    def on_motion(self,w,e):
        if self.painting is not None:
            pos = self.apply_painting(self.mouse_to_square(e))
        if self.dragged is not None:
            box, action_mask = self.dragged

            coor = self.to_local_coor(e)
            if box == tuple(np.floor(coor).astype(int)): return
            y,x = coor - (np.array(box)+0.5)
            if abs(y) > abs(x):
                if y > 0: d = DOWN
                if y < 0: d = UP
            else:
                if x > 0: d = RIGHT
                if x < 0: d = LEFT
            if not action_mask[d]: return

            self.move_stack.apply_action(box+(d,))
            box2 = dir_shift(d, box)
            self.dragged = box2, self.state.action_mask()[box2]
            self.darea.queue_draw()

    def cancel(self, redraw = True):
        self.autoplay_stop()
        self.dragged = None
        self.painting = None
        if redraw: self.darea.queue_draw()

    def autoplay_stop(self):
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None
    def autoplay_start(self):
        self.autoplay_stop()
        self.timer_id = GLib.timeout_add(30, self.autoplay, None)
    def autoplay(self, user_data):
        actions = list(positions_true(self.state.action_mask()))
        if not actions: self.move_stack.reset()
        else: self.move_stack.apply_action(random.choice(actions))
        self.darea.queue_draw()
        return True # so that it is called again

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
    def draw_ghost_box(self, cr):
        cr.rectangle(-0.25, -0.25, 0.5, 0.5)
        cr.set_source_rgb(1, 1, 0.5)
        cr.fill()
    def draw_active_box(self, cr):
        cr.rectangle(-0.25, -0.25, 0.5, 0.5)
        cr.set_source_rgb(1, 0.5, 0)
        cr.fill()
    def draw_storage(self, cr):
        cr.rectangle(-0.25, -0.25, 0.5, 0.5)
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(0.05)
        cr.stroke()
    def draw_ghost_storekeeper(self, cr):
        cr.arc(0, 0, 0.2, 0, 2*np.pi)
        cr.set_source_rgba(0, 0, 0.5, 0.3)
        cr.fill()

    def on_draw(self, wid, cr):

        # fitting to the window center

        screen_border = self.screen_border
        screen_width = self.darea.get_allocated_width()
        screen_height = self.darea.get_allocated_height()
        self.size = np.array([screen_width, screen_height])

        cr.rectangle(0,0, screen_width, screen_height)
        if self.move_stack.is_solved():
            cr.set_source_rgb(0.0, 0.5, 0.0)
        elif self.move_stack.is_locked():
            if self.move_stack.is_locked_full():
                cr.set_source_rgb(0.5, 0.0, 0.0)
            else:
                cr.set_source_rgb(0.3, 0.3, 0.3)
        else: cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.fill()

        cr.save()
        
        self.scale = min(
            (screen_width - 2*screen_border) / self.state.width,
            (screen_height - 2*screen_border) / self.state.height,
        )
        cr.translate(*(self.size/2))
        cr.scale(self.scale, self.scale)
        cr.translate(-self.state.width/2, -self.state.height/2)

        cr.rectangle(0,0, self.state.width, self.state.height)
        cr.set_source_rgb(1, 1, 1)
        cr.fill()

        # drawing the level
        self.draw_state(cr, self.state, self.base_state)

    def draw_state(self, cr, state, base_state):
        available, sub_boxes, sup_boxes, storages, storekeepers = \
            np.transpose(state.export(), [2,0,1])
        _, base_sub_boxes, base_sup_boxes, _, _ = \
            np.transpose(base_state.export(), [2,0,1])

        blocked = available & ~sup_boxes
        blockable = available & ~base_sup_boxes & ~blocked
        disabled_boxes = base_sub_boxes & ~sub_boxes

        self.draw_array(cr, self.draw_blockable, blockable)
        self.draw_array(cr, self.draw_blocked, blocked)
        self.draw_array(cr, self.draw_box, sub_boxes)
        self.draw_array(cr, self.draw_disabled_box, disabled_boxes)
        self.draw_array(cr, self.draw_ghost_storekeeper, storekeepers)
        self.draw_array(cr, self.draw_wall, ~available)
        if self.dragged is not None:
            box, action_mask = self.dragged
            self.draw_to_yx(cr, self.draw_active_box, box)
            for d in directions:
                if action_mask[d]:
                    self.draw_to_yx(cr, self.draw_ghost_box, dir_shift(d, box))
        self.draw_array(cr, self.draw_storage, storages)

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
