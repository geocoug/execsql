"""Native action descriptions and controls must fit without maximizing."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize("overflow", [False, True])
@pytest.mark.parametrize("busy_events", [False, True])
@pytest.mark.parametrize("late_layout", [False, True])
def test_native_action_controls_fit_initial_window_and_overflow_scrolls(overflow, busy_events, late_layout):
    pytest.importorskip("tkinter")
    script = """
import json, sys, tkinter as tk
from tkinter import ttk
from execsql.gui.desktop import ActionDialog
from execsql.utils.gui import ActionSpec
options = json.loads(sys.argv[1])
try:
    root=tk.Tk()
except tk.TclError as exc:
    print('TK_UNAVAILABLE:',exc)
    raise SystemExit(77)
root.withdraw()
errors=[]
def failed(*exc):
    import traceback
    errors.append(''.join(traceback.format_exception(*exc)))
    root.destroy()
root.report_callback_exception=failed
specs=[ActionSpec('Record selected row',('Long description with wrapping. '*15) if options['overflow'] else 'Runs a script using this row','record',data_required=True)]
if options['overflow']:
    specs += [ActionSpec('Action '+str(i),'A wrapping action description. '*10,'record') for i in range(1,12)]
args={'message':("3/5 - Select O'Brien, then click Record selected row. This must run its action exactly once. ")*(6 if options['overflow'] else 1),
      'button_specs':specs,'column_headers':['id','name','note'],'rowset':[(1,'Alice','ordinary'),(2**60,"O'Brien",None),(3,'Charlie','ordinary')]}
def walk(parent):
    for child in parent.winfo_children():
        yield child
        yield from walk(child)
def inside(widget,win):
    return widget.winfo_ismapped() and widget.winfo_rooty() >= win.winfo_rooty() and widget.winfo_rooty()+widget.winfo_height() <= win.winfo_rooty()+win.winfo_height()
phase=['dialog to become visible']
def wait_until(predicate, callback, description):
    phase[0]=description
    def poll():
        if predicate():
            callback()
        else:
            root.after(10, poll)
    root.after(0, poll)
def inspect():
    win=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
    controls=list(walk(win))
    cancel=next(w for w in controls if isinstance(w,ttk.Button) and w.cget('text')=='Cancel')
    action=next(w for w in controls if isinstance(w,ttk.Button) and str(w.cget('text')).split('\\n')[0]=='Record selected row')
    canvas=next(w for w in controls if isinstance(w,tk.Canvas))
    last=next(w for w in controls if isinstance(w,ttk.Button) and w.cget('text')==('Action 11' if options['overflow'] else 'Record selected row'))
    def scroll_last_into_view():
        # Reflow can change the scroll region after a previous scroll request.
        canvas.yview_moveto(1)
        return inside(last,win)
    def accept_selection():
        assert not action.instate(['disabled'])
        action.invoke()
    def inspect_scrolled():
        assert inside(last,win), 'Resized content cannot scroll to its last action'
        assert action.instate(['disabled'])
        tree=next(w for w in controls if isinstance(w,ttk.Treeview))
        tree.selection_set(tree.get_children()[1])
        tree.event_generate('<<TreeviewSelect>>')
        wait_until(lambda: not action.instate(['disabled']), accept_selection, 'selected row to enable its action')
    def inspect_resized():
        assert inside(cancel,win), 'Cancel is clipped after resizing'
        canvas.yview_moveto(1)
        old_bottom=canvas.bbox('all')[3]
        if options['late_layout']:
            # Wrapping can finish after the native window and footer resize.
            # Grow the message after the first scroll, before its next layout.
            message_label=next(w for w in controls if isinstance(w,ttk.Label) and w.cget('text')==args['message'])
            message_label.configure(text=args['message']+' Deferred wrapping.'*200)
        def last_is_visible():
            if options['late_layout'] and canvas.bbox('all')[3] <= old_bottom:
                return False
            return scroll_last_into_view()
        wait_until(last_is_visible, inspect_scrolled, 'resized content to scroll to its last action')
    def resize():
        win.geometry('440x260')
        wait_until(lambda: (win.winfo_width(),win.winfo_height()) == (440,260) and inside(cancel,win), inspect_resized, 'resized window and Cancel control geometry')
    def inspect_focused():
        assert inside(action,win),'Keyboard focus does not reveal the action'
        resize()
    def inspect_overflow():
        assert inside(last,win),'Overflow action cannot be reached by scrolling'
        action.focus_force()
        wait_until(lambda: inside(action,win), inspect_focused, 'keyboard focus to reveal the action')
    def inspect_initial():
        assert inside(cancel,win),'Cancel is clipped at the initial size'
        assert win.winfo_height() <= win.winfo_screenheight()-60
        assert win.winfo_width() <= win.winfo_screenwidth()-40
        if options['overflow']:
            canvas.yview_moveto(1)
            wait_until(scroll_last_into_view, inspect_overflow, 'initial content to scroll to its last action')
        else:
            assert inside(action,win),'Action is clipped at the initial size'
            for label in [w for w in controls if isinstance(w,ttk.Label) and w.cget('text')]:
                assert label.winfo_width() >= label.winfo_reqwidth(), 'Description is clipped horizontally'
                assert label.winfo_height() >= label.winfo_reqheight(), 'Description is clipped vertically'
            resize()
    wait_until(lambda: inside(cancel,win), inspect_initial, 'initial Cancel control geometry')
wait_window = root.wait_window
def wait_for_dialog(win):
    def ready():
        if not win.winfo_viewable():
            root.after(10, ready)
            return
        if options['busy_events']:
            # Keep work arriving while allowing geometry and timers to run.
            # An unbounded zero-delay or idle loop can starve Tk itself.
            def keep_busy():
                root.after(1, keep_busy)
            root.after(1, keep_busy)
        # Older Aqua Tk can crash when a window is destroyed from an idle callback.
        root.after(0, inspect)
    def timed_out():
        errors.append('Timed out waiting for '+phase[0])
        root.destroy()
    root.after_idle(ready)
    root.after(20000, timed_out)
    return wait_window(win)
root.wait_window = wait_for_dialog
try:
    dialog=ActionDialog(root,args)
    assert not errors,errors
    assert dialog.result == {'button':1,'row':[2**60,"O'Brien",None]},dialog.result
finally:
    try:
        root.destroy()
    except tk.TclError:
        pass
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            json.dumps({"overflow": overflow, "busy_events": busy_events, "late_layout": late_layout}),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode == 77 and "TK_UNAVAILABLE:" in completed.stdout:
        pytest.skip(completed.stdout.strip())
    assert completed.returncode == 0, completed.stdout + completed.stderr
