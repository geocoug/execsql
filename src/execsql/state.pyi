from __future__ import annotations

import re
import threading
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from execsql.config import ConfigData, StatObj
from execsql.db.base import DatabasePool
from execsql.exporters.base import ExportMetadata, WriteSpec
from execsql.script import CounterVars, MetaCommandList, ScriptExecSpec, SubVarSet
from execsql.utils.fileio import FileWriter, Logger, TempFileMgr
from execsql.utils.mail import MailSpec
from execsql.utils.timer import Timer

@dataclass
class ExecFrame:
    kind: str
    label: str = ...
    source: str = ...
    line: int | None = ...
    iteration: int = ...
    params: dict[str, str] | None = ...
    localvars: Any = ...
    paramvals: Any = ...
    paramnames: list[str] | None = ...
    scope_ref: ExecFrame | None = ...

varlike: re.Pattern[str]
endloop_rx: re.Pattern[str]
loop_rx: re.Pattern[str]
defer_rx: re.Pattern[str]
stringtypes: type[str]
primary_vno: int
secondary_vno: int
tertiary_vno: int

conf: ConfigData
logfile_encoding: str
last_command: Any
upass: str | None
err_halt_writespec: WriteSpec | None
err_halt_email: MailSpec | None
err_halt_exec: ScriptExecSpec | None
cancel_halt_writespec: WriteSpec | None
cancel_halt_mailspec: MailSpec | None
cancel_halt_exec: ScriptExecSpec | None
cmds_run: int
exec_log: Logger
subvars: SubVarSet
status: StatObj
output: Any
filewriter: FileWriter
counters: CounterVars
timer: Timer
dbs: DatabasePool
tempfiles: TempFileMgr
export_metadata: ExportMetadata
metacommandlist: MetaCommandList
conditionallist: MetaCommandList
gui_console: Any
gui_manager_queue: Any
gui_manager_thread: threading.Thread | None
profile_data: list[tuple[Any, ...]] | None
step_mode: bool
ast_scripts: dict[str, Any]
include_chain: list[str]
ast_exec_stack: list[ExecFrame]

class RuntimeContext:
    conf: ConfigData | None
    logfile_encoding: str
    last_command: Any
    upass: str | None
    err_halt_writespec: WriteSpec | None
    err_halt_email: MailSpec | None
    err_halt_exec: ScriptExecSpec | None
    cancel_halt_writespec: WriteSpec | None
    cancel_halt_mailspec: MailSpec | None
    cancel_halt_exec: ScriptExecSpec | None
    cmds_run: int
    exec_log: Logger | None
    subvars: SubVarSet | None
    status: StatObj | None
    output: Any
    filewriter: FileWriter | None
    counters: CounterVars | None
    timer: Timer | None
    dbs: DatabasePool | None
    tempfiles: TempFileMgr | None
    export_metadata: ExportMetadata | None
    metacommandlist: MetaCommandList | None
    conditionallist: MetaCommandList | None
    gui_console: Any
    gui_manager_queue: Any
    gui_manager_thread: threading.Thread | None
    profile_data: list[tuple[Any, ...]] | None
    step_mode: bool
    ast_scripts: dict[str, Any]
    include_chain: list[str]
    ast_exec_stack: list[ExecFrame]
    def __init__(self) -> None: ...
    def current_scope(self) -> ExecFrame | None: ...
    def current_localvars(self) -> Any: ...
    def current_paramvals(self) -> Any: ...
    def outer_script_scopes(self) -> list[ExecFrame]: ...

def xcmd_test(teststr: str) -> bool: ...
def current_scope() -> ExecFrame | None: ...
def current_localvars() -> Any: ...
def current_paramvals() -> Any: ...
def outer_script_scopes() -> list[ExecFrame]: ...
def get_context() -> RuntimeContext: ...
def set_context(ctx: RuntimeContext) -> None: ...
def reset() -> None: ...
def initialize(config: ConfigData, dispatch_table: object, conditional_table: object) -> None: ...

class active_context(AbstractContextManager[RuntimeContext]):
    def __init__(self, ctx: RuntimeContext) -> None: ...
    def __enter__(self) -> RuntimeContext: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
