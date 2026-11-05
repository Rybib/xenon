#!/bin/bash
# One-time setup of Xenon's update system. Run this ON YOUR OWN COMPUTER
# (not in CI), from anywhere, with the GitHub CLI logged in as the repo
# owner (`gh auth login`). It:
#
#   1. creates the update signing key (an ed25519 GPG key, no passphrase,
#      because GitHub Actions signs unattended),
#   2. stores the private key as the repository secret XENON_REPO_KEY,
#   3. turns on GitHub Pages (source: GitHub Actions) to host the updates,
#   4. saves a backup of the private key next to this script's working
#      directory for you to keep somewhere safe (password manager), then
#      removes the key from this computer's GPG keyring.
#
# Needs: gpg, gh.   Usage: tools/setup-updates.sh [owner/repo]
set -euo pipefail

REPO="${1:-Rybib/xenon}"
command -v gpg >/dev/null || { echo "Install GnuPG first (e.g. brew install gnupg)."; exit 1; }
command -v gh >/dev/null || { echo "Install the GitHub CLI first (e.g. brew install gh)."; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Run 'gh auth login' first."; exit 1; }

if gh secret list --repo "$REPO" 2>/dev/null | grep -q '^XENON_REPO_KEY'; then
    echo "XENON_REPO_KEY already exists in $REPO. Replacing it would lock out"
    echo "every installed Xenon from updates. Stopping without changes."
    exit 1
fi

# Short path: macOS temp folders are too long for gpg-agent's socket.
GNUPGHOME="$(mktemp -d /tmp/xenon-gpg.XXXXXX)"
export GNUPGHOME
trap 'gpgconf --kill gpg-agent 2>/dev/null; rm -rf "$GNUPGHOME"' EXIT

echo "==> Creating the Xenon update signing key"
gpg --batch --passphrase '' --quick-gen-key \
    "Xenon Archive Signing Key <Rybib@users.noreply.github.com>" ed25519 sign never
FPR="$(gpg --list-keys --with-colons | awk -F: '/^fpr/{print $10; exit}')"

BACKUP="xenon-update-key-PRIVATE-$FPR.asc"
gpg --armor --export-secret-keys "$FPR" > "$BACKUP"
chmod 600 "$BACKUP"

echo "==> Storing it as the GitHub secret XENON_REPO_KEY"
gh secret set XENON_REPO_KEY --repo "$REPO" < "$BACKUP"

echo "==> Turning on GitHub Pages (deployed by GitHub Actions)"
if ! gh api -X POST "repos/$REPO/pages" -f build_type=workflow >/dev/null 2>&1; then
    gh api -X PUT "repos/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
        || echo "    Could not switch Pages on automatically: in GitHub open
    Settings > Pages and set Source to 'GitHub Actions'."
fi

echo
echo "Done. Key fingerprint: $FPR"
echo "A backup of the private key is in ./$BACKUP"
echo "Keep it somewhere safe (a password manager) and delete it from here."
echo "Anyone with this key could publish updates to every Xenon computer."
echo
echo "The next push to main builds a signed update repository at"
echo "https://$(echo "${REPO%%/*}" | tr '[:upper:]' '[:lower:]').github.io/${REPO#*/}/apt"
