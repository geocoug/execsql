"""execsql's commands, one module each.

Importing this package registers every command on
:data:`execsql.cli.application.app`. The import order is the order
``execsql --help`` lists them in.
"""

from execsql.cli.commands import run  # noqa: F401
from execsql.cli.commands import format  # noqa: F401, A004
from execsql.cli.commands import lint  # noqa: F401
