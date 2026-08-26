# frozen_string_literal: true

# Homebrew Formula for the RunCat AI Usage monitor.
class RuncatAiUsage < Formula
  desc "AI plan usage cards for RunCat Neo"
  homepage "https://github.com/Simo-C3/runcat-ai-usage"
  url "https://github.com/Simo-C3/runcat-ai-usage/releases/download/v0.3.2/runcat-ai-usage-0.3.2.tar.gz"
  version "0.3.2"
  sha256 "1dfcaa9eb58d2a28f2d72163a0195345e51560a44ba6fa86a02d2448d6bed845"
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

  def post_install
    system bin/"runcat-ai-usage-install", "--no-open"
  end

  def caveats
    <<~EOS
      The background monitor was installed and started automatically.

      Add the JSON files from ~/RunCatMetrics in RunCat Neo:
        Settings > Metrics > Custom Metrics > Add Custom Metrics Source

      To repair or restart the background monitor:
        runcat-ai-usage-install

      Before uninstalling this Formula, stop the monitor with:
        runcat-ai-usage-uninstall
    EOS
  end

  test do
    assert_match "runcat-ai-usage 0.3.2", shell_output("#{bin}/runcat-ai-usage --version")
  end
end
