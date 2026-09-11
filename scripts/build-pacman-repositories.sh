#!/usr/bin/env bash
set -euo pipefail

site=${1:?usage: build-pacman-repositories.sh SITE}
if [ -n "${PACKAGES_GPG_PRIVATE_KEY_B64:-}" ] || [ -n "${PACKAGES_GPG_PASSPHRASE:-}" ]; then
  echo "repo-add must run without private signing material" >&2
  exit 1
fi

while IFS= read -r -d '' directory; do
  (
    cd "$directory"
    rm -f wawrzdev.db wawrzdev.db.tar.gz wawrzdev.files wawrzdev.files.tar.gz
    if compgen -G './*.pkg.tar.zst' >/dev/null; then
      packages=( ./*.pkg.tar.zst )
      repo-add wawrzdev.db.tar.gz "${packages[@]}"
    else
      tar --format=ustar --sort=name --mtime=@0 --owner=0 --group=0 -czf wawrzdev.db.tar.gz --files-from /dev/null
      cp wawrzdev.db.tar.gz wawrzdev.files.tar.gz
    fi
    rm -f wawrzdev.db wawrzdev.files
  )
done < <(find "$site/pacman" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
