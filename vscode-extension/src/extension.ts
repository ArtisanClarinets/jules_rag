import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {
    console.log('Code Intelligence Extension Active');

    const getServerUrl = () => {
        const cfg = vscode.workspace.getConfiguration('codeCouncil');
        return cfg.get<string>('serverUrl', 'http://localhost:8000');
    }

    // Register Chat Participant
    const chatParticipant = vscode.chat.createChatParticipant('code-council', async (request, context, stream, token) => {
        
        try {
            // stream.progress('Thinking...');
            // In newer API, we assume stream handles markdown updates.

            const response = await fetch(`${getServerUrl()}/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query: request.prompt })
            });

            if (!response.ok) {
                throw new Error(`API Error: ${response.statusText}`);
            }

            const data: any = await response.json();
            
            stream.markdown(data.answer);

            if (data.citations && data.citations.length > 0) {
                stream.markdown('\n\n---\n**Sources:**\n');
                for (const cit of data.citations) {
                    // Create a clickable link
                    // Construct URI relative to workspace if possible, or absolute.
                    // Assuming cit.filepath is relative to root as per indexing logic (rel_path)
                    // We need to resolve it to absolute path for VS Code to open it reliably if it's not just a name.
                    // But backend sends what it has.

                    // Note: command:vscode.open expects a URI.
                    // We try to find the file in workspace to get a proper URI.

                    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
                    let uri: vscode.Uri;

                    if (workspaceFolder) {
                         uri = vscode.Uri.joinPath(workspaceFolder.uri, cit.filepath);
                    } else {
                         uri = vscode.Uri.file(cit.filepath);
                    }

                    // Range for selection
                    const selection = new vscode.Range(cit.start_line, 0, cit.end_line, 0);
                    // We can't easily pass selection in vscode.open arguments via markdown link command URI without encoding it complexly.
                    // Standard vscode.open takes a URI.
                    // A trick is to use `vscode.open` with fragment, but line numbers in fragments aren't standard in VS Code URIs unless handled.
                    // Better: define a custom command in package.json/extension.ts that opens a file at a range, but let's stick to simple open for now.

                    stream.markdown(`- [${cit.filepath} (Lines ${cit.start_line}-${cit.end_line})](command:vscode.open?${encodeURIComponent(JSON.stringify(uri))})\n`);
                }
            }
            
        } catch (error) {
            stream.markdown(`\n\n**Error communicating with backend:**\n${error}\n\nPlease ensure the Code Intelligence server is running.`);
        }
        
        return { metadata: { command: '' } };
    });

    context.subscriptions.push(chatParticipant);

    // Register Index Command
    let disposable = vscode.commands.registerCommand('code-intelligence.index', async () => {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders || folders.length === 0) {
            vscode.window.showErrorMessage('No workspace folder open.');
            return;
        }
        const root = folders[0].uri.fsPath;

        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "Code Intelligence: Indexing...",
            cancellable: false
        }, async (progress) => {
            try {
                const response = await fetch(`${getServerUrl()}/index`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: root, force: true }) // Force reindex on manual command
                });

                if (!response.ok) {
                    throw new Error(response.statusText);
                }

                const data: any = await response.json();
                vscode.window.showInformationMessage(`Indexing started for ${data.path}`);
            } catch (err: any) {
                vscode.window.showErrorMessage(`Indexing failed: ${err?.message ?? err}`);
            }
        });
    });

    context.subscriptions.push(disposable);
}

export function deactivate() {}
