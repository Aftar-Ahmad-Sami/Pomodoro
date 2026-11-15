# Security policy

## Supported versions

Security fixes go into the latest release. Please update to it before reporting.

## Reporting a vulnerability

Please **don't** report security problems in public issues.

Report them privately through GitHub: go to the [Security tab](https://github.com/Aftar-Ahmad-Sami/Pomodoro/security) and click **Report a vulnerability**. Include what's affected, how to reproduce it, and what an attacker could do with it.

You can expect an acknowledgement within a week. Once a fix is released, the advisory will be published, crediting you unless you'd rather stay anonymous.

## What Pomodoro stores and sends

To help you judge the impact of an issue:

- **Local files**, all in `%LOCALAPPDATA%\Pomodoro`, for the current Windows user only:
  - `state.json`: time bank balance and settings
  - `slack.json`: Slack settings, including the bot token, in plain text. It's created by the user and never stored in the repo
  - `slack_posts.json`: IDs of Slack alerts waiting to be deleted
- **Network:** only when Slack alerts are set up and turned on. Pomodoro calls `https://slack.com/api/` to post its own alerts and delete them later. Nothing else leaves the PC.
- **Registry:** per-user keys under `HKEY_CURRENT_USER` for the notification identity and the uninstall entry. No admin rights are used.

If your Slack token may have leaked, regenerate it in your Slack app under **OAuth & Permissions** and update `slack.json`.
