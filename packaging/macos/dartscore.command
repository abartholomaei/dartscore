#!/bin/sh
# Started in Terminal by dartscore.app: starts the server and opens the browser, or only
# opens the browser if dartscore is already running.
exec "$(dirname "$0")/dartscore/dartscore" launch
