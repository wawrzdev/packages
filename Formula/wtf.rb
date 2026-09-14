class Wtf < Formula
  desc "Discover commands and compose local documentation"
  homepage "https://github.com/wawrzdev/wtf"
  license "MIT"

  depends_on "fzf"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/wtf/releases/download/v0.1.1/wtf_0.1.1_darwin_arm64.tar.gz"
      sha256 "c8c860f168f4e523c850f71c02af183b3f2e66de48e70d8c7d387cedc996be56"
    else
      url "https://github.com/wawrzdev/wtf/releases/download/v0.1.1/wtf_0.1.1_darwin_amd64.tar.gz"
      sha256 "52c34cf2a73b9c80c5c34c6f45454949778a57b58b20f5e9e811532548cfd9f4"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/wtf/releases/download/v0.1.1/wtf_0.1.1_linux_arm64.tar.gz"
      sha256 "ae574b6b34331d4a054f9319c17272616cdea640822d14eac0263786a401c10b"
    else
      url "https://github.com/wawrzdev/wtf/releases/download/v0.1.1/wtf_0.1.1_linux_amd64.tar.gz"
      sha256 "0ffe0e6c63240f173d8e9c509e4f7b03654fda67e005e9b3c14309f0bfecfa6d"
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
