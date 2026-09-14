class Snip < Formula
  desc "Manage GitHub gists and GitLab snippets as local Git clones"
  homepage "https://github.com/wawrzdev/snip"
  license "MIT"

  depends_on "fzf"
  depends_on "gh"
  depends_on "git"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/snip/releases/download/v0.1.0/snip_0.1.0_darwin_arm64.tar.gz"
      sha256 "ae8d85cb4709e4dfb874de59abaf28cb2de5247c792339c8e209ed509f6a9cbc"
    else
      url "https://github.com/wawrzdev/snip/releases/download/v0.1.0/snip_0.1.0_darwin_amd64.tar.gz"
      sha256 "a090783f747e34239e4f44770203014101b2ec2ec7a9b6e09cf8e5ed839cc70f"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/snip/releases/download/v0.1.0/snip_0.1.0_linux_arm64.tar.gz"
      sha256 "9b4de356bb2e6f06d9c9005f5f3e0a6ae8b3c39bc03847da548488af8066f095"
    else
      url "https://github.com/wawrzdev/snip/releases/download/v0.1.0/snip_0.1.0_linux_amd64.tar.gz"
      sha256 "1454b534a68a8e092a920b9cbfec2e6dc0615f982272e7f0100ebc76134dd933"
    end
  end

  def install
    bin.install "snip"
    bash_completion.install "completions/snip.bash" => "snip"
    zsh_completion.install "completions/_snip"
    fish_completion.install "completions/snip.fish"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/snip --version")
  end
end
