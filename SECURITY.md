# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private
"Report a vulnerability" button on the repository's **Security** tab instead. You will get a reply
within a week. Please include steps to reproduce and what an attacker could do.

## Design rules this project keeps

- No secrets in the repository, the browser, prompts, logs or reports. Secrets live in your cloud
  secret store (Azure Key Vault in the reference deployment) and reach the app as references.
- One owner. Only the configured owner can sign in, approve posts or change policies; the agent can
  request actions but never approve them.
- Instagram tokens are encrypted at rest; images and videos are given to Instagram through signed
  links that expire after an hour.
- Nothing is published outside production, and nothing is published without an owner approval.
- Every push is scanned for secrets (gitleaks) and tested before it can deploy.

## If you run your own copy

You are responsible for your deployment: keep your secrets in a secret store, restrict sign-in to
yourself, and rotate any secret you ever pasted somewhere it could be seen.
