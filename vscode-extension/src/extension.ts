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
            // VS Code API change: stream.progress might not be available or used differently.
            // Using placeholder text for now.
            stream.markdown("Thinking...\n\n");

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
            
            // Clear "Thinking..." if we could, but streaming appends.

            stream.markdown(data.answer);

            if (data.citations && data.citations.length > 0) {
                stream.markdown('\n\n**Sources:**\n');
                for (const cit of data.citations) {
                    // Create a clickable link
                    // VS Code assumes paths are relative or proper URIs.
                    // We can try to use markdown link syntax with file://
                    const uri = vscode.Uri.file(cit.filepath);
                    // Add line number: #L10
                    // Note: VS Code sometimes struggles with local file links in markdown if not trusted.
                    // We'll format it as `File (lines)` text for now, or Command link.

                    stream.markdown(`- [${cit.filepath}:${cit.start_line}-${cit.end_line}](command:vscode.open?${encodeURIComponent(JSON.stringify(uri))})\n`);

                    // A better way is referencing the file directly if the chat API supports it
                    // For now, simple text:
                    // stream.markdown(`- \`${cit.filepath}\` lines ${cit.start_line}-${cit.end_line}\n`);
                }
            }
            
        } catch (error) {
            stream.markdown(`\n\nError communicating with backend: ${error}`);
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
