cask "nuvio" do
  arch arm: "arm64", intel: "x86_64"

  version "0.1.36-alpha"
  # Pinned per-arch checksums (integrity check). Bump these in the SAME commit that bumps `version`
  # — get them from: gh api repos/NuvioMedia/NuvioDesktop/releases/latest --jq '.assets[].digest'
  sha256 arm:   "8da41505125e1c164024aa57a89186318a2a8ca6af725983bd023c805fcf2a31",
         intel: "16f6a5a6fb7377778cd703cc7de955aa4ee7ba653448f4b4d1483b45a1af803f"

  url "https://github.com/NuvioMedia/NuvioDesktop/releases/download/#{version}/Nuvio-macOS-#{arch}-#{version}.dmg",
      verified: "github.com/NuvioMedia/NuvioDesktop/"
  name "Nuvio"
  desc "Media streaming desktop app (alpha)"
  homepage "https://github.com/NuvioMedia/NuvioDesktop"

  livecheck do
    url :url
    strategy :github_latest
  end

  auto_updates true

  app "Nuvio.app"

  zap trash: [
    "~/Library/Application Support/nuvio-desktop",
    "~/Library/Preferences/com.nuvio.media.desktop.plist",
    "~/Library/Saved Application State/com.nuvio.media.desktop.savedState",
  ]
end
