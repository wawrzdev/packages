class Secret < Formula
  desc "Generate and store private machine-local credentials"
  homepage "https://github.com/wawrzdev/secret"
  license "MIT"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/secret/releases/download/v0.1.0/secret_0.1.0_darwin_arm64.tar.gz"
      sha256 "e39fe1c91c140c5bc67b84a520402ca55727115de8f724feb1b9907a6580797b"
    else
      url "https://github.com/wawrzdev/secret/releases/download/v0.1.0/secret_0.1.0_darwin_amd64.tar.gz"
      sha256 "71145bf3b664762e0316eb246945f6efccf9aebf97f7cb6d0f011d4d9f7110f6"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/wawrzdev/secret/releases/download/v0.1.0/secret_0.1.0_linux_arm64.tar.gz"
      sha256 "5985f702a4455eedb80543d611b559eaede1230f68a77810bba455316851b1b1"
    else
      url "https://github.com/wawrzdev/secret/releases/download/v0.1.0/secret_0.1.0_linux_amd64.tar.gz"
      sha256 "d13edc27e854d33a66a8bd0314fc390f70706818f19d2187f97443d7b4d2501d"
    end
  end

  def install
    bin.install "secret"
    bash_completion.install "completions/secret.bash" => "secret"
    zsh_completion.install "completions/_secret"
    fish_completion.install "completions/secret.fish"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/secret --version")
  end
end
