# Google OAuth verification packet

This packet is the Phase 0 start of Google OAuth verification and the CASA engagement. Hosted Gmail cannot ship until Google assigns a case number and the annual assessment is underway. SMTP and bring-your-own OAuth clients do not wait on that queue.

## What to file

1. Google Cloud project for the hosted OAuth client, with the app name **Younique**.
2. Scopes in [scopes.md](scopes.md). Do not request `https://mail.google.com/`.
3. Privacy policy at the URL in [privacy-policy.md](privacy-policy.md), published before submission.
4. Homepage and a demo video of the Gmail send and read flows, including the approval card.
5. Brand verification, then sensitive/restricted scope verification in the Google Auth Platform console.

## CASA

Restricted Gmail scopes require an annual CASA assessment. Contact a Google-authorized lab using [casa-engagement.md](casa-engagement.md) on the same day the verification form is submitted. The elapsed time is external and should start on day one.

## Status

| Item | State |
| --- | --- |
| Packet | Ready in this directory |
| Google case number | Pending the project owner's Cloud console submission |
| CASA assessor | Pending the engagement email |

Do not invent a case number. Record it in [submission-status.md](submission-status.md) when the console shows it.
