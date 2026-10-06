# Privacy policy (OAuth verification draft)

Younique stores the Google account email used to sign in and the OAuth tokens for connections the user creates.

Tokens and model API keys are encrypted with a per-workspace key. The application does not return token or key material to the browser. Disconnecting a connection revokes the token at Google when the provider supports revocation and deletes the ciphertext.

Gmail message bodies are treated as untrusted data. They are not used to train a Younique model. The user can export or delete their workspace; deleting the workspace key makes the ciphertext unrecoverable.

Contact privacy@younique.dev.
