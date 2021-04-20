#!/usr/bin/python3

# only works for forward deadlocks

import argparse
import os
from data_loader import load_xsb_levels, encode_sokoban_level_to_lines
from directions import *
from soko_state import level_to_state
from deadlocks import deadlocks_from_file
from component2d import component_split

parser = argparse.ArgumentParser(
    prog='mov_sol_to_lean',
    description='Converts deadlocks generated by sokodlex into a lean proof')
parser.add_argument('--datadir', type = str, default = "data/Large Test Suite Sets/")
parser.add_argument('--data_suffix', type = str, default = ".xsb")
parser.add_argument('fname', type=str, help='deadlocks file_name (var_dir/deadlocks), path is expected to correspond to the levelset')
args = parser.parse_args()

level_var_dir, _ = os.path.split(args.fname)
_, level_fname = os.path.split(level_var_dir)
i = level_fname.rindex('_l')
level_i = int(level_fname[i+2:])
levelset_fname = os.path.join(args.datadir, level_fname[:i]+args.data_suffix)

levels = load_xsb_levels(levelset_fname)
level = levels[level_i-1]

print("-- Deadlocks:", args.fname)
print("-- Levelset:", levelset_fname)
print("-- Level:", level_i)
print()

print("import .deadlocks")
print()
print('def {} := sokolevel.from_string "'.format(level_fname))
for line in encode_sokoban_level_to_lines(level):
    print(line)
print('"')
print()
print("namespace {}".format(level_fname))
print("open deadlocks")
print()

print("@[reducible]")
print("def deadlock_local (dl : boxint) : Prop := deadlock {}.avail {}.goal dl".format(
    level_fname, level_fname,
))
print("def deadlocks_local (dls : list boxint) : Prop")
print(":= dls.pall (λ dl, deadlock_local dl)")
print("def generate_local : list (ℕ × ℕ) → list (ℕ × ℕ) → ℕ × ℕ → boxint")
print(":= boxint.generate_from_list {}.avail".format(level_fname))
print()

def yx_to_lean_coor(yx):
    y,x = yx
    return "({},{})".format(x-1,y)
def yxs_to_lean_coor(yxs):
    return '['+', '.join(map(yx_to_lean_coor, yxs))+']'
def dl_to_lean_def(dl):
    sks = [yx for (yx,_) in component_split(dl.sk_component)]
    if len(sks) != 1:
        raise Exception("Multiple storekeepers are not supported, dl{}: {}".format(
            dl.full_index, sks
        ))
    [storekeeper] = sks
    return "def dl{} := generate_local {} {} {}".format(
        dl.full_index,
        yxs_to_lean_coor(dl.boxes),
        yxs_to_lean_coor(dl.not_boxes),
        yx_to_lean_coor(storekeeper),
    )
def dl_theorem(dl):
    return "theorem dl{}_dl : deadlock_local dl{}".format(
        dl.full_index, dl.full_index)

def print_dl_analysis(dl, fst_block_index, indent = "  "):
    print(indent+"analyze_deadlock,")
    def action_key(action):
        y,x,d = action
        is_appearance = (y+1,x+1) not in dl.boxes
        if is_appearance:
            (y,x) = dir_shift(d, (y,x))
            assert (y+1,x+1) in dl.not_boxes
        return is_appearance, y, x, d
        
    actions = sorted(dl.descendants.keys(), key = action_key)
    for action in actions:
        dl2 = dl.descendants[action]
        y,x, d = action
        box = y+1,x+1
        action_comment = "-- {} {}".format(
            yx_to_lean_coor(box), dir_to_str(d).lower()
        )
        if dl2.full_index >= fst_block_index: suffix = "in"
        else: suffix = "dl"
        print("{}deadlocked_step dl{}_{}, {}".format(
            indent, dl2.full_index, suffix,
            action_comment,
        ))

dl_blocks = deadlocks_from_file(
    args.fname, level_to_state(level), check_dependencies = True
)
for block in dl_blocks:
    if len(block) == 1:
        [dl] = block
        print(dl_to_lean_def(dl))
        print()
        print(dl_theorem(dl))
        print(":=")
        print("begin")
        print("  apply new_deadlock,")
        print_dl_analysis(dl, dl.full_index, "  ")
        print("end")
        print()
        print("#html dl{}_dl.to_html".format(dl.full_index))
        print()
    else:
        for dl in block: print(dl_to_lean_def(dl))
        dls_name = "dls{}_{}".format(block[0].full_index, block[-1].full_index)
        print("def {} := [{}]".format(
            dls_name,
            ", ".join("dl{}".format(dl.full_index) for dl in block)
        ))
        print()
        thm_name = dls_name+"_dl"
        print("theorem {} : deadlocks_local {}".format(
            thm_name, dls_name
        ))
        print(":=")
        print("begin")
        print("  refine list.pall_iff.mpr (new_deadlocks _),")
        print("  rcases list.pall_in {} with ⟨{}, irrelevant⟩,".format(
            dls_name,
            ", ".join("dl{}_in".format(dl.full_index) for dl in block)
        ))
        print("  refine list.pall_iff.mp ⟨{}trivial⟩,".format("_, "*len(block)))
        for dl in block:
            if dl == block[0]: print("  {")
            else: print("  }, {")
            print_dl_analysis(dl, block[0].full_index, "    ")
        print("  },")
        print("end")
        print()
        for i,dl in enumerate(block):
            print(dl_theorem(dl))
            print(":= " + thm_name + ".2"*i + ".1")
        print()
        for dl in block:
            print("#html dl{}_dl.to_html".format(dl.full_index))
        print()

print("end {}".format(level_fname))