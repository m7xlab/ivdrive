---
sidebar_position: 3
title: Create an account
---

# Create an account

## Hosted beta (ivdrive.eu)

Registration is **invite-only** while the service is in beta.

### Request an invite

1. Go to [ivdrive.eu/register](https://ivdrive.eu/register)
2. Submit your email
3. Wait for the approval email (invite link)

### Register

1. Open the invite link
2. Fill in:
   - Display name
   - Email
   - Password (use a strong, unique password)
3. Confirm your email if asked
4. Sign in at [ivdrive.eu/login](https://ivdrive.eu/login)

### Two-factor authentication (2FA)

We strongly recommend 2FA:

1. Open **Settings → Security**
2. Scan the QR code with an authenticator app (e.g. Aegis, 1Password, Google Authenticator)
3. Store the **recovery codes** offline

If you lose your device, recovery codes restore access.

## Password reset

1. On the login page, choose **Forgot password**
2. Enter your email
3. Open the reset link and choose a new password

## Self-hosted accounts

On a self-hosted install:

1. Set `SERVICE_REGISTRATION` in `.env` (`open` or invite-only depending on version)
2. Register via the UI
3. Promote your first user to admin (see [Docker Compose](../self-hosting/docker-compose.md))

## Account tips

- One account can manage **multiple vehicles**
- Sign out from the sidebar when using a shared machine
- Session cookies are `HttpOnly`; you can revoke sessions by signing out
