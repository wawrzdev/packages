class Wtf < Formula
  desc "Discover commands and compose local documentation"
  homepage "https://github.com/wawrzdev/wtf"
  license "MIT"

  depends_on "fzf"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/wtf/releases/download/v0.1.0/wtf_0.1.0_darwin_arm64.tar.gz"
      sha256 "ec51372bbd8ad616b52fd80585b51a7c884b12d155c74062fcf28c2031b4cc7a"
    else
      url "https://github.com/wawrzdev/wtf/releases/download/v0.1.0/wtf_0.1.0_darwin_amd64.tar.gz"
      sha256 "79fa1a37372e6a7843be7bfa47bd9520fc4da1406f828ceb736e6b1a31ddc67f"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/wtf/releases/download/v0.1.0/wtf_0.1.0_linux_arm64.tar.gz"
      sha256 "a5427e2995fc0aaa6a3e52592c0738ede4490d658ee2681ba9f3124ff45a1105"
    else
      url "https://github.com/wawrzdev/wtf/releases/download/v0.1.0/wtf_0.1.0_linux_amd64.tar.gz"
      sha256 "32f6d6bbbbb75b8c487bd93ae32a2e31980aaaccbf87d8c5fcca2be6b598097c"
    end
  end

  def install
    bin.install "wtf"
    bash_completion.install "completions/wtf.bash" => "wtf"
    zsh_completion.install "completions/wtf.zsh" => "_wtf"
    fish_completion.install "completions/wtf.fish"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/wtf --version")
  end
end
