cask "nuvio" do
  arch arm: "arm64", intel: "x86_64"

  version "0.1.29-alpha"
  # Pinned per-arch checksums (integrity check). Bump these in the SAME commit that bumps `version`
  # — get them from: gh api repos/NuvioMedia/NuvioDesktop/releases/latest --jq '.assets[].digest'
  sha256 arm:   "0d8992627cf9779f1d5f1ffab573b4a73cb89d8741b9eeea3095560acb8d86a5",
         intel: "f5f7b3df7d448adbb3c0b35481d2e7e21928643c951088aede7aabd9ffb03c8a"

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
