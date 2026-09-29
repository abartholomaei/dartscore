#!/bin/sh
# Main executable of dartscore.app: runs dartscore in a Terminal window (see build.py).
exec open -a Terminal "$(dirname "$0")/../Resources/dartscore.command"
