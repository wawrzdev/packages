#!/usr/bin/env bash
set -euo pipefail

# A real tap makes Homebrew apply formula rules, including name isolation from core.
fixture_tap="$(brew --repository)/Library/Taps/wawrzdev/homebrew-ci"
mkdir -p "$fixture_tap/Formula"
git -C "$fixture_tap" init
python3 tests/render-homebrew-fixture.py /tmp/homebrew-fixture
cp /tmp/homebrew-fixture/*.rb "$fixture_tap/Formula/"
brew style wawrzdev/ci
for formula in secret snip wtf; do
  brew install "wawrzdev/ci/$formula"
  brew test "wawrzdev/ci/$formula"
done
