import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {
    console.log('Congratulations, your extension "advanced-code-intelligence" is now active!');

    const getServerUrl = () => {
        const cfg = vscode.workspace.getConfiguration();
        return cfg.get<string>('codeCouncil.serverUrl', 'http://localhost:8000');
    }

    // Register Chat Participant
    const chatParticipant = vscode.chat.createChatParticipant('code-council', async (request, context, stream, token) => {
        stream.markdown('Checking with the **Council of Judges**...');
        
        try {
            // Call the Python backend
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

            const data = await response.json();
            
            stream.markdown('\n\n**Retrieval Results:**\n');
            for (const result of data.results) {
                const fp = result.metadata?.filepath ? ` (${result.metadata.filepath})` : '';
                stream.markdown(`- ${result.source}${fp} (Score: ${result.score})\n`);
            }

            stream.markdown('\n**Council Validation:**\n');
            stream.markdown(`- Approved: ${data.validation.approved}\n`);
            
        } catch (error) {
            stream.markdown(`\n\nError communicating with Code Intelligence backend: ${error}`);
        }
        
        return { metadata: { command: '' } };
    });

    context.subscriptions.push(chatParticipant);

    // Register Index Command
    let disposable = vscode.commands.registerCommand('code-intelligence.index', async () => {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders || folders.length === 0) {
            vscode.window.showErrorMessage('Code Intelligence: No workspace folder open.');
            return;
        }
        const root = folders[0].uri.fsPath;
        vscode.window.showInformationMessage('Code Council: Indexing workspace...');
        try {
            const response = await fetch(`${getServerUrl()}/index`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: root })
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.error || response.statusText);
            }
            vscode.window.showInformationMessage(`Code Council: Index complete (${data.parsed_files} files).`);
        } catch (err: any) {
            vscode.window.showErrorMessage(`Code Council: Indexing failed: ${err?.message ?? err}`);
        }
    });

    context.subscriptions.push(disposable);
}

export function deactivate() {}
