#!/usr/bin/env bash
# Capture screenshots of the app in demo mode on a booted simulator.
#
#   ios/scripts/screenshots.sh <simulator-udid> <out-dir>
#
# Needs the app installed (bundle id com.arxivdigest.app). Each scenario
# relaunches the app with launch options (see LaunchOptions.swift) and waits
# for it to settle. SETTLE overrides the wait in seconds.
set -euo pipefail

UDID="$1"
OUT="$2"
BUNDLE="com.arxivdigest.app"
mkdir -p "$OUT"

xcrun simctl status_bar "$UDID" override --time "9:41" --batteryState charged --batteryLevel 100 \
  --cellularBars 4 --wifiBars 3 >/dev/null 2>&1 || true

shot() {
  local name="$1" appearance="$2"; shift 2
  xcrun simctl ui "$UDID" appearance "$appearance"
  xcrun simctl terminate "$UDID" "$BUNDLE" >/dev/null 2>&1 || true
  xcrun simctl launch "$UDID" "$BUNDLE" -demo "$@" >/dev/null
  sleep "${SETTLE:-6}"
  xcrun simctl io "$UDID" screenshot --type=png "$OUT/$name.png" >/dev/null
  echo "captured $name"
}

shot 01-papers                light
shot 02-papers-dark           dark
shot 03-paper-detail          light -open-paper 1
shot 04-day-and-removed       light -day 5 -remove 1
shot 05-score-in-digest       light -score 2609.21188
shot 06-score-below-cutoff    dark  -score https://arxiv.org/abs/2609.20166v1
shot 07-config                light -tab config -dirty
shot 08-config-keywords       light -config-page keywords
shot 09-config-feeds          light -config-page feeds
shot 10-config-scoring        dark  -config-page scoring
shot 11-config-presets        light -config-page presets
shot 12-settings              light -tab settings

xcrun simctl ui "$UDID" appearance light
