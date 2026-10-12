// Starts `execsql lsp` for SQL files: lint findings as you type, completion
// and hover.  Plain JavaScript so the extension needs no build step.
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

const INSTALL_HINT =
  'Install it with `uv tool install "execsql2[lsp]"` (or add the lsp extra to an existing install: ' +
  "https://execsql2.readthedocs.io/en/latest/getting-started/installation/), or set execsql.server.path.";

let client;

// Whether *file* is a program this extension may run.
function isProgram(file) {
  try {
    if (!fs.statSync(file).isFile()) {
      return false;
    }
    if (process.platform !== "win32") {
      fs.accessSync(file, fs.constants.X_OK);
    }
    return true;
  } catch {
    return false;
  }
}

// *name* looked up in PATH only, never in the working directory: on Windows a
// bare command name is otherwise looked up in the child's working directory
// (the workspace folder) first, so a repository could ship its own execsql.exe.
// Relative PATH entries are skipped for the same reason.  Only .exe and .com
// are tried on Windows: Node cannot start a .cmd or .bat without a shell.
function findOnPath(name) {
  const suffixes = process.platform === "win32" ? [".exe", ".com"] : [""];
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    if (!dir || !path.isAbsolute(dir)) {
      continue;
    }
    for (const suffix of suffixes) {
      const candidate = path.join(dir, name + suffix);
      if (isProgram(candidate)) {
        return candidate;
      }
    }
  }
  return undefined;
}

// The absolute path of the program to run as `<program> lsp`, or an Error saying
// why there is none.  execsql.server.path is a command name looked up in PATH
// (the default, `execsql`) or an absolute path, with a leading ~ expanded; a
// relative path is refused, as it would be resolved inside the workspace.  In a
// workspace that is not trusted, VS Code ignores the workspace's own value of
// this setting (restrictedConfigurations in package.json).
function serverProgram() {
  let configured = (vscode.workspace.getConfiguration("execsql").get("server.path") || "").trim() || "execsql";
  if (configured === "~" || configured.startsWith("~/") || configured.startsWith("~\\")) {
    configured = path.join(os.homedir(), configured.slice(1));
  }
  if (!configured.includes("/") && !configured.includes("\\")) {
    return findOnPath(configured) || new Error(`${configured} was not found on PATH.`);
  }
  if (!path.isAbsolute(configured)) {
    return new Error(`execsql.server.path must be a command name or an absolute path, not ${configured}.`);
  }
  return isProgram(configured) ? configured : new Error(`${configured} is not a program.`);
}

async function start() {
  const program = serverProgram();
  if (program instanceof Error) {
    vscode.window.showWarningMessage(`The execsql language server did not start: ${program.message} ${INSTALL_HINT}`);
    return;
  }
  client = new LanguageClient(
    "execsql",
    "execsql",
    // The server runs from the home directory, not the workspace folder: it
    // finds the workspace through the protocol, not its working directory.
    { command: program, args: ["lsp"], transport: TransportKind.stdio, options: { cwd: os.homedir() } },
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
      `The execsql language server did not start (${program} lsp): ${err.message}. ${INSTALL_HINT}`,
    );
  }
}

async function activate(context) {
  if (!vscode.workspace.getConfiguration("execsql").get("server.enabled", true)) {
    return;
  }
  context.subscriptions.push(
    vscode.commands.registerCommand("execsql.restartServer", async () => {
      if (!vscode.workspace.isTrusted) {
        vscode.window.showInformationMessage(
          "The execsql language server starts once you trust this workspace.",
        );
        return;
      }
      if (client) {
        await client.stop();
        client = undefined;
      }
      await start();
    }),
  );
  // The server reads the scripts, the files they INCLUDE and the execsql.conf files the
  // workspace names, so it starts only in a trusted workspace; syntax
  // highlighting works either way.
  if (vscode.workspace.isTrusted) {
    await start();
  } else {
    context.subscriptions.push(vscode.workspace.onDidGrantWorkspaceTrust(() => start()));
  }
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
