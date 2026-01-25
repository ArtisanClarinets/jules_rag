import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {
    console.log('Code Intelligence Extension Active');

    const getServerUrl = () => {
        const cfg = vscode.workspace.getConfiguration('codeCouncil');
        return cfg.get<string>('serverUrl', 'http://localhost:8000');
    }

    const getApiToken = () => {
        const cfg = vscode.workspace.getConfiguration('codeCouncil');
        return cfg.get<string>('apiToken', '');
    }

    const getHeaders = () => {
        const headers: any = { 'Content-Type': 'application/json' };
        const token = getApiToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    }

    // Register Chat Participant
    const chatParticipant = vscode.chat.createChatParticipant('code-council', async (request, context, stream, token) => {
        
        try {
            // stream.progress('Thinking...');
            // In newer API, we assume stream handles markdown updates.

            const response = await fetch(`${getServerUrl()}/query`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({ query: request.prompt })
            });

            if (!response.ok) {
                throw new Error(`API Error: ${response.status} ${response.statusText}`);
            }

            const data: any = await response.json();
            
            stream.markdown(data.answer);

            if (data.citations && data.citations.length > 0) {
                stream.markdown('\n\n---\n**Sources:**\n');
                for (const cit of data.citations) {
                    // Create a clickable link
                    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
                    let uri: vscode.Uri;

                    if (workspaceFolder) {
                        // cit.filepath is now relative, so joinPath works correctly
                        uri = vscode.Uri.joinPath(workspaceFolder.uri, cit.filepath);
                    } else {
                        // Fallback if no workspace (unlikely in this context)
                        uri = vscode.Uri.file(cit.filepath);
                    }

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
                    headers: getHeaders(),
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
