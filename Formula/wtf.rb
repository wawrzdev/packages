class Wtf < Formula
  desc "Discover commands and compose local documentation"
  homepage "https://github.com/wawrzdev/wtf"
  license "MIT"

  depends_on "fzf"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/wtf/releases/download/v0.2.0/wtf_0.2.0_darwin_arm64.tar.gz"
      sha256 "354c277c592e59895f44247e9c0c8a5a1186de71d9ff8a7bf5f7641e9d885807"
    else
      url "https://github.com/wawrzdev/wtf/releases/download/v0.2.0/wtf_0.2.0_darwin_amd64.tar.gz"
      sha256 "ffbd829bbbd207ced3deb1f1568a9ead9d21306d4b5c7e0561970f6346852dca"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/wtf/releases/download/v0.2.0/wtf_0.2.0_linux_arm64.tar.gz"
      sha256 "1b28b1e226370db508cbc4959a0a1e4d3ba3076b7efc193bc30516a39fd66923"
    else
      url "https://github.com/wawrzdev/wtf/releases/download/v0.2.0/wtf_0.2.0_linux_amd64.tar.gz"
      sha256 "f088ecd5f6d4e3a6344359bc452a07b50c0fcc06474a53763ec3562381a342e8"
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
