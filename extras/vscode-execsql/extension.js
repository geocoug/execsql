// Starts `execsql lsp` for SQL files: lint findings as you type, completion
// and hover.  Plain JavaScript so the extension needs no build step.
"use strict";

const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function serverCommand() {
  const configured = vscode.workspace.getConfiguration("execsql").get("server.path");
  return configured && configured.trim() ? configured.trim() : "execsql";
}

async function start() {
  const command = serverCommand();
  client = new LanguageClient(
    "execsql",
    "execsql",
    { command, args: ["lsp"], transport: TransportKind.stdio },
    {
      documentSelector: [
        { scheme: "file", language: "sql" },
        { scheme: "untitled", language: "sql" },
      ],
    },
  );
  try {
    await client.start();
  } catch (err) {
    client = undefined;
    vscode.window.showWarningMessage(
      `The execsql language server did not start (${command} lsp): ${err.message}. ` +
        'Install it with: uv tool install "execsql2[lsp]", or set execsql.server.path.',
    );
  }
}

async function activate(context) {
  if (!vscode.workspace.getConfiguration("execsql").get("server.enabled", true)) {
    return;
  }
  context.subscriptions.push(
    vscode.commands.registerCommand("execsql.restartServer", async () => {
      if (client) {
        await client.stop();
      }
      await start();
    }),
  );
  await start();
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
