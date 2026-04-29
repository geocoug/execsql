import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration("execsql.lsp");
  const enabled = config.get<boolean>("enabled", true);

  if (!enabled) {
    return;
  }

  const pythonPath = config.get<string>("pythonPath", "python");

  const serverOptions: ServerOptions = {
    command: pythonPath,
    args: ["-m", "execsql.lsp"],
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "sql" }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.sql"),
    },
  };

  client = new LanguageClient(
    "execsql-lsp",
    "execsql Language Server",
    serverOptions,
    clientOptions
  );

  client.start();
}

export function deactivate(): Thenable<void> | undefined {
  if (client) {
    return client.stop();
  }
  return undefined;
}
