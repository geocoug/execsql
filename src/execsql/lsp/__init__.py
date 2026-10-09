"""Language server for execsql scripts: ``execsql lsp``.

Editors start it over stdio. The features are plain functions over a
document's text, so they are tested without a client; :mod:`.server` wires
them to the protocol with pygls (the ``lsp`` extra).
"""
