from __future__ import annotations

"""
Database support tiers.

execsql2 ships nine DBMS adapters, but only five of them are exercised
against a live server (or a real database file) on every CI run.  The other
four are carried forward from the upstream monolith and are not verified
anywhere.  Documenting all nine with equal confidence tells users nothing
about which ones have actually been run.

:class:`SupportTier` records that distinction, each adapter declares its own
tier via ``Database.support_tier``, and :func:`announce_tier` emits a single
informational line the first time a session opens a Tier 2 connection.

The notice is written to stderr (never stdout, so it cannot corrupt piped
query output) and can be switched off with ``support_tier_notice=No`` in the
``[interface]`` section of ``execsql.conf``.
"""

import enum

import execsql.state as _state

__all__ = ["SupportTier", "announce_tier"]


class SupportTier(enum.Enum):
    """How thoroughly a DBMS adapter is verified.

    Attributes:
        SUPPORTED: Tested against a live server or real database file on
            every CI run.  Regressions block a release, and bugs are fixed.
        BEST_EFFORT: Inherited from the upstream monolith and not verified
            in CI.  The code is present and may work; nothing proves it
            still does.  Issues and pull requests are welcome, but no
            guarantee is made.
    """

    SUPPORTED = "supported"
    BEST_EFFORT = "best effort"


_NOTICE = (
    "Note: {dbms} support is best-effort — it is not verified in CI and may break. "
    "Set support_tier_notice=No in the [interface] section of execsql.conf to silence this."
)


def announce_tier(tier: SupportTier, dbms_name: str) -> None:
    """Emit the best-effort notice for ``dbms_name``, at most once per session.

    Silent for :attr:`SupportTier.SUPPORTED`, when the user has set
    ``support_tier_notice=No``, and before output hooks are installed (which is
    the case for adapters built by the test suite and by library callers that
    have not started a run).

    Which names have been announced is tracked on the runtime context, so
    :func:`execsql.state.reset` clears it between runs and between tests, and a
    script that opens twenty Firebird connections prints the notice once.

    Args:
        tier: The adapter's declared support tier.
        dbms_name: Human-readable DBMS name used in the message.
    """
    if tier is not SupportTier.BEST_EFFORT:
        return
    conf = _state.conf
    if conf is not None and not getattr(conf, "support_tier_notice", True):
        return
    shown = _state.tier_notices_shown
    if dbms_name in shown:
        return
    shown.add(dbms_name)
    message = _NOTICE.format(dbms=dbms_name)
    if _state.exec_log is not None:
        _state.exec_log.log_status_info(message)
    if _state.output is not None:
        _state.output.write_err(message)
