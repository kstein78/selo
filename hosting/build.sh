#!/usr/bin/env bash
# Builds one commit of a selo site and makes it live. Called by selo-update as the "deploy" user,
# after the site repo (with the engine submodule) was reset to that commit.
#   bash build.sh <site dir> <commit-sha>      (<site dir> holds repo/, releases/, current)
# Hugo and Pagefind versions are read from the site's .github/workflows/deploy.yml, so the server
# builds with the same versions as GitHub Actions. The last KEEP releases stay on disk and
# <site dir>/current (what Caddy serves) is switched atomically.
set -euo pipefail
site=${1:?usage: build.sh <site dir> <commit-sha>}
sha=${2:?usage: build.sh <site dir> <commit-sha>}
BIN=${SELO_BIN:-/srv/selo/bin}
KEEP=3
repo=$site/repo
rel=$site/releases
mkdir -p "$rel" "$BIN"
cd "$repo"

ver=$(sed -n 's/^ *HUGO_VERSION: *\([0-9.]*\).*/\1/p' .github/workflows/deploy.yml | head -1)
[ -n "$ver" ] || { echo "HUGO_VERSION not found in .github/workflows/deploy.yml" >&2; exit 1; }
hugo=$BIN/hugo-$ver
if [ ! -x "$hugo" ]; then
  case $(uname -m) in x86_64) arch=amd64 ;; aarch64) arch=arm64 ;; *) echo "unsupported CPU $(uname -m)" >&2; exit 1 ;; esac
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/gohugoio/hugo/releases/download/v${ver}/hugo_extended_${ver}_linux-${arch}.tar.gz" | tar -xz -C "$tmp" hugo
  install -m 755 "$tmp/hugo" "$hugo"; rm -rf "$tmp"
  echo "installed Hugo $ver"
fi

# Serbian Cyrillic pages from the Latin ones (normally already committed; this makes sure).
python3 themes/selo/scripts/sr_cyrl.py >/dev/null || echo "warning: sr_cyrl.py failed, building with the committed Cyrillic files" >&2

pfver=$(sed -n 's/^ *PAGEFIND_VERSION: *\([0-9.]*\).*/\1/p' .github/workflows/deploy.yml | head -1)
pagefind=""
if [ -n "$pfver" ]; then
  pagefind=$BIN/pagefind-$pfver
  if [ ! -x "$pagefind" ]; then
    case $(uname -m) in x86_64) pfarch=x86_64 ;; aarch64) pfarch=aarch64 ;; *) pfarch="" ;; esac
    tmp=$(mktemp -d)
    if [ -n "$pfarch" ] && curl -fsSL "https://github.com/Pagefind/pagefind/releases/download/v${pfver}/pagefind-v${pfver}-${pfarch}-unknown-linux-musl.tar.gz" | tar -xz -C "$tmp" pagefind; then
      install -m 755 "$tmp/pagefind" "$pagefind"; echo "installed Pagefind $pfver"
    else
      echo "warning: could not install Pagefind $pfver, building without search index" >&2; pagefind=""
    fi
    rm -rf "$tmp"
  fi
fi

out=$rel/$sha
rm -rf "$out"
"$hugo" --quiet --gc --minify --destination "$out"
[ -n "$pagefind" ] && { "$pagefind" --site "$out" --quiet || echo "warning: Pagefind failed" >&2; }
printf '%s\n' "$sha" > "$out/version.txt"
ln -sfn "$out" "$site/current.new"
mv -Tf "$site/current.new" "$site/current"
echo "live: $(basename "$site") $sha (Hugo $ver)"
ls -1dt "$rel"/*/ | tail -n +$((KEEP + 1)) | xargs -r rm -rf
