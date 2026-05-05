# Lifeguard Production Deploy Runbook

## Purpose

This document records the May 2026 production deploy incident and the final known-good recovery path. Use it when the GitHub Actions deploy workflow fails, when production SSH access changes, or when the VM needs to be reconnected to the repository's deployment pipeline.

## Production Environment Facts

- Hosting: Google Cloud VM (`e2-micro`)
- Public IP: `34.71.241.84`
- SSH port: `22`
- SSH user: `kuuryu_taikaichi`
- Repository path on VM: `/home/kuuryu_taikaichi/Lifeguard`
- Production service: `lifeguard.service`
- OS observed during recovery: Debian 12

## Deployment Workflow Facts

- Workflow file: `.github/workflows/deploy.yml`
- Trigger: push to `main`
- SSH action: `appleboy/ssh-action@v1.0.3`
- Remote deploy flow:
  - `cd ~/Lifeguard`
  - `git pull origin main`
  - `./venv/bin/pip install -r requirements.txt`
  - `sudo -n systemctl restart lifeguard`
  - `systemctl status lifeguard --no-pager --lines=20`

## Incident Summary

The initial report was that live deploy did not run on merge. That was false. The deploy workflow had run and failed.

The recovery required working through three separate failure classes:

1. CI had unrelated Ruff failures that needed to be cleaned up so `main` was in a healthy state.
2. Production connectivity secrets were stale, so the workflow initially could not reach the correct SSH endpoint.
3. After SSH connectivity was fixed, the workflow still failed first on SSH key compatibility and then on non-interactive sudo for the service restart.

The final blocking issue was `sudo systemctl restart lifeguard` requiring a password in a non-interactive GitHub Actions SSH session.

## Root Causes

### 1. Stale GitHub Actions Deploy Configuration

The repository secrets did not reflect the active production VM and user, which caused the workflow to fail before any remote commands could run.

Required secrets:

- `SERVER_HOST = 34.71.241.84`
- `SERVER_USER = kuuryu_taikaichi`
- `SSH_PRIVATE_KEY =` RSA PEM private key matching the VM's installed deploy public key

### 2. SSH Key Compatibility With `appleboy/ssh-action`

An Ed25519/OpenSSH key path was tested first and could be accepted manually on the VM, but the GitHub Actions SSH action still failed authentication in this environment.

The working fallback was an RSA key generated in PEM format.

Known working local key:

- Private key path: `C:\Users\dwigh\.ssh\lifeguard_github_actions_rsa`
- Fingerprint: `SHA256:WNmw7ZISxVSydvN5UUkFVz5ImoRsRAU0H8ZsK9EFrPI`

Ed25519 key attempted during recovery:

- Private key path: `C:\Users\dwigh\.ssh\lifeguard_github_deploy`
- Fingerprint: `SHA256:WRtk3EGaSwEXjAhzoCTeDdqxs9+FoDeIU98qsLZ33fo`

### 3. Non-Interactive Sudo Requirement

Once the workflow was able to SSH and run the remote script, deployment still failed here:

```text
sudo: a terminal is required to read the password; either use the -S option to read from standard input or configure an askpass helper
sudo: a password is required
```

That is the decisive signal that the deploy user lacks passwordless sudo for restarting `lifeguard.service`.

## Known-Good Configuration

Production deploy is considered correctly wired when all of the following are true:

- GitHub Actions uses the current production host `34.71.241.84`
- GitHub Actions uses the current production user `kuuryu_taikaichi`
- The `SSH_PRIVATE_KEY` secret contains the RSA PEM deploy private key
- The VM `authorized_keys` file contains the matching RSA public key
- `/etc/sudoers.d/lifeguard-deploy` grants `NOPASSWD` for `/usr/bin/systemctl restart lifeguard`
- `lifeguard.service` is still the correct production systemd unit name

## Required VM Fix For Non-Interactive Deploys

The restart command must be allowed without a password.

Confirmed systemctl path:

- `/usr/bin/systemctl`

Required sudoers rule:

```text
kuuryu_taikaichi ALL=(root) NOPASSWD: /usr/bin/systemctl restart lifeguard
```

Safe setup sequence:

```bash
printf 'kuuryu_taikaichi ALL=(root) NOPASSWD: /usr/bin/systemctl restart lifeguard\n' | sudo tee /etc/sudoers.d/lifeguard-deploy > /dev/null
sudo chmod 440 /etc/sudoers.d/lifeguard-deploy
sudo visudo -cf /etc/sudoers.d/lifeguard-deploy
sudo -n systemctl restart lifeguard
```

If the final command succeeds without prompting, the deploy workflow can restart the service non-interactively.

## Useful Verification Commands

### Check Workflow State

```bash
gh api repos/Skigim/Lifeguard/actions/runs/<run_id> --jq ".status, .conclusion, .run_attempt"
```

### Check Workflow Job Steps

```bash
gh api repos/Skigim/Lifeguard/actions/runs/<run_id>/jobs --jq ".jobs[] | {id: .id, run_attempt: .run_attempt, status: .status, conclusion: .conclusion, steps: [.steps[]? | {name: .name, conclusion: .conclusion}]}"
```

### Fetch Failed Logs

```bash
gh run view <run_id> --log-failed -R Skigim/Lifeguard
```

### Verify Non-Interactive Restart Over SSH

```bash
ssh -i C:\Users\dwigh\.ssh\lifeguard_github_actions_rsa -o BatchMode=yes kuuryu_taikaichi@34.71.241.84 "sudo -n systemctl restart lifeguard"
```

### Check Service Status Without Sudo

```bash
ssh -i C:\Users\dwigh\.ssh\lifeguard_github_actions_rsa -o BatchMode=yes kuuryu_taikaichi@34.71.241.84 "systemctl status lifeguard --no-pager --lines=20"
```

## Workflow Hardening Added During Recovery

The deploy workflow was narrowed and made more diagnosable:

- Added a preflight SSH reachability check using a Python socket connection to `${{ secrets.SERVER_HOST }}:22`
- Added `script_stop: true` so the SSH action stops on the first remote failure
- Changed the restart block so lack of passwordless sudo fails with an explicit error message
- Limited sudo usage to the actual restart command; service status is read without sudo

## Practical Lessons Learned

- If deploy appears not to have run, verify the workflow run history before changing triggers.
- `gh` CLI was more reliable than cached UI impressions during reruns.
- Browser-managed SSH access on GCP can expire and should not be treated as durable deploy access.
- Copying SSH public keys through browser terminals can corrupt `authorized_keys`; base64 transfer is safer.
- On Windows, `cmd /c ... < file` was more reliable than PowerShell piping for `gh secret set` with a private key.
- Assume every privileged action inside GitHub Actions must be non-interactive.

## If Deploy Breaks Again

1. Confirm whether the workflow ran at all.
2. Check whether the SSH reachability step passed.
3. If SSH authentication fails, validate the RSA PEM deploy key secret and the matching `authorized_keys` entry.
4. If the remote script starts but restart fails, run `sudo -n systemctl restart lifeguard` over SSH manually.
5. If `git pull` or `pip install` fail, the issue is now inside the remote repository or runtime rather than in network or authentication.

## Related History

- CI cleanup commit from the same incident: `c63c912075e64538f8a307fdfd420d0d17b99c74`
- Deploy diagnostic and hardening commit: `fc5a239147ce7385aef07e9a4099df8ec9bcd98f`

The corresponding detailed working memory for this incident lives in repo memory at `/memories/repo/production_deploy_debugging_2026-05-05.md`.