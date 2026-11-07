cask "nuvio" do
  arch arm: "arm64", intel: "x86_64"

  version "0.1.35-alpha"
  # Pinned per-arch checksums (integrity check). Bump these in the SAME commit that bumps `version`
  # — get them from: gh api repos/NuvioMedia/NuvioDesktop/releases/latest --jq '.assets[].digest'
  sha256 arm:   "927b9a29da9dd3215fecbb4108e7a91731e3583c9f8a4056d5635ba04a5db778",
         intel: "6e652baca94bf7181a93d25fee977940cc350c92521819889f0b024341cd851e"

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
