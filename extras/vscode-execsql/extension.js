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
  "https://execsql2.readthedocs.io/en/stable/getting-started/installation/), or set execsql.server.path.";

let client;
// The server's log, its protocol trace (execsql.trace.server) and why it did not start, in one place:
// View > Output > execsql.
let output;

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

// Shows *message* as a warning and keeps it in the Output channel, where the server's log is.
function warn(message) {
  output.appendLine(`[extension] ${message}`);
  vscode.window.showWarningMessage(message);
}

async function start() {
  const program = serverProgram();
  if (program instanceof Error) {
    warn(`The execsql language server did not start: ${program.message} ${INSTALL_HINT}`);
    return;
  }
  // An environment variable, not --log-level, so an older execsql without the option still starts.
  const logLevel = vscode.workspace.getConfiguration("execsql").get("server.logLevel", "info");
  output.appendLine(`[extension] starting ${program} lsp (log level ${logLevel})`);
  client = new LanguageClient(
    "execsql",
    "execsql",
    // The server runs from the home directory, not the workspace folder: it
    // finds the workspace through the protocol, not its working directory.
    {
      command: program,
      args: ["lsp"],
      transport: TransportKind.stdio,
      options: { cwd: os.homedir(), env: { ...process.env, EXECSQL_LSP_LOG_LEVEL: logLevel } },
    },
    {
      documentSelector: [
        { scheme: "file", language: "sql" },
        { scheme: "untitled", language: "sql" },
      ],
      outputChannel: output,
    },
  );
  try {
    await client.start();
  } catch (err) {
    client = undefined;
    warn(`The execsql language server did not start (${program} lsp): ${err.message}. ${INSTALL_HINT}`);
  }
}

function serverEnabled() {
  return vscode.workspace.getConfiguration("execsql").get("server.enabled", true);
}

async function stop() {
  if (client) {
    const running = client;
    client = undefined;
    await running.stop();
  }
}

// Brings the server to the state the settings and workspace trust call for,
// one change at a time: a second request waits for the first, so two quick
// restarts cannot leave an orphaned server process.
let pending = Promise.resolve();
function update(restart) {
  pending = pending
    .then(async () => {
      if (restart) {
        await stop();
      }
      // The server reads the scripts, the files they INCLUDE and the
      // execsql.conf files the workspace names, so it runs only in a trusted
      // workspace; syntax highlighting works either way.
      if (!serverEnabled() || !vscode.workspace.isTrusted) {
        await stop();
      } else if (!client) {
        await start();
      }
    })
    .catch((err) => warn(`execsql language server: ${err.message}`));
  return pending;
}

async function activate(context) {
  output = vscode.window.createOutputChannel("execsql");
  context.subscriptions.push(
    output,
    vscode.commands.registerCommand("execsql.restartServer", async () => {
      if (!serverEnabled()) {
        vscode.window.showInformationMessage("The execsql language server is turned off (execsql.server.enabled).");
        return;
      }
      if (!vscode.workspace.isTrusted) {
        vscode.window.showInformationMessage("The execsql language server starts once you trust this workspace.");
        return;
      }
      await update(true);
    }),
    // The execsql.server.* settings take effect without reloading the window.
    vscode.workspace.onDidChangeConfiguration((event) => {
      return event.affectsConfiguration("execsql.server") ? update(true) : undefined;
    }),
    vscode.workspace.onDidGrantWorkspaceTrust(() => update(false)),
  );
  await update(false);
}

function deactivate() {
  return stop();
}

module.exports = { activate, deactivate };
