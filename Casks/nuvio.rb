cask "nuvio" do
  arch arm: "arm64", intel: "x86_64"

  version "0.1.25-alpha"
  # Pinned per-arch checksums (integrity check). Bump these in the SAME commit that bumps `version`
  # — get them from: gh api repos/NuvioMedia/NuvioDesktop/releases/latest --jq '.assets[].digest'
  sha256 arm:   "b6f6047d3d5ef49d33b3e484c74373e5402cd5e4b00c8e7440cef5141359693e",
         intel: "81127a7775e25bec238322ae445d83efe75186dacd2e59dd1c4063797b2f63cb"

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
