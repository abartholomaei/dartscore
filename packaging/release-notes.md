## Download

| System | File | Guide |
| --- | --- | --- |
| Windows 10/11 (64-bit) | `dartscore-…-windows-x64-setup.exe` (or the portable `.zip`) | [Windows](https://github.com/abartholomaei/dartscore/blob/main/docs/install/windows.md) |
| macOS 14+ (Apple Silicon) | `dartscore-…-macos-arm64.tar.gz` | [macOS](https://github.com/abartholomaei/dartscore/blob/main/docs/install/macos.md) |
| Linux x86_64 (Debian 12+, Ubuntu 22.04+) | `dartscore-…-linux-x86_64.tar.gz` | [Linux](https://github.com/abartholomaei/dartscore/blob/main/docs/install/linux.md) |
| Linux ARM64 (Raspberry Pi 5) | `dartscore-…-linux-arm64.tar.gz` | [Linux](https://github.com/abartholomaei/dartscore/blob/main/docs/install/linux.md) |

Linux and macOS in one line:

```bash
curl -fsSL https://github.com/abartholomaei/dartscore/releases/latest/download/install.sh | sh
```

The builds are not signed: Windows SmartScreen and macOS Gatekeeper warn on the first start, the guides explain how to allow it. Checksums are in `SHA256SUMS.txt`.
