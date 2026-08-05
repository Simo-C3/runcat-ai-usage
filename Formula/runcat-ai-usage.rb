# frozen_string_literal: true

# Homebrew Formula for the RunCat AI Usage monitor.
class RuncatAiUsage < Formula
  desc "AI plan usage cards for RunCat Neo"
  homepage "https://github.com/Simo-C3/runcat-ai-usage"
  url "https://github.com/Simo-C3/runcat-ai-usage/archive/0a4507d4bee348e44cbd8302c423f499677626ed.tar.gz"
  version "0.1.0"
  sha256 "f93c38f51dcf4afd3c1cb7ab734825ba393b40a2571a36b00f691156f5640787"
  license "MIT"

  depends_on :macos
  depends_on "python@3.13"

  def install
    libexec.install "scripts", "src"

    python = formula_opt_bin("python@3.13")/"python3.13"
    (bin/"runcat-ai-usage").write <<~SH
      #!/bin/sh
      export PYTHONPATH="#{libexec}/src"
      export PYTHONDONTWRITEBYTECODE=1
      exec "#{python}" -m runcat_ai_usage "$@"
    SH
    (bin/"runcat-ai-usage-install").write <<~SH
      #!/bin/sh
      export RUNCAT_AI_USAGE_PYTHON="#{python}"
      exec "#{libexec}/scripts/install.sh" "$@"
    SH
    (bin/"runcat-ai-usage-uninstall").write <<~SH
      #!/bin/sh
      exec "#{libexec}/scripts/uninstall.sh" "$@"
    SH
    chmod 0755, bin/"runcat-ai-usage"
    chmod 0755, bin/"runcat-ai-usage-install"
    chmod 0755, bin/"runcat-ai-usage-uninstall"
  end

  def caveats
    <<~EOS
      Complete the installation and start the background monitor:
        runcat-ai-usage-install

      Then add the JSON files from ~/RunCatMetrics in RunCat Neo:
        Settings > Metrics > Custom Metrics > Add Custom Metrics Source

      Before uninstalling this Formula, stop the monitor with:
        runcat-ai-usage-uninstall
    EOS
  end

  test do
    assert_match "runcat-ai-usage 0.1.0", shell_output("#{bin}/runcat-ai-usage --version")
  end
end
