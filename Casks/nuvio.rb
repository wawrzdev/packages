cask "nuvio" do
  arch arm: "arm64", intel: "x86_64"

  version "0.1.34-alpha"
  # Pinned per-arch checksums (integrity check). Bump these in the SAME commit that bumps `version`
  # — get them from: gh api repos/NuvioMedia/NuvioDesktop/releases/latest --jq '.assets[].digest'
  sha256 arm:   "497856e825f4efe1a27d286de7925dc5b7abbd7644ec6b0ae2abdf6df4e75e94",
         intel: "058e4657d5b08af08ca54e93d6aae0109c9af601251e6d29a35c688d16dbc517"

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
