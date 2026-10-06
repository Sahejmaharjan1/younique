# OAuth scopes

| Connector | Scope | Class | Why |
| --- | --- | --- | --- |
| Gmail send | `https://www.googleapis.com/auth/gmail.send` | Restricted | Send mail the user approved. No mailbox read. |
| Gmail read | `https://www.googleapis.com/auth/gmail.readonly` | Restricted | Read messages the user granted. Content is untrusted. |
| Drive | `https://www.googleapis.com/auth/drive.file` | Non-restricted | Only files the app created or the user picked. |
| Sheets | `https://www.googleapis.com/auth/spreadsheets` | Sensitive | Read and write spreadsheets the user selected. |

A send-only Gmail connection does not receive the read scope, and the read tool is not registered for that connection.

The hosted app stays in testing mode until verification completes. Self-hosters paste their own client id and secret per workspace.
