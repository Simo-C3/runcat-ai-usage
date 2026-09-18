# frozen_string_literal: true

# Homebrew Formula for the RunCat AI Usage monitor.
class RuncatAiUsage < Formula
  desc "AI plan usage cards for RunCat Neo"
  homepage "https://github.com/Simo-C3/runcat-ai-usage"
  url "https://github.com/Simo-C3/runcat-ai-usage/releases/download/v0.5.1/runcat-ai-usage-0.5.1.tar.gz"
  version "0.5.1"
  sha256 "2998d4aa9360a85dcf9b954ec7e8c04328dd379912bd5abca80c8b20f41db60f"
  license "MIT"

  depends_on :macos
  depends_on "python@3.13"

  def install
    libexec.install "scripts", "src"
    libexec.install "otel" if (buildpath/"otel").directory?

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
      Install or update the background monitor from your user session:
        runcat-ai-usage-install --no-open

      This starts the Collector, RunCat adapter, and automatic quota updates.

      Add the JSON files from ~/RunCatMetrics in RunCat Neo:
        Settings > Metrics > Custom Metrics > Add Custom Metrics Source

      To repair or restart the background monitor, run the same command:
        runcat-ai-usage-install

      Before uninstalling this Formula, stop the monitor with:
        runcat-ai-usage-uninstall
    EOS
  end

  test do
    assert_match "runcat-ai-usage 0.5.1", shell_output("#{bin}/runcat-ai-usage --version")
  end
end
