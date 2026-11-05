#!/bin/bash
# shellcheck disable=SC2015  # "cond && pass || fail": pass() always succeeds
# End-to-end test of Xenon's update system on a Debian/Ubuntu machine
# (CI runs it in a throwaway debian:trixie container; it installs and
# removes packages, so don't run it on a computer you care about).
#
#  1. create a throwaway signing key
#  2. build packages as version +t1, publish a signed repository, serve it
#  3. install xenon-archive-keyring and xenon-branding from it
#  4. build +t2, republish, run unattended-upgrades (what installed Xenon
#     systems run daily) and check it upgraded to +t2 by itself
#  5. tamper with the repository and check APT refuses it
#
# Needs root, plus: debhelper dh-python python3-pytest librsvg2-bin gnupg
# apt-utils xz-utils unattended-upgrades curl.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
PORT=8765
export GNUPGHOME="$WORK/gnupg"
mkdir -m 700 "$GNUPGHOME"
SERVER=""
# shellcheck disable=SC2317  # called via trap
cleanup() {
    local rc=$?
    [ -n "$SERVER" ] && kill "$SERVER" 2>/dev/null
    apt-get purge -y -qq xenon-branding xenon-archive-keyring >/dev/null 2>&1 || true
    rm -f /etc/apt/sources.list.d/xenon.sources
    exit "$rc"
}
trap cleanup EXIT
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; exit 1; }

echo "== throwaway signing key"
gpg --batch --quiet --passphrase '' --quick-gen-key \
    "Xenon Test Key <test@example.invalid>" ed25519 sign never
FPR="$(gpg --list-keys --with-colons | awk -F: '/^fpr/{print $10; exit}')"
XENON_REPO_KEY="$(gpg --armor --export-secret-keys "$FPR")"
export XENON_REPO_KEY XENON_SKIP_THIRDPARTY=1

publish() { # version suffix
    XENON_VERSION_SUFFIX="$1" "$ROOT/tools/build-packages.sh" "$WORK/debs$1" >"$WORK/build$1.log" 2>&1 \
        || { tail -30 "$WORK/build$1.log"; fail "package build $1"; }
    rm -rf "$WORK/site"
    "$ROOT/tools/build-apt-repo.sh" "$WORK/debs$1" "$WORK/site" "$FPR" >/dev/null
}

echo "== version +t1"
publish +t1
(cd "$WORK/site" && exec python3 -m http.server "$PORT" --bind 127.0.0.1) >/dev/null 2>&1 &
SERVER=$!
sleep 1

dpkg -i "$WORK"/debs+t1/xenon-archive-keyring_*.deb >/dev/null
[ -f /usr/share/keyrings/xenon-archive-keyring.gpg ] && pass "keyring package installs the key" \
    || fail "keyring missing"
grep -q '^URIs: https://rybib.github.io/xenon/apt' /etc/apt/sources.list.d/xenon.sources \
    && pass "points at the published repository" || fail "sources file"
# For the test, fetch from the local server instead of GitHub Pages.
sed -i "s|^URIs: .*|URIs: http://127.0.0.1:$PORT/apt|" /etc/apt/sources.list.d/xenon.sources

out="$(apt-get update 2>&1)"
if echo "$out" | grep "127.0.0.1" | grep -qE "^(Err|W:|E:)"; then
    echo "$out" | grep "127.0.0.1"
    fail "apt rejected the repository"
fi
pass "apt accepts the signed repository"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xenon-branding >/dev/null 2>&1 \
    || fail "install from the repository"
v1="$(dpkg-query -W -f '${Version}' xenon-branding)"
[[ "$v1" == *+t1 ]] && pass "installed xenon-branding $v1" || fail "version $v1"

echo "== version +t2"
publish +t2
apt-get update -qq
# What installed Xenon systems run every day (apt-daily-upgrade.timer):
${XENON_UU_CMD:-unattended-upgrade} -v >"$WORK/uu.log" 2>&1 || { cat "$WORK/uu.log"; fail "unattended-upgrade"; }
v2="$(dpkg-query -W -f '${Version}' xenon-branding)"
[[ "$v2" == *+t2 ]] && pass "unattended-upgrades updated it by itself to $v2" \
    || { grep -iE "xenon|allowed|origin" "$WORK/uu.log" | head -20; fail "still at $v2"; }

echo "== tampered repository"
# An attacker who changes what the repository offers must change the signed
# release file; its signature then no longer matches.
sed -i 's/^Description: Xenon updates$/Description: tampered/' "$WORK/site/apt/dists/stable/InRelease"
rm -f "$WORK/site/apt/dists/stable/Release" "$WORK/site/apt/dists/stable/Release.gpg"
if apt-get update 2>&1 | grep -qiE "BADSIG|signatures were invalid|not signed"; then
    pass "APT refuses a modified repository"
else
    fail "a modified repository was accepted"
fi
echo "== update system checks passed"
